/**
 * 场景：session store——学习会话阶段派生与分屏白名单（阶段9）。
 *
 * session 只拥 splitView；activeStage 是 assessment 的纯 computed（优先级 graph>agent>quiz>goal），
 * 不另存以避免双源真相。这里 mock assessment 为 reactive 对象，翻转其 hasResults/loading/phase/
 * orchestrationLog 字段，验证 activeStage 各分支与优先级、splitView 白名单校验。
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { reactive } from 'vue'

// mock assessment store (session.activeStage 派生自它)
// 用 reactive 持有可变状态, 让每个测试能翻转字段验证各分支与优先级
const mockAssessment = reactive({
  hasResults: false,
  loading: false,
  phase: 'idle',
  orchestrationLog: [],
})
vi.mock('@/stores/assessment', () => ({
  useAssessmentStore: () => mockAssessment,
}))

const { useSessionStore } = await import('@/stores/session')

describe('session store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockAssessment.hasResults = false
    mockAssessment.loading = false
    mockAssessment.phase = 'idle'
    mockAssessment.orchestrationLog = []
  })

  it('activeStage=goal 当无结果无日志无 loading', () => {
    const s = useSessionStore()
    expect(s.activeStage).toBe('goal')
  })

  it('splitView 默认 null, setSplitView/closeSplit 控制', () => {
    const s = useSessionStore()
    expect(s.splitView).toBeNull()
    s.setSplitView('graph')
    expect(s.splitView).toBe('graph')
    s.closeSplit()
    expect(s.splitView).toBeNull()
  })

  it('#30 showCollab: 默认 false, phase=feedback 自动点亮, 可手动收起', () => {
    const s = useSessionStore()
    expect(s.showCollab).toBe(false)
    mockAssessment.phase = 'feedback'
    expect(s.showCollab).toBe(true)   // flush: 'sync' → 同步点亮
    s.setShowCollab(false)            // 手动收起
    expect(s.showCollab).toBe(false)
  })

  it('#30 showCollab: phase 回 idle (重新测评) 复位', () => {
    const s = useSessionStore()
    mockAssessment.phase = 'feedback'
    expect(s.showCollab).toBe(true)
    mockAssessment.phase = 'idle'
    expect(s.showCollab).toBe(false)
  })

  it('setSplitView 拒绝非法视图名', () => {
    const s = useSessionStore()
    s.setSplitView('code')
    expect(s.splitView).toBeNull() // code 不在允许列表
  })

  // ---- activeStage 分支覆盖 ----

  it('activeStage=graph 当 hasResults=true', () => {
    mockAssessment.hasResults = true
    const s = useSessionStore()
    expect(s.activeStage).toBe('graph')
  })

  it('activeStage=agent 当 loading 且 orchestrationLog 非空', () => {
    mockAssessment.loading = true
    mockAssessment.orchestrationLog = [{ msg: 'demo SSE 流' }]
    const s = useSessionStore()
    expect(s.activeStage).toBe('agent')
  })

  it('activeStage=quiz 当 phase=answering', () => {
    mockAssessment.phase = 'answering'
    const s = useSessionStore()
    expect(s.activeStage).toBe('quiz')
  })

  it('activeStage=quiz 当 phase=feedback', () => {
    mockAssessment.phase = 'feedback'
    const s = useSessionStore()
    expect(s.activeStage).toBe('quiz')
  })

  it('issue-06: phase=feedback 且 hasResults=true 仍在 quiz (不因画像落地过早跳 graph)', () => {
    // interactive 提交答案后 profile 已写入 (hasResults=true), 但用户仍在反馈阶段
    mockAssessment.phase = 'feedback'
    mockAssessment.hasResults = true
    const s = useSessionStore()
    expect(s.activeStage).toBe('quiz')
  })

  it('issue-06: phase=answering 且 hasResults=true 仍在 quiz', () => {
    mockAssessment.phase = 'answering'
    mockAssessment.hasResults = true
    const s = useSessionStore()
    expect(s.activeStage).toBe('quiz')
  })

  // ---- 优先级: graph > agent > quiz > goal ----

  it('优先级: hasResults 胜过 loading (graph > agent)', () => {
    mockAssessment.hasResults = true
    mockAssessment.loading = true
    mockAssessment.orchestrationLog = [{ msg: '协同中' }]
    const s = useSessionStore()
    expect(s.activeStage).toBe('graph')
  })

  it('优先级: loading+log 胜过 phase (agent > quiz)', () => {
    mockAssessment.loading = true
    mockAssessment.orchestrationLog = [{ msg: '协同中' }]
    mockAssessment.phase = 'answering'
    const s = useSessionStore()
    expect(s.activeStage).toBe('agent')
  })

  it('优先级: phase 胜过空态 (quiz > goal)', () => {
    mockAssessment.phase = 'feedback'
    const s = useSessionStore()
    expect(s.activeStage).toBe('quiz')
  })
})
