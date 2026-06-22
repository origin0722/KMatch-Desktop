import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/stores/assessment', () => ({
  useAssessmentStore: () => ({
    hasResults: false, loading: false, phase: 'idle', orchestrationLog: [],
    profile: null, knowledgeGraph: null,
  }),
}))

// MarkdownViewer 经由 monaco-editor, 在 jsdom 下无法解析包入口, 故 stub
vi.mock('@/components/MarkdownViewer.vue', () => ({ default: { props: ['content'], template: '<div>{{ content }}</div>' } }))

const LearningSession = (await import('@/views/LearningSession.vue')).default

// SplitPane 是右半分屏 (非本视图测试重点), 经 KnowledgeGraph/Dashboard 拉 @antv/g6 + echarts, stub 掉隔离
const STUBS = ['el-button','el-form','el-form-item','el-input','el-select','el-option','el-tag','el-descriptions','el-descriptions-item','el-card','el-radio-group','el-radio','el-divider','SplitPane']
// StageQuiz 用 v-loading 指令, jsdom 下需注册空指令
const GLOBAL = { stubs: STUBS, directives: { loading: {} } }

describe('LearningSession', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('渲染阶段卡 + 进度连线 (无结果时 3 卡, rail 4 节点)', () => {
    const w = mount(LearningSession, { global: { plugins: [createPinia()], ...GLOBAL } })
    expect(w.find('.session-flow').exists()).toBe(true)
    expect(w.findAll('.stage-card').length).toBe(3) // goal/quiz/agent (graph v-if hasResults)
    expect(w.find('.progress-rail').exists()).toBe(true)
    expect(w.findAll('.rail-node').length).toBe(4) // rail always shows all 4 stages
  })

  it('默认 activeStage=goal 时 StageGoal 可见且标记 active', () => {
    const w = mount(LearningSession, { global: { plugins: [createPinia()], ...GLOBAL } })
    expect(w.find('.stage-goal.active').exists()).toBe(true)
  })
})
