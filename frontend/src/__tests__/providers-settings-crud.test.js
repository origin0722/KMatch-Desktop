import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import ProvidersSettings from '@/ide/settings/ProvidersSettings.vue'
import { useCustomProvidersStore } from '@/stores/customProviders'

// ElMessageBox.confirm 在 jsdom 下挂起 (无真实点击), mock 成 resolve
// 仅覆写 confirm, 保留 default 插件 + 全部组件 + 其他命名导出 (同 assistant-settings.test.js)
vi.mock('element-plus', async (importOriginal) => {
  const orig = await importOriginal()
  return {
    ...orig,
    ElMessageBox: { ...orig.ElMessageBox, confirm: vi.fn(() => Promise.resolve()) },
  }
})

describe('ProvidersSettings CRUD', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    globalThis.window = globalThis.window || {}
    window.api = window.api || {}
    window.api.http = { request: vi.fn() }
  })

  const mountOpts = () => ({ global: { plugins: [ElementPlus], stubs: ['el-icon'] } })

  it('renders list of custom providers', async () => {
    const cps = useCustomProvidersStore()
    cps.add({ name: 'OpenRouter', baseUrl: 'https://openrouter.ai/v1', apiKey: 'k', models: ['m1'] })
    const w = mount(ProvidersSettings, mountOpts())
    await flushPromises()
    expect(w.text()).toContain('OpenRouter')
    expect(w.findAll('.cp-item')).toHaveLength(1)
  })

  it('delete button removes provider', async () => {
    const cps = useCustomProvidersStore()
    cps.add({ name: 'X', baseUrl: 'u' })
    const w = mount(ProvidersSettings, mountOpts())
    await flushPromises()
    await w.find('[data-test="cp-delete"]').trigger('click')
    await flushPromises() // 等 removeProvider 内 await confirm(resolve) -> cps.remove
    expect(cps.list).toHaveLength(0)
  })

  it('new provider button opens dialog', async () => {
    const w = mount(ProvidersSettings, mountOpts())
    await w.find('[data-test="cp-new"]').trigger('click')
    expect(w.findComponent({ name: 'ProviderEditDialog' }).exists()).toBe(true)
  })
})
