/**
 * 学情检测 API
 *
 * POST /api/diagnostics/assess         阻塞式测评
 * POST /api/diagnostics/assess/stream  SSE 流式测评 (demo模式，防超时)
 * POST /api/diagnostics/submit         interactive 提交答题
 * POST /api/diagnostics/feedback       动态反馈再生
 *
 * 对齐 backend/app/api/diagnostics.py
 */
import http from './index'
import { withOverrides, withFeedbackOverrides } from '@/stores/agentLlm'

/**
 * 发起学情测评
 *
 * @param {Object} params
 * @param {string} params.targetDirection - 学习目标方向（自然语言），如 "Python 基础语法入门"
 * @param {'demo'|'interactive'} [params.mode='demo'] - 测评模式
 * @param {Array<{node_id: string, mastery: number}>} [params.knownTopics=[]] - 已知知识点
 * @param {'no_project'|'with_project'} [params.scene='no_project'] - 场景类型
 * @param {number} [params.maxRetries=3] - 审核打回最大轮数 (1-5)
 * @param {string} [params.tavilyKey] - Tavily key (目标未收录时动态建域联网检索)
 * @returns {Promise<{
 *   session_id: string,
 *   profile: Object,
 *   review_results: Object,
 *   assessment: Object,
 *   orchestration_log: string[]
 * }>}
 */
export function submitAssessment({
  targetDirection,
  mode = 'demo',
  knownTopics = [],
  scene = 'no_project',
  maxRetries = 3,
  tavilyKey,
}, signal) {
  // interactive timeout 300s: 目标未命中既有域时后端会动态建域
  // (Tavily 检索 + LLM 生成 ~10 节点/20 题, 常超默认 60s, 含一轮重试余量)
  const opts = {}
  if (mode === 'interactive') opts.timeout = 300_000
  if (signal) opts.signal = signal
  return http.post('/api/diagnostics/assess', withOverrides({
    target_direction: targetDirection,
    mode,
    known_topics: knownTopics,
    scene,
    max_retries: maxRetries,
    tavily_key: tavilyKey || undefined,
  }), Object.keys(opts).length ? opts : undefined)
}

/**
 * 健康检查
 * @returns {Promise<{status: string, app: string, version: string, neo4j: string, llm_api: string}>}
 */
export function healthCheck() {
  return http.get('/api/health')
}

/**
 * 版本信息
 * @returns {Promise<{app: string, version: string, langgraph: string, neo4j: string}>}
 */
export function getVersion() {
  return http.get('/api/version')
}

/**
 * Phase 1: 读取已落盘的 run 记录 (复盘/续跑)。404 表示无运行记录。
 * @param {string} sessionId
 * @returns {Promise<Object|null>} run 记录 (含 request/summary/orchestration_events/orchestration_log)
 */
export async function fetchRun(sessionId) {
  const data = await http.get(`/api/diagnostics/runs/${encodeURIComponent(sessionId)}`)
  return data
}

/**
 * Phase 1: 最近 run 摘要列表 (历史运行入口)。
 * @param {number} [limit=20]
 * @returns {Promise<{count:number, runs:Array}>}
 */
export async function fetchRuns(limit = 20) {
  const data = await http.get('/api/diagnostics/runs', { params: { limit } })
  return data
}

/**
 * issue-83: 删除一条运行记录 (永久删除本地 run 目录; 二次确认由 UI 层负责)。
 * @param {string} sessionId
 * @returns {Promise<{session_id, deleted:boolean}>}
 */
export async function deleteRun(sessionId) {
  const data = await http.delete(`/api/diagnostics/runs/${encodeURIComponent(sessionId)}`)
  return data
}

/**
 * Phase 2: 流程定义列表 (流程即数据; Phase 3 画布的数据底座)。
 * @returns {Promise<{workflows: Array<{id,name,description,stages}>}>}
 */
export async function fetchWorkflows() {
  const data = await http.get('/api/diagnostics/workflows')
  return data
}

/**
 * Phase 4: 流程决策确定性求值 (不跑 Agent, 如 feedback 策略由 correct_ratio 判定)。
 * @param {string} workflowId
 * @param {Object} [context] 求值上下文 (点路径字段, 如 { correct_ratio: 0.9 })
 * @returns {Promise<{workflow_id, ok, decisions: Array<{id,label,chosen}>}>}
 */
export async function fetchWorkflowEvaluate(workflowId, context = {}) {
  const data = await http.post('/api/diagnostics/workflows/evaluate', {
    workflow_id: workflowId,
    context,
  })
  return data
}

/**
 * Phase 3b: 保存流程定义草稿 (未提交, WIP 可不通过严格校验)。
 */
export async function saveWorkflowDraft(workflowId, definition) {
  const data = await http.put(
    `/api/diagnostics/workflows/${encodeURIComponent(workflowId)}/draft`,
    { definition },
  )
  return data
}

