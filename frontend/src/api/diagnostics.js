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
}, signal) {
  return http.post('/api/diagnostics/assess', withOverrides({
    target_direction: targetDirection,
    mode,
    known_topics: knownTopics,
    scene,
    max_retries: maxRetries,
  }), signal ? { signal } : undefined)
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
export function submitAnswers({ sessionId, answers }, signal) {
  return http.post('/api/diagnostics/submit', withOverrides({
    session_id: sessionId,
    answers,
  }), signal ? { signal } : undefined)
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
  }), { signal, timeout: 150_000 })
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
export async function startAssessmentStream(payload, { onProgress, onDone, onError }) {
  // S1: 走 IPC SSE 代理 (window.api.http.stream), 桌面应用无需浏览器 fetch。
  // http-proxy.js 转发后端 SSE, 逐块推 'http:stream:chunk' 事件。
  const body = withOverrides({
    target_direction: payload.targetDirection,
    mode: 'demo',
    scene: payload.scene || 'no_project',
    max_retries: payload.maxRetries ?? 3,
  })

  // F3: 生成 reqId 并按之过滤 IPC 事件, 避免与 chat 等并发 SSE 流串扰。
  // http-proxy 已按 \n\n 分帧, 每个 http:stream:chunk 就是一个完整 SSE block, 直接解析。
  const reqId = `s${Date.now()}-${Math.floor(Math.random() * 1e6)}`
  const offChunk = window.api.http.onChunk((rid, block) => {
    if (rid !== reqId) return
    if (!block.trim()) return
    const event = block.match(/^event:\s*(.+)$/m)?.[1]
    const dataStr = block.match(/^data:\s*(.+)$/m)?.[1]
    if (!event || !dataStr) return
    let data
    try { data = JSON.parse(dataStr) } catch { return }
    if (event === 'progress') onProgress?.(data)
    else if (event === 'done') onDone?.(data)
    else if (event === 'error') onError?.(data.detail || '测评流程失败')
    // start 事件可忽略
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