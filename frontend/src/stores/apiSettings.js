/**
 * apiSettings — 统一 API 配置协调层 (设置页「API 设置」栏目)
 *
 * 作用: 在【AI 助手 (aiSettings)】与【出题/Agent 引擎 (agentLlm)】两个独立 LLM 通道之上,
 * 提供「统一 / 分开」两种模式 + 预设模型 + 连通性测试。
 *
 *  - mode=unified : 一份配置 (unified) → applyUnified() 同时落到 aiSettings 与 agentLlm
 *  - mode=separate: 两通道各自独立 (仍是既有 aiSettings / agentLlm, 本栏目只是把它们放到一起管理)
 *
 * 约定: 这里是"协调层", 不是新的单一真相源——真正的消费方仍是 aiSettings / agentLlm;
 * 统一只做"一端配置写两端", 分开则透出两端各自状态。
 */
import { ref } from 'vue'
import { defineStore } from 'pinia'
import http from '@/api/index'
import { PROVIDERS, useAiSettingsStore } from './aiSettings'
import { useAgentLlmStore } from './agentLlm'

const MODE_KEY = 'kmatch-api-settings'

/** 预设模型名 (方便下拉选择; 用户仍可手输自定义) */
export const MODEL_PRESETS = Object.freeze({
  deepseek: ['deepseek-v4-pro', 'deepseek-v4-flash', 'deepseek-chat', 'deepseek-reasoner'],
  openai: ['gpt-4.1', 'gpt-4o', 'gpt-4o-mini', 'o3'],
  anthropic: ['claude-sonnet-4-5', 'claude-3-7-sonnet', 'claude-3-5-haiku'],
  moonshot: ['moonshot-v1-32k', 'moonshot-v1-auto'],
  qwen: ['qwen3.5-plus', 'qwen-max', 'qwen-plus', 'qwen-turbo'],
  glm: ['glm-4.5', 'glm-4-plus', 'glm-4-flash'],
  gemini: ['gemini-2.5-pro', 'gemini-2.5-flash'],
  ollama: ['llama3.1', 'qwen2.5', 'deepseek-r1'],
})

/** 某厂商的预设模型清单 */
export function presetModelsFor(providerId) {
  return MODEL_PRESETS[providerId] || []
}

/** 全部预设合并 (供单个 <datalist> 用) */
export function allPresetModels() {
  return Object.values(MODEL_PRESETS).flat()
}

function defaultUnified() {
  return { provider: 'deepseek', baseUrl: 'https://api.deepseek.com/v1', apiKey: '', model: 'deepseek-v4-pro' }
}

function load() {
  try {
    const s = JSON.parse(localStorage.getItem(MODE_KEY) || '{}')
    return {
      mode: s.mode === 'unified' ? 'unified' : 'separate',
      unified: { ...defaultUnified(), ...(s.unified || {}) },
    }
  } catch {
    return { mode: 'separate', unified: defaultUnified() }
  }
}

function persist(mode, unified) {
  try { localStorage.setItem(MODE_KEY, JSON.stringify({ mode, unified })) } catch { /* quota/private */ }
}

function baseUrlOf(providerId) {
  const meta = PROVIDERS.find((p) => p.id === providerId)
  return meta?.baseUrl || ''
}

export const useApiSettingsStore = defineStore('apiSettings', () => {
  const s = load()
  const mode = ref(s.mode)
  const unified = ref({ ...s.unified })

  function setMode(m) {
    mode.value = m === 'unified' ? 'unified' : 'separate'
    persist(mode.value, unified.value)
  }

  function setUnified(patch) {
    const next = { ...unified.value, ...patch }
    // 选厂商(未显式给 baseUrl 时)自动带出新厂商默认 baseUrl
    if (patch.provider !== undefined && patch.baseUrl === undefined) {
      next.baseUrl = baseUrlOf(patch.provider)
    }
    unified.value = next
    persist(mode.value, unified.value)
  }

  /** 统一模式: 把 unified 配置落到 AI 助手 + Agent 引擎两端 */
  async function applyUnified() {
    const u = { ...unified.value, baseUrl: unified.value.baseUrl || baseUrlOf(unified.value.provider) }
    unified.value = u
    const ai = useAiSettingsStore()
    const ag = useAgentLlmStore()
    await ai.setProvider(u.provider)
    ai.setApiKey(u.apiKey)
    ai.setModel(u.model)
    ag.setUseOverrides(true) // 统一即"引擎走此 key"
    ag.setProvider(u.provider)
    ag.setBaseUrl(u.baseUrl)
    ag.setApiKey(u.apiKey)
    ag.setModel(u.model)
    persist(mode.value, unified.value)
  }

  /**
   * 连通性测试 (复用 /api/agents/ping, openai 兼容; anthropic 端点在 v1 中可能不支持)。
   * @returns {Promise<{ok:boolean, content?:string, error?:string}>}
   */
  async function testConnectivity({ apiKey, baseUrl, model }) {
    const { data } = await http.post('/api/agents/ping', {
      llm_overrides: { api_key: apiKey, base_url: baseUrl, model },
    })
    return data
  }

  return { mode, unified, setMode, setUnified, applyUnified, testConnectivity }
})
