/**
 * RunsPanel — 后台任务页 (P1 耐久 run + 协同事件复用) 单测。
 * mock '@/api/diagnostics' 的 fetchRuns/fetchRun 与 '@/stores/assessment',
 * sidebar store 用真实(pinia) 以验证 setView 导航。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'

const mocks = vi.hoisted(() => ({
  fetchRuns: vi.fn(),
  fetchRun: vi.fn(),
  store: {
    startAssessment: vi.fn(),
    startDemoStream: vi.fn(),
    loadRun: vi.fn(async () => ({})),
    resumeRunDemo: vi.fn(async () => true),
  },
}))
vi.mock('@/api/diagnostics', () => ({ fetchRuns: mocks.fetchRuns, fetchRun: mocks.fetchRun }))
vi.mock('@/stores/assessment', () => ({ useAssessmentStore: () => mocks.store }))

const RunsPanel = (await import('@/ide/RunsPanel.vue')).default
const SAMPLE = {
  session_id: 'demo-1', mode: 'demo', created_at: '2026-08-18T08:00:00Z',
  request: { target_direction: 'Python 入门', scene: 'no_project' },
  summary: { review_passed: true, review_rounds: 2 },
}
const SAMPLE2 = {
  session_id: 'inter-1', mode: 'interactive', created_at: '2026-08-18T09:00:00Z',
  request: { target_direction: '数据分析', scene: 'no_project' },
  summary: { correct_count: 7, total_count: 10, strategy: 'remediate', theory_level: 3, path_nodes: 12, profile_diff: { summary: {} } },
}
const EVENTS = [
  { type: 'agent-end', agent: 'diagnostics', status: 'done', message: '判分完成' },
  { type: 'agent-end', agent: 'reviewer', status: 'failed', message: '打回' },
]

describe('RunsPanel 后台任务页', () => {
  let pinia
  beforeEach(() => {
    pinia = createPinia()
    setActivePinia(pinia)
    vi.clearAllMocks()
    mocks.fetchRuns.mockResolvedValue({ count: 2, runs: [SAMPLE, SAMPLE2] })
    mocks.fetchRun.mockImplementation(async (sid) => ({
      ...(sid === 'inter-1' ? SAMPLE2 : SAMPLE),
      orchestration_events: EVENTS,
    }))
  })

  it('渲染运行列表 (模式/目标/统计 chips/画像变化标记)', async () => {
    const w = mount(RunsPanel, { global: { plugins: [pinia, ElementPlus] } })
    await flushPromises()
    expect(mocks.fetchRuns).toHaveBeenCalledWith(30)
    const rows = w.findAll('.rp-row')
    expect(rows).toHaveLength(2)
    expect(w.text()).toContain('演示测评')
    expect(w.text()).toContain('自定义测评')
    expect(w.text()).toContain('Python 入门')
    expect(w.text()).toContain('7/10 正确')
    expect(w.text()).toContain('策略 remediate')
    expect(w.text()).toContain('📈 画像变化')
  })

  it('点击行 → 展开事件时间线 (Agent 状态/消息)', async () => {
    const w = mount(RunsPanel, { global: { plugins: [pinia, ElementPlus] } })
    await flushPromises()
    const demoRow = w.findAll('.rp-row').find((r) => r.text().includes('演示测评'))
    await demoRow.trigger('click')
    await flushPromises()
    expect(mocks.fetchRun).toHaveBeenCalledWith('demo-1')
    const evs = w.findAll('.rp-event')
    expect(evs.length).toBe(2)
    expect(w.text()).toContain('diagnostics')
    expect(w.text()).toContain('打回')
  })

  it('demo run → 按此重跑 (loadRun + resumeRunDemo + 切学习会话)', async () => {
    const { useSidebarStore } = await import('@/stores/sidebar')
    const w = mount(RunsPanel, { global: { plugins: [pinia, ElementPlus] } })
    await flushPromises()
    const demoRow = w.findAll('.rp-row').find((r) => r.text().includes('演示测评'))
    await demoRow.trigger('click')
    await flushPromises()
    const rerun = w.findAll('.rp-run-actions button').find((b) => b.text().includes('按此重跑'))
    expect(rerun).toBeTruthy()
    await rerun.trigger('click')
    await flushPromises()
    expect(mocks.store.loadRun).toHaveBeenCalledWith('demo-1')
    expect(mocks.store.resumeRunDemo).toHaveBeenCalled()
    expect(useSidebarStore().activeView).toBe('learning-session')
  })

  it('交互 run → 重新测评该目标 (startAssessment + 切学习会话)', async () => {
    const { useSidebarStore } = await import('@/stores/sidebar')
    const w = mount(RunsPanel, { global: { plugins: [pinia, ElementPlus] } })
    await flushPromises()
    const interRow = w.findAll('.rp-row').find((r) => r.text().includes('自定义测评'))
    await interRow.trigger('click')
    await flushPromises()
    const retake = w.findAll('.rp-run-actions button').find((b) => b.text().includes('重新测评该目标'))
    expect(retake).toBeTruthy()
    await retake.trigger('click')
    expect(mocks.store.startAssessment).toHaveBeenCalledWith({ targetDirection: '数据分析' })
    expect(useSidebarStore().activeView).toBe('learning-session')
  })

  it('fetchRuns 失败 → 错误提示', async () => {
    mocks.fetchRuns.mockRejectedValue(new Error('网络失败'))
    const w = mount(RunsPanel, { global: { plugins: [pinia, ElementPlus] } })
    await flushPromises()
    expect(w.text()).toContain('网络失败')
  })
})
