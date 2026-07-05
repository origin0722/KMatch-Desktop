import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import SettingsView from '@/ide/settings/SettingsView.vue'

describe('SettingsView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    globalThis.window = globalThis.window || {}
    window.api = window.api || {}
  })

  it('renders three section titles + three anchors', () => {
    const w = mount(SettingsView, { global: { stubs: ['AssistantSettings', 'AgentSettings', 'ProvidersSettings'] } })
    const text = w.text()
    expect(text).toContain('AI 助手')
    expect(text).toContain('Agent 学习引擎')
    expect(text).toContain('供应商管理')
    expect(w.findAll('.settings-anchor')).toHaveLength(3)
  })

  it('clicking anchor sets active anchor', async () => {
    const w = mount(SettingsView, { global: { stubs: ['AssistantSettings', 'AgentSettings', 'ProvidersSettings'] } })
    await w.findAll('.settings-anchor')[1].trigger('click')
    expect(w.vm.activeAnchor).toBe('sec-agent')
  })
})