/**
 * Phase 3b: 提交发布流程定义 (校验→原子 revision 保存)。
 * @returns {Promise<{id, revision, committed}>} 内置 id 会被后端以 409 拒绝
 */
export async function commitWorkflow(workflowId, definition, { note = '', reviewedBy = '' } = {}) {
  const data = await http.post(
    `/api/diagnostics/workflows/${encodeURIComponent(workflowId)}/commit`,
    { definition, note, reviewed_by: reviewedBy },
  )
  return data
}

/**
 * Phase 3b: 流程定义 revision 列表 (可回滚)。
 */
export async function fetchWorkflowRevisions(workflowId) {
  const data = await http.get(`/api/diagnostics/workflows/${encodeURIComponent(workflowId)}/revisions`)
  return data
}

/**
 * Phase 3b: 回滚流程定义到指定 revision。
 */
export async function restoreWorkflowRevision(workflowId, revision) {
  const data = await http.post(
    `/api/diagnostics/workflows/${encodeURIComponent(workflowId)}/restore`,
    { revision },
  )
  return data
}

// ============================================================
// W5 — interactive 答题闭环（assess(interactive) → submit → feedback）
// ============================================================

/**
 * 提交 interactive 答题（W5）
 *
 * 三步流程的第二步。session_id 必须来自 assess(interactive) 响应，
 * 后端用内存 LRU(100) 缓存出题信息，服务重启会失效（404）。
 *
 * @param {Object} params
 * @param {string} params.sessionId - assess(interactive) 返回的 session_id
 * @param {string[]} params.answers - 逐题作答，顺序与 questions 一致
 * @returns {Promise<{
 *   session_id: string,
 *   profile: Object,
 *   assessment: Object,
 *   feedback: { strategy: 'advance'|'remediate'|'scaffold', accuracy: number, description: string },
 *   knowledge_graph: Object,
 *   orchestration_log: string[]
 * }>}
 */
export function submitAnswers({ sessionId, answers, learnerKey, learningStyleQuiz, practicalEvidence, demographics }, signal) {
  // 判分+画像+图谱组装为 LLM 关键路径, 显式放宽到 300s (慢网络/慢模型不误杀)
  const cfg = { timeout: 300_000 }
  if (signal) cfg.signal = signal
  return http.post('/api/diagnostics/submit', withOverrides({
    session_id: sessionId,
    answers,
    learner_key: learnerKey || undefined,
    // W5 三维测评: VARK 问卷答案 + 实操证据 (可空 — 后端按占位处理)
    learning_style_quiz: Array.isArray(learningStyleQuiz) && learningStyleQuiz.length ? learningStyleQuiz : undefined,
    practical_evidence: practicalEvidence || undefined,
    // 赛题(2) 先验画像: 学习背景 {education, major} (可选采集, 全空不上送)
    demographics: (demographics && (demographics.education || demographics.major)) ? demographics : undefined,
  }), cfg)
}

/**
 * 动态反馈内容再生（W5）
 *
 * 三步流程的第三步。strategy 必须用 submit 响应里返回的那个，前端勿硬编码。
 *
 * @param {Object} params
 * @param {string} params.sessionId
 * @param {'advance'|'remediate'|'scaffold'} params.strategy - 来自 submit 响应的 feedback.strategy
 * @param {Object} params.profile - 来自 submit 响应的 profile
 * @returns {Promise<{
 *   session_id: string,
 *   strategy: string,
 *   resources: Array,
 *   node_count: number
 * }>}
 */
export function requestFeedback({ sessionId, strategy, profile, tavilyKey }, signal) {
  // timeout 150s: feedback 逐节点 LLM 再生 + 可选 Tavily 联网, 常超默认 60s
  // withFeedbackOverrides: 反馈走「快模型」(设置页反馈快模型), 交互式等待敏感
  return http.post('/api/diagnostics/feedback', withFeedbackOverrides({
    session_id: sessionId,
    strategy,
    profile,
    tavily_key: tavilyKey || undefined,
  }), { signal, timeout: 300_000 })
}

// ============================================================
// W7③ — SSE 流式测评（demo 模式，解决 2-4 分钟超前端 60s 超时）
// ============================================================

/**
 * SSE 流式测评 — 仅 demo 模式使用
 *
 * 用 fetch + ReadableStream 手动解析 SSE（EventSource 只支持 GET）。
 * 逐步推送节点进度，跑完推最终结果，不会因 axios 60s 超时而中断。
 *
 * @param {Object} payload — { targetDirection, scene, maxRetries } (mode 固定 demo)
 * @param {Object} callbacks
 * @param {Function} callbacks.onProgress — ({node, message, log_tail}) => void
 * @param {Function} callbacks.onDone     — (AssessResponse) => void
 * @param {Function} callbacks.onError    — (detail: string) => void
 * @returns {Promise<void>}
 */
