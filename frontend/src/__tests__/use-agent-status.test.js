import { describe, it, expect, beforeEach, vi } from 'vitest'

const { mockAssessment } = vi.hoisted(() => {
  const { reactive } = require('vue')
  return {
    mockAssessment: reactive({
      hasResults: false,
      loading: false,
      profile: null,
      assessment: null,
      knowledgeGraph: null,
      learningReport: null,
      generatedContent: null,
      feedbackContent: null,
      reviewResults: null,
      orchestrationLog: [],
      orchestrationEvents: [],
    }),
  }
})

vi.mock('@/stores/assessment', () => ({ useAssessmentStore: () => mockAssessment }))

const { useAgentStatus } = await import('@/composables/useAgentStatus')

function nodeMap() {
  return Object.fromEntries(useAgentStatus().agentNodes.value.map((node) => [node.key, node]))
}

describe('useAgentStatus 资源阶段状态', () => {
  beforeEach(() => {
    mockAssessment.hasResults = true
    mockAssessment.loading = false
    mockAssessment.profile = { theory_level: 2, practical_level: 1, weak_topics: [] }
    mockAssessment.assessment = { correct_count: 6, total_count: 10 }
    mockAssessment.knowledgeGraph = { learning_path: [{ node_id: 'PY-001' }] }
    mockAssessment.learningReport = null
    mockAssessment.generatedContent = null
    mockAssessment.feedbackContent = null
    mockAssessment.reviewResults = null
    mockAssessment.orchestrationLog = ['[10:00] ✅ 学情检测 完成']
    mockAssessment.orchestrationEvents = []
  })

  it('诊断与图谱就绪、资源未生成时将资源阶段标为延后启动', () => {
    const nodes = nodeMap()

    expect(nodes.content_generator).toMatchObject({
      status: 'deferred',
      activationHint: '生成学习资源后启动',
    })
    expect(nodes.reviewer).toMatchObject({
      status: 'deferred',
      activationHint: '生成学习资源后启动',
    })
  })

  it('已有学习资源时内容生成完成，审核不再被标为延后启动', () => {
    mockAssessment.generatedContent = { resources: [{ title: '资源' }] }
    const nodes = nodeMap()

    expect(nodes.content_generator.status).toBe('done')
    expect(nodes.reviewer.status).toBe('idle')
  })
})
