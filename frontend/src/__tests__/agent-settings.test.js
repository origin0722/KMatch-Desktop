import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import AgentSettings from '@/ide/settings/AgentSettings.vue'
import { useAgentLlmStore } from '@/stores/agentLlm'

describe('AgentSettings', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    globalThis.window = globalThis.window || {}
    window.api = window.api || {}
    window.api.http = { request: vi.fn() }
  })

  const mountOpts = () => ({ global: { plugins: [ElementPlus], stubs: ['el-icon'] } })

  it('hides config when useOverrides off', () => {
    const w = mount(AgentSettings, mountOpts())
    expect(w.find('[data-test="agent-provider"]').exists()).toBe(false)
  })

  it('shows config when useOverrides on', async () => {
    const agent = useAgentLlmStore()
    agent.setUseOverrides(true)
    const w = mount(AgentSettings, mountOpts())
    expect(w.find('[data-test="agent-provider"]').exists()).toBe(true)
  })

  it('anthropic provider option is disabled', async () => {
    const agent = useAgentLlmStore()
    agent.setUseOverrides(true)
    const w = mount(AgentSettings, mountOpts())
    // Agent 本期仅 OpenAI 协议, anthropic option disabled
    const options = w.findAllComponents({ name: 'ElOption' })
    const anthropic = options.find((o) => o.props('value') === 'anthropic')
    expect(anthropic?.props('disabled')).toBe(true)
  })

  it('test connection calls /api/agents/ping with overrides', async () => {
    const agent = useAgentLlmStore()
    agent.setUseOverrides(true)
    agent.setApiKey('sk-x')
    agent.setProvider('deepseek')
    agent.setModel('m')
    window.api.http.request.mockResolvedValueOnce({ ok: true, status: 200, body: { ok: true, content: 'pong' } })
    const w = mount(AgentSettings, mountOpts())
    await w.find('[data-test="test-conn"]').trigger('click')
    await flushPromises()
    expect(window.api.http.request).toHaveBeenCalledWith('POST', '/api/agents/ping',
      expect.objectContaining({ llm_overrides: expect.objectContaining({ api_key: 'sk-x' }) }))
  })
})
