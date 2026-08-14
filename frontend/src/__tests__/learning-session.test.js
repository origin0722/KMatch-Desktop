/**
 * 场景：LearningSession 视图——三合一学习会话流挂载（阶段9）。
 *
 * LearningSession 把 Assessment + AgentView + 知识图谱合并成纵向会话流，Agent 推动 4 阶段卡
 * （目标→答题→协同→图谱）。这里 mock assessment store，验视图能挂载并按 activeStage 渲染对应阶段。
 * MarkdownViewer 经由 monaco-editor，jsdom 下无法解析包入口，故 stub。
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'

// #30: mock 用 reactive 持有可变 phase, 验证 "答题完成 → showCollab 点亮" 的会话层联动
const { mockAssessment } = vi.hoisted(() => {
  const { reactive } = require('vue')
  return {
    mockAssessment: reactive({
      hasResults: false, loading: false, phase: 'idle', orchestrationLog: [],
      profile: null, knowledgeGraph: null, feedbackStrategy: null,
    }),
  }
})

vi.mock('@/stores/assessment', () => ({
  useAssessmentStore: () => mockAssessment,
}))

// MarkdownViewer 经由 monaco-editor, 在 jsdom 下无法解析包入口, 故 stub
vi.mock('@/components/MarkdownViewer.vue', () => ({ default: { props: ['content'], template: '<div>{{ content }}</div>' } }))

const LearningSession = (await import('@/views/LearningSession.vue')).default
const { useSessionStore } = await import('@/stores/session')

// SplitPane 是右半分屏 (非本视图测试重点), 经 KnowledgeGraph/Dashboard 拉 @antv/g6 + echarts, stub 掉隔离;
// ProfileRadar 走 echarts canvas, jsdom 无 canvas 会崩 — 同样 stub
const STUBS = ['el-button','el-form','el-form-item','el-input','el-select','el-option','el-tag','el-descriptions','el-descriptions-item','el-card','el-collapse','el-collapse-item','el-radio-group','el-radio','el-divider','SplitPane','ProfileRadar']
// StageQuiz 用 v-loading 指令, jsdom 下需注册空指令
const GLOBAL = { stubs: STUBS, directives: { loading: {} } }

describe('LearningSession', () => {
  let pinia
  beforeEach(() => {
    pinia = createPinia()
    setActivePinia(pinia)
    mockAssessment.hasResults = false
    mockAssessment.loading = false
    mockAssessment.phase = 'idle'
    mockAssessment.orchestrationLog = []
    mockAssessment.feedbackStrategy = null
  })

  it('渲染阶段卡 + 进度连线 (无结果时 3 卡 3 节点, 轨卡同步)', () => {
    const w = mount(LearningSession, { global: { plugins: [pinia], ...GLOBAL } })
    expect(w.find('.session-flow').exists()).toBe(true)
    expect(w.findAll('.stage-card').length).toBe(3) // goal/quiz/agent (graph v-if hasResults)
    expect(w.find('.stages-grid').exists()).toBe(true)
    expect(w.findAll('.rail-node').length).toBe(3) // 轨卡同步: graph 无结果时节点不显示, 避免错位
  })

  it('默认 activeStage=goal 时 StageGoal 可见且标记 active', () => {
    const w = mount(LearningSession, { global: { plugins: [pinia], ...GLOBAL } })
    expect(w.find('.stage-goal.active').exists()).toBe(true)
  })

  it('#30 答题完成 (phase→feedback) 自动点亮 AI 协同入口', async () => {
    const session = useSessionStore()
    const w = mount(LearningSession, { global: { plugins: [pinia], ...GLOBAL } })
    expect(session.showCollab).toBe(false)
    mockAssessment.phase = 'feedback'
    await nextTick()
    expect(session.showCollab).toBe(true)
  })
  it('loading 文案按 phase 区分: 出题/判分/取反馈不混用 (修"没答题就说生成学习内容")', async () => {
    // 出题中 (idle): 应说"定制题目", 不应出现反馈阶段的"针对性学习内容"
    mockAssessment.loading = true; mockAssessment.phase = 'idle'
    let w = mount(LearningSession, { global: { plugins: [pinia], ...GLOBAL } })
    let txt = w.find('.quiz-loading').attributes('element-loading-text')
    expect(txt).toContain('定制题目')
    expect(txt).not.toContain('针对性学习内容')
    w.unmount()
    // 判分中 (answering): 遮罩不再消失 (修阶段②白屏)
    mockAssessment.phase = 'answering'
    w = mount(LearningSession, { global: { plugins: [pinia], ...GLOBAL } })
    expect(w.find('.quiz-loading').attributes('element-loading-text')).toContain('判分')
    w.unmount()
    // 取反馈 (feedback): 原文案保留
    mockAssessment.phase = 'feedback'
    w = mount(LearningSession, { global: { plugins: [pinia], ...GLOBAL } })
    expect(w.find('.quiz-loading').attributes('element-loading-text')).toContain('针对性学习内容')
    w.unmount()
  })
})
