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
  deleteRun: vi.fn(async () => ({ deleted: true })),
  store: {
    startAssessment: vi.fn(),
    startDemoStream: vi.fn(),
    loadRun: vi.fn(async () => ({})),
    resumeRunDemo: vi.fn(async () => true),
  },
}))
vi.mock('@/api/diagnostics', () => ({ fetchRuns: mocks.fetchRuns, fetchRun: mocks.fetchRun, deleteRun: mocks.deleteRun }))
vi.mock('@/stores/assessment', () => ({ useAssessmentStore: () => mocks.store }))
// ElMessageBox.confirm 在 jsdom 下挂起, mock 成 resolve
vi.mock('element-plus', async (importOriginal) => {
  const orig = await importOriginal()
  return {
    ...orig,
    ElMessageBox: { ...orig.ElMessageBox, confirm: vi.fn(() => Promise.resolve()) },
  }
})

const RunsPanel = (await import('@/ide/RunsPanel.vue')).default
const SAMPLE = {
  session_id: 'demo-1', mode: 'demo', created_at: '2026-08-18T08:00:00Z',
  display_title: '学习 · Python 入门', scene: 'no_project', scene_label: '无项目技能学习',
  target_direction: 'Python 入门', project_name: null, status: 'completed',
  summary: { review_passed: true, review_rounds: 2 },
}
const SAMPLE2 = {
  session_id: 'inter-1', mode: 'interactive', created_at: '2026-08-18T09:00:00Z',
  display_title: '学习 · 数据分析', scene: 'no_project', scene_label: '无项目技能学习',
  target_direction: '数据分析', project_name: null, status: 'completed',
  summary: {
    correct_count: 7, total_count: 10, strategy: 'remediate', theory_level: 3, path_nodes: 12,
    profile_diff: { summary: {} },
    weak_topics: ['缺失值处理', 'SQL 连接'],
    pacing: { total_hours: 5.2, hours_per_week: 6, weeks: 1 },
  },
}
const DETAIL_SAMPLE = { ...SAMPLE, request: { target_direction: 'Python 入门', scene: 'no_project' } }
const DETAIL_SAMPLE2 = { ...SAMPLE2, request: { target_direction: '数据分析', scene: 'no_project' } }
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
      ...(sid === 'inter-1' ? DETAIL_SAMPLE2 : DETAIL_SAMPLE),
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
    // issue-66: 场景标签 + 薄弱点 chips
    expect(w.text()).toContain('无项目技能学习')
    expect(w.text()).toContain('薄弱 缺失值处理')
    expect(w.text()).toContain('薄弱 SQL 连接')
  })

  it('issue-66/69: with_project 场景标签 + 详情 pacing/薄弱点摘要', async () => {
    const PROJ = {
      session_id: 'p-1', mode: 'demo', created_at: '2026-08-18T10:00:00Z',
      display_title: 'shop-service · 项目质量流水线', scene: 'with_project', scene_label: '有项目二次开发',
      target_direction: 'Web 后端', project_name: 'shop-service', status: 'completed',
      summary: { weak_topics: ['装饰器'], pacing: { total_hours: 3.2, hours_per_week: 6, weeks: 1 } },
    }
    mocks.fetchRuns.mockResolvedValue({ count: 1, runs: [PROJ] })
    mocks.fetchRun.mockResolvedValue({ ...PROJ, request: { target_direction: 'Web 后端', scene: 'with_project' }, orchestration_events: [] })
    const w = mount(RunsPanel, { global: { plugins: [pinia, ElementPlus] } })
    await flushPromises()
    expect(w.text()).toContain('有项目二次开发')
    await w.find('.rp-row').trigger('click')
    await flushPromises()
    const txt = w.text()
    expect(txt).toContain('约 1 周 · 共 3.2h')
    expect(txt).toContain('薄弱点: 装饰器')
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

  it('issue-83: 删除按钮 → 确认后 deleteRun 并移除该行', async () => {
    const w = mount(RunsPanel, { global: { plugins: [pinia, ElementPlus] } })
    await flushPromises()
    expect(mocks.deleteRun).not.toHaveBeenCalled()
    // 按目标定位行 (列表按时间倒序, 不假设首行)
    const row = w.findAll('.rp-row').find((r) => r.text().includes('Python 入门'))
    await row.find('[data-test="run-delete"]').trigger('click')
    await flushPromises()
    expect(mocks.deleteRun).toHaveBeenCalledWith('demo-1')
    expect(w.text()).not.toContain('Python 入门')
  })
})
