import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import ProvidersSettings from '@/ide/settings/ProvidersSettings.vue'
import { useCustomProvidersStore } from '@/stores/customProviders'

describe('ProvidersSettings vision batch', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    globalThis.window = globalThis.window || {}
    window.api = window.api || {}
    window.api.http = { request: vi.fn(async () => ({ ok: true, status: 200, body: { vision: true } })) }
  })

  const mountOpts = () => ({ global: { plugins: [ElementPlus], stubs: ['el-icon'] } })

  it('batch probe button exists with count', async () => {
    const cps = useCustomProvidersStore()
    cps.add({ name: 'X', baseUrl: 'u', apiKey: 'k', models: ['m1', 'm2'] })
    const w = mount(ProvidersSettings, mountOpts())
    await flushPromises()
    expect(w.find('[data-test="vision-batch"]').exists()).toBe(true)
    expect(w.text()).toContain('2')
  })

  it('clear cache button calls modelVision.clearAll', async () => {
    const w = mount(ProvidersSettings, mountOpts())
    await flushPromises()
    await w.find('[data-test="vision-clear"]').trigger('click')
    await flushPromises()
    // DELETE /api/chat/probe-vision/cache 被调
    expect(window.api.http.request).toHaveBeenCalledWith('DELETE', '/api/chat/probe-vision/cache')
  })
})
