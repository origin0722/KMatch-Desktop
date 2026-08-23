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

  it('renders four section titles + four anchors (AI 助手/学习引擎/联网搜索/通用)', () => {
    const w = mount(SettingsView, { global: { stubs: ['AssistantSettings', 'AgentSettings', 'ProvidersSettings', 'WebSearchSettings', 'ApiSettings'] } })
    const text = w.text()
    expect(text).toContain('AI 助手')
    expect(text).toContain('学习引擎')
    expect(text).toContain('联网搜索')
    expect(text).toContain('通用')
    expect(w.findAll('.settings-anchor')).toHaveLength(4)
  })

  it('clicking re-onboard button activates onboarding via sidebar store', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const w = mount(SettingsView, { global: { plugins: [pinia], stubs: ['AssistantSettings', 'AgentSettings', 'ProvidersSettings', 'WebSearchSettings', 'ApiSettings', 'el-button'] } })
    const sidebar = useSidebarStore()
    expect(sidebar.onboardingActive).toBe(false)
    await w.find('[data-test="re-onboard"]').trigger('click')
    expect(sidebar.onboardingActive).toBe(true)
  })

  it('clicking anchor sets active anchor', async () => {
    const w = mount(SettingsView, { global: { stubs: ['AssistantSettings', 'AgentSettings', 'ProvidersSettings', 'WebSearchSettings', 'ApiSettings'] } })
    // 按 label 定位, 而非固定下标 (避免新增栏目时下标漂移)
    const anchor = w.findAll('.settings-anchor').find((a) => a.text().includes('学习引擎'))
    await anchor.trigger('click')
    expect(w.vm.activeAnchor).toBe('sec-agent')
  })
})
