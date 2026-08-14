import { describe, it, expect, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAgentLlmStore, withOverrides, withFeedbackOverrides } from '@/stores/agentLlm'

describe('agentLlm store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('defaults to useOverrides=false + empty key + feedbackModel=flash', () => {
    const s = useAgentLlmStore()
    expect(s.state.useOverrides).toBe(false)
    expect(s.state.apiKey).toBe('')
    expect(s.state.feedbackModel).toBe('deepseek-v4-flash')
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

  // ---- 反馈快模型 (buildFeedbackOverrides) ----

  it('feedback overrides: disabled + default flash -> partial override {model} only', () => {
    const s = useAgentLlmStore()
    s.setUseOverrides(false)
    expect(s.buildFeedbackOverrides()).toEqual({ model: 'deepseek-v4-flash' })
  })

  it('feedback overrides: cleared feedbackModel follows engine (null when disabled)', () => {
    const s = useAgentLlmStore()
    s.setFeedbackModel('')
    s.setUseOverrides(false)
    expect(s.buildFeedbackOverrides()).toBeNull()
  })

  it('feedback overrides: cleared feedbackModel follows engine overrides when enabled', () => {
    const s = useAgentLlmStore()
    s.setFeedbackModel('')
    s.setUseOverrides(true)
    s.setApiKey('sk-x')
    s.setProvider('deepseek')
    s.setBaseUrl('https://api.deepseek.com/v1')
    s.setModel('deepseek-v4-pro')
    expect(s.buildFeedbackOverrides()).toEqual({
      api_key: 'sk-x',
      base_url: 'https://api.deepseek.com/v1',
      model: 'deepseek-v4-pro',
      protocol: 'openai',
    })
  })

  it('feedback overrides: enabled + key -> full overrides with fast model', () => {
    const s = useAgentLlmStore()
    s.setUseOverrides(true)
    s.setApiKey('sk-x')
    s.setProvider('deepseek')
    s.setBaseUrl('https://api.deepseek.com/v1')
    s.setModel('deepseek-v4-pro')
    s.setFeedbackModel('deepseek-chat')
    expect(s.buildFeedbackOverrides()).toEqual({
      api_key: 'sk-x',
      base_url: 'https://api.deepseek.com/v1',
      model: 'deepseek-chat',
      protocol: 'openai',
    })
  })

  it('withFeedbackOverrides injects llm_overrides on feedback body; no-op when cleared', () => {
    const s = useAgentLlmStore()
    const body1 = withFeedbackOverrides({ session_id: 's1', strategy: 'scaffold' })
    expect(body1.llm_overrides).toEqual({ model: 'deepseek-v4-flash' })
    s.setFeedbackModel('')
    const body2 = withFeedbackOverrides({ session_id: 's1', strategy: 'scaffold' })
    expect(body2.llm_overrides).toBeUndefined()
    expect(body2.session_id).toBe('s1')
  })

  it('setProvider to non-deepseek clears default flash feedbackModel (mismatch guard)', () => {
    const s = useAgentLlmStore()
    expect(s.state.feedbackModel).toBe('deepseek-v4-flash')
    s.setProvider('qwen')
    expect(s.state.feedbackModel).toBe('')
    // 用户手动设置的快模型不被清
    s.setFeedbackModel('qwen3-turbo')
    s.setProvider('glm')
    expect(s.state.feedbackModel).toBe('qwen3-turbo')
  })
})
