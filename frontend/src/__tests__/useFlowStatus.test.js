/**
 * useFlowStatus — Phase 3a 流程进度 DAG 输入 (agent 状态 → 阶段/current/计数)
 *
 * 覆盖: status 映射、current(首个 running)、doneCount/pendingCount、无运行中时 current=null。
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

// useFlowStatus 内部真调 useAgentStatus (其依赖的 assessment store 已 mock)
import { useFlowStatus } from '@/composables/useFlowStatus'

function reset() {
  Object.assign(mockAssessment, {
    hasResults: false, loading: false, phase: 'idle',
    orchestrationLog: [], orchestrationEvents: [], profile: null, assessment: null,
    knowledgeGraph: null, generatedContent: null, feedbackContent: null,
    reviewResults: null,
  })
}

const ev = (type, agent, status, message) => ({ type, agent, status, message, log: message })

describe('useFlowStatus (Phase 3a 流程进度)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    reset()
  })

  it('事件驱动阶段状态: done/running/failed 映射 + current 落在首个 running', async () => {
    mockAssessment.loading = true
    mockAssessment.orchestrationEvents = [
      ev('agent-start', 'orchestrator', 'running', '主控调度: 编排'),
      ev('agent-end', 'orchestrator', 'done', '主控调度完成'),
      ev('agent-start', 'diagnostics', 'running', '学情检测: 开始'),
      ev('agent-end', 'diagnostics', 'done', '学情检测: 判分 7/10'),
      ev('agent-start', 'reviewer', 'running', '内容审核: 开始'),
    ]
    const flow = useFlowStatus()
    await nextTick()
    const byKey = Object.fromEntries(flow.stages.value.map((s) => [s.key, s]))
    expect(byKey.diagnostics.status).toBe('done')
    expect(byKey.reviewer.status).toBe('running')
    expect(byKey.reviewer.current).toBe(true)   // 首个 running
    expect(byKey.diagnostics.current).toBe(false)
    expect(byKey.orchestrator.status).toBe('done')
    expect(flow.currentLabel.value).toBe('内容审核')
    expect(flow.doneCount.value).toBe(2)        // orchestrator + diagnostics
  })

  it('无运行中阶段时 current 全 false, currentLabel null', async () => {
    mockAssessment.orchestrationEvents = [
      ev('agent-end', 'diagnostics', 'done', '学情检测: 完成'),
      ev('agent-end', 'graph_controller', 'done', '图谱组装完成'),
    ]
    const flow = useFlowStatus()
    await nextTick()
    expect(flow.stages.value.some((s) => s.current)).toBe(false)
    expect(flow.currentLabel.value).toBeNull()
    expect(flow.doneCount.value).toBe(2)
  })

  it('阶段顺序 = AGENT_DEFS 序 (orchestrator → diagnostics → …)', async () => {
    const flow = useFlowStatus()
    await nextTick()
    const keys = flow.stages.value.map((s) => s.key)
    expect(keys[0]).toBe('orchestrator')
    expect(keys).toContain('diagnostics')
    expect(keys).toContain('content_generator')
  })

  it('failed 阶段保留 failed 状态', async () => {
    mockAssessment.orchestrationEvents = [ev('error', 'reviewer', 'failed', '内容审核不通过')]
    const flow = useFlowStatus()
    await nextTick()
    expect(flow.stages.value.find((s) => s.key === 'reviewer').status).toBe('failed')
  })
})
