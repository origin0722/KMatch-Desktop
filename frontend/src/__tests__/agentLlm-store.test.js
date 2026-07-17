import { describe, it, expect, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAgentLlmStore, withOverrides } from '@/stores/agentLlm'

describe('agentLlm store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('defaults to useOverrides=false + empty key', () => {
    const s = useAgentLlmStore()
    expect(s.state.useOverrides).toBe(false)
    expect(s.state.apiKey).toBe('')
  })

  it('buildOverrides returns null when disabled', () => {
    const s = useAgentLlmStore()
    s.setUseOverrides(false)
    expect(s.buildOverrides()).toBeNull()
  })

  it('buildOverrides returns null when enabled but no apiKey', () => {
    const s = useAgentLlmStore()
    s.setUseOverrides(true)
    s.setProvider('deepseek')
    s.setModel('deepseek-v4-pro')
    expect(s.buildOverrides()).toBeNull()
  })

  it('buildOverrides returns overrides when enabled + key set', () => {
    const s = useAgentLlmStore()
    s.setUseOverrides(true)
    s.setProvider('deepseek')
    s.setApiKey('sk-x')
    s.setBaseUrl('https://api.deepseek.com/v1')
    s.setModel('deepseek-v4-pro')
    expect(s.buildOverrides()).toEqual({
      api_key: 'sk-x',
      base_url: 'https://api.deepseek.com/v1',
      model: 'deepseek-v4-pro',
      protocol: 'openai',
    })
  })

  it('withOverrides injects llm_overrides when enabled', () => {
    const s = useAgentLlmStore()
    s.setUseOverrides(true)
    s.setApiKey('sk-x')
    s.setProvider('deepseek')
    s.setModel('m')
    const body = withOverrides({ target_direction: 'x' })
    expect(body.llm_overrides).toBeDefined()
    expect(body.target_direction).toBe('x')
  })

  it('withOverrides is no-op when disabled', () => {
    const s = useAgentLlmStore()
    s.setUseOverrides(false)
    const body = withOverrides({ target_direction: 'x' })
    expect(body.llm_overrides).toBeUndefined()
  })

  it('persists across store instances', () => {
    const s = useAgentLlmStore()
    s.setUseOverrides(true)
    s.setApiKey('sk-persist')
    setActivePinia(createPinia())
    const s2 = useAgentLlmStore()
    expect(s2.state.useOverrides).toBe(true)
    expect(s2.state.apiKey).toBe('sk-persist')
  })
})
