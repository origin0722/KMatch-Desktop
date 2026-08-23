/**
 * ReadyGate — 启动就绪门 (issue-62) 单测。
 * mock backendHealth store: 就绪 → emit ready; 超时未就绪 → 错误卡片, 可重试/跳过。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

const mock = vi.hoisted(() => {
  const { reactive } = require('vue')
  return reactive({
    backendUp: false,
    graphStore: '',
    neo4jConnected: false,
    lastError: '',
    check: vi.fn(),
    start: vi.fn(),
  })
})
vi.mock('@/stores/backendHealth', () => ({
  useBackendHealthStore: () => mock,
}))

const ReadyGate = (await import('@/ide/ReadyGate.vue')).default

describe('ReadyGate', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mock.backendUp = false
    mock.graphStore = ''
    mock.lastError = ''
    mock.check.mockClear()
    mock.start.mockClear()
  })
  afterEach(() => { vi.useRealTimers() })

  it('后端就绪 → 展示就绪并 emit ready', async () => {
    const w = mount(ReadyGate, { global: { plugins: [ElementPlus] } })
    expect(w.find('[data-test="ready-gate"]').exists()).toBe(true)
    expect(mock.start).toHaveBeenCalled()
    mock.backendUp = true
    await vi.advanceTimersByTimeAsync(700)
    expect(w.emitted('ready')).toBeTruthy()
  })

  it('未就绪 → 错误卡片, 「仍要进入」 emit skip', async () => {
    mock.lastError = '连接失败'
    const w = mount(ReadyGate, { global: { plugins: [ElementPlus] } })
    await vi.advanceTimersByTimeAsync(3500)
    expect(w.find('[data-test="gate-error"]').exists()).toBe(true)
    const skip = w.findAll('button').find((b) => b.text().includes('仍要进入'))
    expect(skip).toBeTruthy()
    await skip.trigger('click')
    expect(w.emitted('skip')).toBeTruthy()
  })
})
