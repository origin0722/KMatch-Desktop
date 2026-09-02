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

  it('定义驱动: 按 workflow 阶段渲染真实拓扑 + agents 聚合状态 + 依赖边', async () => {
    mockAssessment.loading = true
    mockAssessment.orchestrationEvents = [
      ev('agent-end', 'diagnostics', 'done', '学情检测完成'),
      ev('agent-start', 'reviewer', 'running', '内容审核: 开始'),
    ]
    const DEF = {
      id: 'x', name: 'X',
      stages: [
        { id: 'diagnostics', label: '学情检测', agents: ['diagnostics'], dependencies: [] },
        { id: 'graph', label: '图谱组装', agents: ['graph_controller'], dependencies: ['diagnostics'] },
        { id: 'review-content', label: '内容审核', agents: ['reviewer'], dependencies: ['graph'] },
      ],
    }
    const flow = useFlowStatus(DEF)
    await nextTick()
    expect(flow.stages.value.map((s) => s.key)).toEqual(['diagnostics', 'graph', 'review-content'])
    expect(flow.stages.value.find((s) => s.key === 'diagnostics').status).toBe('done')
    expect(flow.stages.value.find((s) => s.key === 'graph').status).toBe('idle')
    expect(flow.stages.value.find((s) => s.key === 'review-content').status).toBe('running')
    expect(flow.stages.value.find((s) => s.key === 'review-content').current).toBe(true)
    expect(flow.edges.value).toEqual([
      { source: 'diagnostics', target: 'graph' },
      { source: 'graph', target: 'review-content' },
    ])
    expect(flow.currentLabel.value).toBe('内容审核')
    expect(flow.doneCount.value).toBe(1)
  })

  it('有定义但 stages 为空 → 回退 AGENT_DEFS 线性链', async () => {
    const flow = useFlowStatus({ id: 'empty', stages: [] })
    await nextTick()
    expect(flow.stages.value.length).toBeGreaterThan(0)
    expect(flow.edges.value).toBeNull() // 回退时不提供边, FlowDiagram 默认线性
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

  it('资源阶段全员延后时聚合为 deferred (不落回 idle 灰色)', async () => {
    // 诊断+图谱就绪、资源未生成 → useAgentStatus 派生 deferred (与 StageAgent 列表文案同源)
    mockAssessment.hasResults = true
    mockAssessment.loading = false
    mockAssessment.profile = { theory_level: 2, practical_level: 1, weak_topics: [] }
    mockAssessment.assessment = { correct_count: 6, total_count: 10 }
    mockAssessment.knowledgeGraph = { learning_path: [{ node_id: 'PY-001' }] }
    mockAssessment.generatedContent = null
    mockAssessment.reviewResults = null
    mockAssessment.orchestrationEvents = []
    const DEF = {
      id: 'x', name: 'X',
      stages: [
        { id: 'content', label: '内容生成', agents: ['content_generator'], dependencies: ['diagnostics'] },
        { id: 'review-content', label: '内容审核', agents: ['reviewer'], dependencies: ['content'] },
      ],
    }
    const flow = useFlowStatus(DEF)
    await nextTick()
    const byKey = Object.fromEntries(flow.stages.value.map((s) => [s.key, s]))
    expect(byKey.content.status).toBe('deferred')
    expect(byKey['review-content'].status).toBe('deferred')
  })
})
