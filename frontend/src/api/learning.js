/**
 * 学习报告 API (interactive 模式可视化报告)
 *
 * POST /api/learning/report — 按 session_id 补跑 graph_controller + content_generator
 * + reviewer (单轮), 返回三类可视化数据契约 learning_report (盲区/难度曲线/路径图
 * + review_status + M5 真实质量指标)。幂等: 首次补跑后后端按 session 缓存。
 *
 * 对齐 backend/app/api/learning.py
 */
import http from './index'
import { postSseJson } from './diagnostics'
import { withOverrides } from '@/stores/agentLlm'

/**
 * 拉取 interactive 会话的可视化报告 (补跑, 首次约 9+ 次 LLM, 后端按 session 缓存)
 *
 * @param {Object} params
 * @param {string} params.sessionId - assess(interactive) + submit 后的 session_id
 * @param {AbortSignal} [params.signal]
 * @returns {Promise<{
 *   session_id: string,
 *   profile: Object,
 *   knowledge_graph: Object,
 *   generated_content: Object,
 *   review_results: Object,
 *   learning_report: { blind_spots, difficulty_match, learning_path, review_status, quality_metrics, generated_at },
 *   orchestration_log: string[]
 * }>}
 */
export function fetchLearningReport({ sessionId }, signal) {
  // 补跑涉及逐节点 LLM 生成 (最长几分钟), 放宽到 300s (默认 60s 不够)
  return http.post('/api/learning/report', withOverrides({
    session_id: sessionId,
  }), { signal, timeout: 300_000 })
}

/**
 * 报告补跑（SSE 流式）— /api/learning/report/stream (v1.3.3 等待优化感知层)
 *
 * 进度: path 组装 → generate 逐资源 (done/total) → review 审核 → judge 裁判。
 * 后端缓存命中时直接同步返回 JSON (非流), Promise 同样 resolve。
 * 后端缺流式端点时 reject e.status===404, 调用方降级 fetchLearningReport。
 *
 * @param {Object} params - { sessionId }
 * @param {Object} [opts] - { onProgress, signal }
 * @returns {Promise<Object>} done 事件 data (LearningReportResponse 结构)
 */
export function fetchLearningReportStream({ sessionId }, { onProgress, signal } = {}) {
  return postSseJson('/api/learning/report/stream', withOverrides({ session_id: sessionId }), { onProgress, signal })
}
