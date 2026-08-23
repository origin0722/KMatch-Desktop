import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import ProvidersSettings from '@/ide/settings/WebSearchSettings.vue'
import { useAiSettingsStore } from '@/stores/aiSettings'

describe('proxy settings', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    globalThis.window = globalThis.window || {}
    window.api = window.api || {}
    window.api.http = { request: vi.fn() }
    window.api.setProxyConfig = vi.fn()
  })

  // el-switch / el-input 的 @change 是组件事件, 需 .vm.$emit 触发。
  // v2 的 find(css) 返 DOMWrapper 无 .vm (同 assistant-settings 调整),
  // 改用 findAllComponents({name}) + attributes('data-test') 过滤取 VueWrapper。
  const mountOpts = () => ({ global: { plugins: [ElementPlus], stubs: ['el-icon'] } })

  it('toggling proxy enabled calls setProxy', async () => {
    const ai = useAiSettingsStore()
    const w = mount(ProvidersSettings, mountOpts())
    await flushPromises()
    const sw = w.findAllComponents({ name: 'ElSwitch' })
      .find((c) => c.attributes('data-test') === 'proxy-enabled')
    await sw.vm.$emit('change', true)
    expect(ai.proxy.enabled).toBe(true)
  })

  it('url input calls setProxy', async () => {
    const ai = useAiSettingsStore()
    ai.setProxy({ enabled: true })
    const w = mount(ProvidersSettings, mountOpts())
    await flushPromises()
    const urlInput = w.findAllComponents({ name: 'ElInput' })
      // el-input inheritAttrs:false, data-test 转发到内部 <input> 而非根 div,
      // 故在组件树内查 input[data-test="proxy-url"] 定位对应 ElInput
      .find((c) => c.find('input[data-test="proxy-url"]').exists())
    await urlInput.vm.$emit('change', 'http://127.0.0.1:7890')
    expect(ai.proxy.url).toBe('http://127.0.0.1:7890')
  })

  it('Tavily 测试连接调用 /api/search/verify 并展示结果', async () => {
    window.api.http.request.mockResolvedValueOnce({ ok: true, body: { ok: true, hits: 2 } })
    const w = mount(ProvidersSettings, mountOpts())
    await flushPromises()
    const input = w.findAllComponents({ name: 'ElInput' })
      .find((c) => c.find('input[data-test="tavily-key"]').exists())
    await input.setValue('tvly-test')
    const btn = w.findAll('button').find((b) => b.text().includes('测试连接'))
    expect(btn).toBeTruthy()
    await btn.trigger('click')
    await flushPromises()
    expect(window.api.http.request).toHaveBeenCalledWith('POST', '/api/search/verify', { tavily_key: 'tvly-test' })
    expect(w.text()).toContain('连接成功')
  })
})
