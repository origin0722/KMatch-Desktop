import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import SettingsView from '@/ide/settings/SettingsView.vue'
import { useSidebarStore } from '@/stores/sidebar'

describe('SettingsView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    globalThis.window = globalThis.window || {}
    window.api = window.api || {}
  })

  it('renders five section titles + five anchors (含 API 设置)', () => {
    const w = mount(SettingsView, { global: { stubs: ['AssistantSettings', 'AgentSettings', 'ProvidersSettings', 'ApiSettings'] } })
    const text = w.text()
    expect(text).toContain('API 设置')
    expect(text).toContain('AI 助手')
    expect(text).toContain('Agent 学习引擎')
    expect(text).toContain('供应商管理')
    expect(text).toContain('通用')
    expect(w.findAll('.settings-anchor')).toHaveLength(5)
  })

  it('clicking re-onboard button activates onboarding via sidebar store', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const w = mount(SettingsView, { global: { plugins: [pinia], stubs: ['AssistantSettings', 'AgentSettings', 'ProvidersSettings', 'ApiSettings', 'el-button'] } })
    const sidebar = useSidebarStore()
    expect(sidebar.onboardingActive).toBe(false)
    await w.find('[data-test="re-onboard"]').trigger('click')
    expect(sidebar.onboardingActive).toBe(true)
  })

  it('clicking anchor sets active anchor', async () => {
    const w = mount(SettingsView, { global: { stubs: ['AssistantSettings', 'AgentSettings', 'ProvidersSettings', 'ApiSettings'] } })
    // 按 label 定位, 而非固定下标 (避免新增栏目时下标漂移)
    const anchor = w.findAll('.settings-anchor').find((a) => a.text().includes('Agent 学习引擎'))
    await anchor.trigger('click')
    expect(w.vm.activeAnchor).toBe('sec-agent')
  })
})
