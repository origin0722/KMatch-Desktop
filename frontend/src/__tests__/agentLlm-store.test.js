import { describe, it, expect, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAgentLlmStore, withOverrides, withFeedbackOverrides } from '@/stores/agentLlm'
import { useAiSettingsStore } from '@/stores/aiSettings'

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

  // ---- 回退链: 学习引擎未配 → AI 助手 Key (消除"明明配了 AI 助手还 401") ----

  it('fallback: 未开启独立配置 + AI 助手有 key → 回退使用 AI 助手 Key', async () => {
    const ai = useAiSettingsStore()
    await ai.setApiKey('sk-ai-key')
    const s = useAgentLlmStore()
    s.setUseOverrides(false)
    const ov = s.buildOverrides()
    expect(ov).not.toBeNull()
    expect(ov.api_key).toBe('sk-ai-key')
    expect(ov.protocol).toBe('openai')
    expect(s.effectiveSource().type).toBe('ai')
  })

  it('fallback: AI 助手也无 key → null (走后端 .env), effectiveSource=env', () => {
    const s = useAgentLlmStore()
    s.setUseOverrides(false)
    expect(s.buildOverrides()).toBeNull()
    expect(s.effectiveSource().type).toBe('env')
  })

  it('fallback: 独立配置优先于 AI 助手 Key', async () => {
    const ai = useAiSettingsStore()
    await ai.setApiKey('sk-ai-key')
    const s = useAgentLlmStore()
    s.setUseOverrides(true)
    s.setApiKey('sk-engine')
    s.setProvider('deepseek')
    s.setBaseUrl('https://api.deepseek.com/v1')
    s.setModel('deepseek-v4-pro')
    const ov = s.buildOverrides()
    expect(ov.api_key).toBe('sk-engine')
    expect(s.effectiveSource().type).toBe('engine')
  })

  it('withOverrides 注入 AI 回退 key 到请求体', async () => {
    const ai = useAiSettingsStore()
    await ai.setApiKey('sk-ai-key')
    const body = withOverrides({ target_direction: 'x' })
    expect(body.llm_overrides.api_key).toBe('sk-ai-key')
  })

  // issue: 独立 Key 原样发送未 trim, 粘贴带入的尾随换行/空格通过校验却在上游 401
  // (桩值刻意避开真实凭据形态: 无厂商 key 前缀, 仅本地测试假值)
  it('buildOverrides 发送前逐字段 trim (粘贴脏字符不再导致 401)', () => {
    const s = useAgentLlmStore()
    s.setUseOverrides(true)
    const dirtyKey = `  test-engine-key-9999  \n`
    s.setApiKey(dirtyKey)
    s.setBaseUrl(' https://api.deepseek.com/v1 \n')
    s.setModel(' deepseek-v4-pro ')
    const ov = s.buildOverrides()
    expect(ov.api_key.trim()).toBe(dirtyKey.trim())
    expect(ov.base_url).toBe('https://api.deepseek.com/v1')
    expect(ov.model).toBe('deepseek-v4-pro')
    expect(ov.protocol).toBe('openai')
  })

  it('setApiKey 落盘即 trim (旧版本存进 localStorage 的脏值被覆盖自愈)', () => {
    const s = useAgentLlmStore()
    const dirtyKey = ` dirty-test-key \n`
    s.setApiKey(dirtyKey)
    expect(s.state.apiKey).toBe(dirtyKey.trim())
  })
})
