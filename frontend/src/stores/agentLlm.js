/**
 * Agent 学习引擎独立 LLM 配置 store (Spec B)
 *
 * 与 AI 助手 (aiSettings) 解耦：Agent 链（学情检测/资源生成/代码审查/测试）可用独立 key。
 * 本期 protocol 固定 'openai'（Anthropic 接入留后续 spec）。
 *
 * buildOverrides() 返回供 axios body 注入的 llm_overrides；关闭或无 key 时返回 null（走后端 .env）。
 */
import { ref } from 'vue'
import { defineStore } from 'pinia'
import { PROVIDERS, isCustomProvider, customProviderUuid } from './aiSettings'
import { useCustomProvidersStore } from './customProviders'

const STORAGE_KEY = 'kmatch-agent-llm'

function providerBaseUrl(pid) {
  if (isCustomProvider(pid)) {
    const cp = useCustomProvidersStore().get(customProviderUuid(pid))
    return cp?.baseUrl || ''
  }
  const meta = PROVIDERS.find((p) => p.id === pid)
  return meta?.baseUrl || ''
}

function defaultState() {
  return {
    useOverrides: false,
    provider: 'deepseek',
    apiKey: '',
    baseUrl: providerBaseUrl('deepseek'),
    model: 'deepseek-v4-pro',
    protocol: 'openai',
  }
}

function loadState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return defaultState()
    const s = JSON.parse(raw)
    return { ...defaultState(), ...s }
  } catch {
    return defaultState()
  }
}

function saveState(state) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)) } catch { /* quota / private */ }
}

export const useAgentLlmStore = defineStore('agentLlm', () => {
  const state = ref(loadState())

  function persist() { saveState(state.value) }

  function setUseOverrides(on) { state.value.useOverrides = !!on; persist() }
  function setProvider(pid) {
    state.value.provider = pid
    state.value.baseUrl = providerBaseUrl(pid)
    if (isCustomProvider(pid)) {
      const cp = useCustomProvidersStore().get(customProviderUuid(pid))
      state.value.apiKey = cp?.apiKey || ''
    }
    persist()
  }
  function setApiKey(key) { state.value.apiKey = key; persist() }
  function setBaseUrl(url) { state.value.baseUrl = url; persist() }
  function setModel(m) { state.value.model = m; persist() }

  /** 返回供请求体注入的 overrides；关闭/无 key 时返回 null（走后端 .env 默认）。 */
  function buildOverrides() {
    if (!state.value.useOverrides) return null
    if (!state.value.apiKey?.trim()) return null
    return {
      api_key: state.value.apiKey,
      base_url: state.value.baseUrl,
      model: state.value.model,
      protocol: state.value.protocol,   // 本期固定 'openai'
    }
  }

  return { state, setUseOverrides, setProvider, setApiKey, setBaseUrl, setModel, buildOverrides }
})

/**
 * 显式注入 helper：把 agentLlm.buildOverrides() 注入请求 body。
 * Agent 路由（assess/submit/feedback/stream/project review/test）调用点用它。
 * 关闭或无 key 时原样返回 body（走后端 .env）。
 */
export function withOverrides(body) {
  const overrides = useAgentLlmStore().buildOverrides()
  if (!overrides) return body
  return { ...(body || {}), llm_overrides: overrides }
}
