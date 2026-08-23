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
import { PROVIDERS, isCustomProvider, customProviderUuid, useAiSettingsStore } from './aiSettings'
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
    feedbackModel: 'deepseek-v4-flash', // 反馈专用快模型; 留空 = 跟随引擎模型
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
    // 防脚枪: 换非 DeepSeek 厂商时清掉默认的 deepseek flash, 避免模型/端点不匹配
    if (pid !== 'deepseek' && state.value.feedbackModel === 'deepseek-v4-flash') {
      state.value.feedbackModel = ''
    }
    persist()
  }
  function setApiKey(key) { state.value.apiKey = key; persist() }
  function setBaseUrl(url) { state.value.baseUrl = url; persist() }
  function setModel(m) { state.value.model = m; persist() }
  function setFeedbackModel(m) { state.value.feedbackModel = m; persist() }

  /** 回退来源: AI 助手 Key (OpenAI 兼容厂商), 用于学习引擎未独立配置时。 */
  function aiFallbackOverrides() {
    const ai = useAiSettingsStore()
    const key = ai.apiKey?.trim()
    if (!key) return null
    const meta = PROVIDERS.find((p) => p.id === ai.provider)
    // Agent 引擎仅支持 OpenAI 兼容协议; Anthropic 等不回退 (走后端 .env)
    if (meta?.protocol === 'anthropic') return null
    return {
      api_key: key,
      base_url: ai.getBaseUrl() || '',
      model: ai.model || '',
      protocol: 'openai',
    }
  }

  /**
   * 返回供请求体注入的 overrides；优先级:
   * 1. 独立配置开启且有 key → 独立 key
   * 2. 未开启/空 key → 回退 AI 助手 Key (OpenAI 兼容, 消除"明明配了 AI 助手还 401")
   * 3. 两者皆无 → null (走后端 .env)
   */
  function buildOverrides() {
    if (state.value.useOverrides && state.value.apiKey?.trim()) {
      return {
        api_key: state.value.apiKey,
        base_url: state.value.baseUrl,
        model: state.value.model,
        protocol: state.value.protocol,   // 本期固定 'openai'
      }
    }
    return aiFallbackOverrides()
  }

  /** 设置页提示: 当前出题/判分实际生效的密钥来源。 */
  function effectiveSource() {
    const mask = (k) => (k?.length > 6 ? `…${k.slice(-4)}` : (k ? '已配置' : '未配置'))
    if (state.value.useOverrides && state.value.apiKey?.trim()) {
      return { type: 'engine', text: `学习引擎独立 Key（${mask(state.value.apiKey)}）` }
    }
    const ai = useAiSettingsStore()
    if (ai.apiKey?.trim()) {
      return { type: 'ai', text: `回退到 AI 助手 Key（${mask(ai.apiKey)}）` }
    }
    return { type: 'env', text: '后端 .env 的 LLM_API_KEY（若为占位符 sk-placeholder 将 401）' }
  }

  /**
   * 反馈专用 overrides（仅「获取针对性反馈」请求注入，交互式等待敏感）：
   * - feedbackModel 留空 → 跟随引擎（buildOverrides 结果，可能 null）
   * - 独立配置开 → 全量覆写，仅 model 换成快模型
   * - 独立配置关 → 部分覆写仅 model，api_key/base_url 走后端 .env
   *   （后端 get_chat_model 逐字段回退 settings，实测可用）
   */
  function buildFeedbackOverrides() {
    const engine = buildOverrides()
    const fm = state.value.feedbackModel?.trim()
    if (!fm) return engine
    if (!engine) return { model: fm }
    return { ...engine, model: fm }
  }

  return {
    state, setUseOverrides, setProvider, setApiKey, setBaseUrl, setModel, setFeedbackModel,
    buildOverrides, buildFeedbackOverrides, effectiveSource,
  }
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

/**
 * 反馈专用注入 helper：仅「获取针对性反馈」请求用它（等待敏感，换快模型减等待）。
 * 其余 Agent 调用仍走 withOverrides（引擎模型）。
 */
export function withFeedbackOverrides(body) {
  const overrides = useAgentLlmStore().buildFeedbackOverrides()
  if (!overrides) return body
  return { ...(body || {}), llm_overrides: overrides }
}