// SSE block 解析 (event/data 段落, 取首行单行标记; 与 IPC 代理分帧契约一致)
function _dispatchSseBlock(block, { onProgress, onDone, onError }) {
  if (!block || !block.trim()) return
  const event = block.match(/^event:\s*(.+)$/m)?.[1]
  const dataStr = block.match(/^data:\s*(.+)$/m)?.[1]
  if (!event || !dataStr) return
  let data
  try { data = JSON.parse(dataStr) } catch { return }
  if (event === 'progress') onProgress?.(data)
  else if (event === 'done') onDone?.(data)
  else if (event === 'error') onError?.(data.detail || '测评流程失败')
  // start 事件可忽略
}

// 浏览器 dev 回退: fetch + ReadableStream 直连 /api (Vite proxy → 后端)。
// 与 useChatStream 浏览器回退同款 \n\n 分帧 + 看门狗 (60s 无数据判断流, issue-07/m5)。
async function _streamViaFetch(url, body, cbs) {
  let settled = false
  const fail = (msg) => { if (!settled) { settled = true; cbs.onError?.(msg) } }
  let resp
  try {
    resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch (e) {
    fail(e?.message || '网络请求失败')
    return
  }
  if (!resp.ok || !resp.body) {
    const text = await resp.text().catch(() => '')
    fail(text || `HTTP ${resp.status}`)
    return
  }
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let watchdog = null
  const armWatchdog = () => {
    clearTimeout(watchdog)
    watchdog = setTimeout(() => {
      fail('SSE 流超时（后端 60s 无数据，可能已断流）')
      void reader.cancel().catch(() => {})
    }, 60_000)
  }
  armWatchdog()
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      armWatchdog()
      buffer += decoder.decode(value, { stream: true })
      const parts = buffer.split('\n\n')
      buffer = parts.pop()
      for (const b of parts) _dispatchSseBlock(b, cbs)
    }
  } catch (e) {
    fail(e?.message || 'SSE 流中断')
  } finally {
    clearTimeout(watchdog)
  }
}

/**
 * SSE 流式测评 — 仅 demo 模式使用
 *
 * 用 fetch + ReadableStream 手动解析 SSE（EventSource 只支持 GET）。
 * 逐步推送节点进度，跑完推最终结果，不会因 axios 60s 超时而中断。
 *
 * 双环境: Electron 走 IPC SSE 代理; 浏览器 dev 走 fetch 回退 (issue-07)。
 *
 * @param {Object} payload — { targetDirection, scene, maxRetries } (mode 固定 demo)
 * @param {Object} callbacks
 * @param {Function} callbacks.onProgress — ({node, message, log_tail}) => void
 * @param {Function} callbacks.onDone     — (AssessResponse) => void
 * @param {Function} callbacks.onError    — (detail: string) => void
 * @returns {Promise<void>}
 */
export async function startAssessmentStream(payload, { onProgress, onDone, onError }) {
  const body = withOverrides({
    target_direction: payload.targetDirection,
    mode: 'demo',
    scene: payload.scene || 'no_project',
    max_retries: payload.maxRetries ?? 3,
  })

  // 浏览器 dev 回退: 无 Electron window.api.http
  if (typeof window === 'undefined' || !window.api?.http) {
    return _streamViaFetch('/api/diagnostics/assess/stream', body, { onProgress, onDone, onError })
  }

  // S1: 走 IPC SSE 代理 (window.api.http.stream), 桌面应用无需浏览器 fetch。
  // http-proxy.js 转发后端 SSE, 逐块推 'http:stream:chunk' 事件。
  // F3: 生成 reqId 并按之过滤 IPC 事件, 避免与 chat 等并发 SSE 流串扰。
  // http-proxy 已按 \n\n 分帧, 每个 http:stream:chunk 就是一个完整 SSE block, 直接解析。
  const reqId = `s${Date.now()}-${Math.floor(Math.random() * 1e6)}`
  const offChunk = window.api.http.onChunk((rid, block) => {
    if (rid !== reqId) return
    _dispatchSseBlock(block, { onProgress, onDone, onError })
  })
  const offDone = window.api.http.onDone((rid) => { if (rid === reqId) { offChunk(); offDone(); offError() } })
  const offError = window.api.http.onError((rid, err) => {
    if (rid !== reqId) return
    offChunk(); offDone(); offError()
    onError?.(err || 'SSE 流失败')
  })

  try {
    await window.api.http.stream('/api/diagnostics/assess/stream', body, reqId)
  } catch (e) {
    offChunk(); offDone(); offError()
    onError?.(e.message || '网络请求失败')
  }
}