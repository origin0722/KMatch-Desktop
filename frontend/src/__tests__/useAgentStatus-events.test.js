/**
 * useAgentStatus - Phase 0 结构化事件优先推导 (后端 to_log_event 产出)
 *
 * 验证:
 *   1. orchestrationEvents 驱动 agentNodes 状态 (running/done/failed)
 *   2. 事件优先于日志正则 (两者并存时以事件为准)
 *   3. run-end degraded → orchestrator failed; run-end done → orchestrator done
 *   4. currentAction 取最后一条事件的 message
 *   5. retryCount 仍从日志 "(第N轮)" 合并 (事件不带轮数)
 *   6. 无事件时回退正则推导 (向后兼容)
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'

const { mockAssessment } = vi.hoisted(() => {
  const { reactive } = require('vue')
  return {
    mockAssessment: reactive({
      hasResults: false, loading: false, phase: 'idle',
      orchestrationLog: [], orchestrationEvents: [], profile: null, assessment: null,
      knowledgeGraph: null, generatedContent: null, feedbackContent: null,
      reviewResults: null,
    }),
  }
})
vi.mock('@/stores/assessment', () => ({ useAssessmentStore: () => mockAssessment }))

const { useAgentStatus } = await import('@/composables/useAgentStatus')

function reset() {
  Object.assign(mockAssessment, {
    hasResults: false, loading: false, phase: 'idle',
    orchestrationLog: [], orchestrationEvents: [], profile: null, assessment: null,
    knowledgeGraph: null, generatedContent: null, feedbackContent: null,
    reviewResults: null,
  })
}

// 后端 to_log_event 语义一致的样例事件
const ev = (type, agent, status, message, log = message) => ({ type, agent, status, message, log })

describe('useAgentStatus 结构化事件 (Phase 0)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    reset()
  })

  it('agentNodes: 事件直接驱动 running/done/failed', async () => {
    mockAssessment.loading = true
    mockAssessment.orchestrationEvents = [
      ev('agent-start', 'diagnostics', 'running', '学情检测: 开始'),
      ev('agent-end', 'diagnostics', 'done', '学情检测: 判分 7/10'),
      ev('agent-start', 'content_generator', 'running', '领域知识生成: 开始'),
      ev('error', 'reviewer', 'failed', '内容审核不通过'),
    ]
    const { agentNodes, completedCount, pendingCount } = useAgentStatus()
    await nextTick()
    const byKey = Object.fromEntries(agentNodes.value.map((a) => [a.key, a.status]))
    expect(byKey.diagnostics).toBe('done')
    expect(byKey.content_generator).toBe('running')
    expect(byKey.reviewer).toBe('failed')
    expect(byKey.orchestrator).toBe('idle')
    expect(completedCount.value).toBe(1)
    expect(pendingCount.value).toBe(2) // 仅 idle 计入; running(内容生成)/failed(审核) 不算
  })

  it('事件优先于日志正则 (两者并存时以事件为准)', async () => {
    // 日志正则会误判此文案 (发音/措辞), 事件应覆盖
    mockAssessment.loading = true
    mockAssessment.orchestrationLog = ['[ts] ✅ 学情检测 完成']
    mockAssessment.orchestrationEvents = [
      ev('agent-start', 'diagnostics', 'running', '学情检测: 开始'),
      ev('agent-start', 'reviewer', 'running', '画像模式: 审核学情检测产出的用户画像'),
    ]
    const { agentNodes } = useAgentStatus()
    await nextTick()
    const byKey = Object.fromEntries(agentNodes.value.map((a) => [a.key, a.status]))
    // 事件里 reviewer 是 running 而非 done → 以事件为准
    expect(byKey.reviewer).toBe('running')
    // diagnostics 事件仍 running (未 done) → 不以日志 ✅ 为准
    expect(byKey.diagnostics).toBe('running')
  })

  it('run-end degraded → orchestrator degraded; run-end done → orchestrator done', async () => {
    mockAssessment.loading = true
    mockAssessment.orchestrationEvents = [
      ev('run-end', 'orchestrator', 'degraded', '流程结束 (超过最大重试, 降级为待人工审核)'),
    ]
    const { agentNodes } = useAgentStatus()
    await nextTick()
    let byKey = Object.fromEntries(agentNodes.value.map((a) => [a.key, a.status]))
    expect(byKey.orchestrator).toBe('degraded') // 降级 ≠ 失败, 独立可视化

    reset()
    mockAssessment.loading = true
    mockAssessment.orchestrationEvents = [
      ev('run-end', 'orchestrator', 'done', '流程结束'),
    ]
    const s2 = useAgentStatus()
    await nextTick()
    byKey = Object.fromEntries(s2.agentNodes.value.map((a) => [a.key, a.status]))
    expect(byKey.orchestrator).toBe('done')
  })

  it('⚠️ 降级事件 → 该 Agent 显示 degraded', async () => {
    mockAssessment.orchestrationEvents = [
      ev('info', 'content_generator', 'degraded', '⚠️ LLM 未配置, 内容生成降级'),
      ev('agent-end', 'diagnostics', 'done', '学情检测完成'),
    ]
    const { agentNodes } = useAgentStatus()
    await nextTick()
    const byKey = Object.fromEntries(agentNodes.value.map((a) => [a.key, a.status]))
    expect(byKey.content_generator).toBe('degraded')
    expect(byKey.diagnostics).toBe('done')
  })

  it('currentAction 取最后一条事件的 message', async () => {
    mockAssessment.loading = true
    mockAssessment.orchestrationEvents = [
      ev('agent-start', 'diagnostics', 'running', '学情检测: 开始'),
      ev('agent-start', 'content_generator', 'running', '领域知识生成: 开始'),
    ]
    const { currentAction, pipelineRunning } = useAgentStatus()
    await nextTick()
    expect(pipelineRunning.value).toBe(true)
    expect(currentAction.value.label).toBe('内容生成')
    expect(currentAction.value.action).toBe('领域知识生成: 开始')
  })

  it('retryCount 从日志合并 (事件不带轮数)', async () => {
    mockAssessment.loading = true
    mockAssessment.orchestrationEvents = [
      ev('agent-start', 'reviewer', 'running', '内容审核: 开始'),
    ]
    mockAssessment.orchestrationLog = ['[ts] 🔍 内容审核 第3轮 打回']
    const { agentNodes } = useAgentStatus()
    await nextTick()
    const reviewer = agentNodes.value.find((a) => a.key === 'reviewer')
    expect(reviewer.status).toBe('running')
    expect(reviewer.retryCount).toBe(2) // maxRetry-1
  })

  it('无事件时回退正则推导 (向后兼容)', async () => {
    mockAssessment.loading = true
    mockAssessment.orchestrationLog = ['[ts] ✅ 学情检测 完成']
    const { agentNodes } = useAgentStatus()
    await nextTick()
    const byKey = Object.fromEntries(agentNodes.value.map((a) => [a.key, a.status]))
    expect(byKey.diagnostics).toBe('done')
  })
})
