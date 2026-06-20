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
  return http.post('/api/diagnostics/assess', {
    target_direction: targetDirection,
    mode,
    known_topics: knownTopics,
    scene,
    max_retries: maxRetries,
  }, signal ? { signal } : undefined)
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
 *   feedback: { strategy: 'advance'|'remediate'|'scaffold', accuracy: number, description: string }
 * }>}
 */
export function submitAnswers({ sessionId, answers }, signal) {
  return http.post('/api/diagnostics/submit', {
    session_id: sessionId,
    answers,
  }, signal ? { signal } : undefined)
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
export function requestFeedback({ sessionId, strategy, profile }, signal) {
  return http.post('/api/diagnostics/feedback', {
    session_id: sessionId,
    strategy,
    profile,
  }, signal ? { signal } : undefined)
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
  let resp
  try {
    resp = await fetch('/api/diagnostics/assess/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        target_direction: payload.targetDirection,
        mode: 'demo',
        scene: payload.scene || 'no_project',
        max_retries: payload.maxRetries ?? 3,
      }),
    })
  } catch (e) {
    onError(e.message || '网络请求失败')
    return
  }

  if (!resp.ok) {
    const text = await resp.text().catch(() => '')
    onError(text || `HTTP ${resp.status}`)
    return
  }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // SSE 事件以 \n\n 分隔
      const blocks = buffer.split('\n\n')
      buffer = blocks.pop() // 最后一块可能不完整，留待下次拼接

      for (const block of blocks) {
        if (!block.trim()) continue
        const event = block.match(/^event:\s*(.+)$/m)?.[1]
        const dataStr = block.match(/^data:\s*(.+)$/m)?.[1]
        if (!event || !dataStr) continue

        let data
        try { data = JSON.parse(dataStr) } catch { continue }

        if (event === 'progress') {
          onProgress?.(data)
        } else if (event === 'done') {
          onDone?.(data)
        } else if (event === 'error') {
          onError?.(data.detail || '测评流程失败')
        }
        // start 事件可忽略
      }
    }
  } catch (e) {
    onError?.(e.message || 'SSE 流读取中断')
  } finally {
    reader.cancel().catch(() => {})
  }
}
