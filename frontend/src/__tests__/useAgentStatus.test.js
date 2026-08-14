/**
 * useAgentStatus - 产出概览 / 实时动作 / 完成计数 (StageAgent 粗糙->详细改造)
 *
 * 验证 productions 从 store 实际产出取数 (非"待命"即给真实数字),
 * currentAction 运行中取最后日志, completedCount/pendingCount 计数正确。
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'

const { mockAssessment } = vi.hoisted(() => {
  const { reactive } = require('vue')
  return {
    mockAssessment: reactive({
      hasResults: false, loading: false, phase: 'idle',
      orchestrationLog: [], profile: null, assessment: null,
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
    orchestrationLog: [], profile: null, assessment: null,
    knowledgeGraph: null, generatedContent: null, feedbackContent: null,
    reviewResults: null,
  })
}

describe('useAgentStatus 产出概览', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    reset()
  })

  it('productions.diagnostics: 判分 + 画像维度 + 薄弱点数', async () => {
    mockAssessment.assessment = { correct_count: 7, total_count: 10 }
    mockAssessment.profile = { theory_level: 3, practical_level: 2, weak_topics: [{ node_id: 'X' }, { node_id: 'Y' }] }
    const { productions } = useAgentStatus()
    await nextTick()
    expect(productions.value.diagnostics).toBe('判分 7/10 · 理论 L3/实操 L2 · 薄弱 2 点')
  })

  it('productions.graph_controller: 节点数 + 预估时长', async () => {
    mockAssessment.knowledgeGraph = { learning_path: new Array(12), estimated_total_hours: 4.2 }
    const { productions } = useAgentStatus()
    await nextTick()
    expect(productions.value.graph_controller).toBe('12 节点学习路径 · 预估 4.2h')
  })

  it('productions.content_generator: 优先 generatedContent, 回落 feedbackContent', async () => {
    mockAssessment.generatedContent = { resources: new Array(6), node_count: 2 }
    const { productions } = useAgentStatus()
    await nextTick()
    expect(productions.value.content_generator).toBe('已生成 6 段资源 · 覆盖 2 节点')

    // generatedContent 缺失 -> 回落到针对性反馈
    mockAssessment.generatedContent = null
    mockAssessment.feedbackContent = { strategy: 'scaffold', resources: new Array(2) }
    await nextTick()
    expect(productions.value.content_generator).toBe('针对性反馈 · scaffold 策略 · 2 段')
  })

  it('productions.reviewer: 通过/打回 + 评分', async () => {
    mockAssessment.reviewResults = { passed: true, overall_score: 88 }
    const { productions } = useAgentStatus()
    await nextTick()
    expect(productions.value.reviewer).toBe('通过 · 评分 88')
  })

  it('productions: 无产出时回落 undefined (组件用 role 描述)', async () => {
    const { productions } = useAgentStatus()
    await nextTick()
    expect(productions.value.content_generator).toBeUndefined()
    expect(productions.value.reviewer).toBeUndefined()
  })

  it('currentAction: 运行中(loading)取最后一条日志的 agent + 去时间戳/emoji', async () => {
    mockAssessment.loading = true
    mockAssessment.orchestrationLog = ['[10:00] 📚 领域知识生成 开始']
    const { currentAction, pipelineRunning } = useAgentStatus()
    await nextTick()
    expect(pipelineRunning.value).toBe(true)
    expect(currentAction.value.label).toBe('内容生成')
    expect(currentAction.value.action).toBe('领域知识生成 开始')
  })

  it('currentAction: loading 结束后为 null (即使日志末尾无"流程结束")', async () => {
    // interactive submit 无"流程结束"标记, 但 loading=false -> 不应误判运行中
    mockAssessment.loading = false
    mockAssessment.orchestrationLog = ['[10:00] ✅ 路径组装完成: 12 节点']
    const { currentAction, pipelineRunning } = useAgentStatus()
    await nextTick()
    expect(pipelineRunning.value).toBe(false)
    expect(currentAction.value).toBeNull()
  })

  it('completedCount/pendingCount: 日志推导 agent 状态计数', async () => {
    mockAssessment.orchestrationLog = [
      '[10:00] 🔧 学情检测 开始',
      '[10:01] ✅ 学情检测 完成',
      '[10:02] 🗺️ 知识图谱组装 开始',
      '[10:03] ✅ 知识图谱 路径组装完成',
    ]
    const { completedCount, pendingCount } = useAgentStatus()
    await nextTick()
    // diagnostics + graph_controller 完成; orchestrator/reviewer/content_generator 待触发
    expect(completedCount.value).toBe(2)
    expect(pendingCount.value).toBe(3)
  })

  it('interactive 场景: 产出覆盖日志推导 (修状态 bug 的核心)', async () => {
    // 复现用户反馈的 bug: interactive submit 日志措辞(判分/路径组装完成)不匹配 demo 的开始/完成正则,
    // 单靠日志推导会判 0 完成、图谱管控卡 running。修复=产出覆盖: 有产出即 done。
    mockAssessment.loading = false
    mockAssessment.hasResults = true // profile 已设 -> 真实 store hasResults=true
    mockAssessment.orchestrationLog = [
      '[10:00] 🔧 学情检测: 判分 0/10',
      '[10:00] 📋 画像构建: theory_level=1 weak=7 known=0',
      '[10:00] 🗺️ 知识图谱管控: 开始组装学习路径',
      '📥 画像输入: known=0 weak=7 level=1 max_nodes=12',
      '✅ 路径组装完成: 12 个节点，预估 4.6h，状态更新 8/8',
    ]
    mockAssessment.assessment = { correct_count: 0, total_count: 10 }
    mockAssessment.profile = { theory_level: 1, practical_level: 1, weak_topics: [{ node_id: 'DA-001' }] }
    mockAssessment.knowledgeGraph = { learning_path: new Array(12), estimated_total_hours: 4.6 }
    const { agentNodes, completedCount, pendingCount, pipelineRunning } = useAgentStatus()
    await nextTick()
    // pipelineRunning=false (loading=false) -> 不再误显示运行中
    expect(pipelineRunning.value).toBe(false)
    // orchestrator + diagnostics + graph_controller 完成 (产出覆盖); content_generator/reviewer 待触发
    expect(completedCount.value).toBe(3)
    expect(pendingCount.value).toBe(2)
    const byKey = Object.fromEntries(agentNodes.value.map((a) => [a.key, a.status]))
    expect(byKey.diagnostics).toBe('done')
    expect(byKey.graph_controller).toBe('done')
    expect(byKey.orchestrator).toBe('done')
    expect(byKey.content_generator).toBe('idle')
    expect(byKey.reviewer).toBe('idle')
  })
})
