import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { TOOL_PERMISSION, DEFAULT_TOOL_PERMISSIONS } from '@/ide/tools/registry'
import { useCustomProvidersStore } from './customProviders'

export function isCustomProvider(p) {
  return typeof p === 'string' && p.startsWith('custom:')
}

export function customProviderUuid(p) {
  return isCustomProvider(p) ? p.slice('custom:'.length) : null
}

const STORAGE_KEY = 'kmatch-ai-settings'

export const REASONING_MODE = Object.freeze({
  AUTO: 'auto',
  FAST: 'fast',
  DEEP: 'deep',
})

const DEFAULT_PROXY = Object.freeze({
  enabled: false,
  type: 'http',
  url: '',
  scope: 'all',
})

// ---- 厂商 & 模型 (C1.1: 从 chat.js 迁入, 统一 AI 配置单一源) ----
export const PROVIDERS = Object.freeze([
  { id: 'deepseek',  label: 'DeepSeek',         baseUrl: 'https://api.deepseek.com/v1',
    protocol: 'openai',    iconKey: 'deepseek',
    fallbackModels: ['deepseek-v4-pro', 'deepseek-v3', 'deepseek-reasoner'] },
  { id: 'openai',    label: 'OpenAI',           baseUrl: 'https://api.openai.com/v1',
    protocol: 'openai',    iconKey: 'openai',
    fallbackModels: ['gpt-4o', 'gpt-4o-mini', 'gpt-4.1', 'o1', 'o3-mini'] },
  { id: 'anthropic', label: 'Anthropic',        baseUrl: 'https://api.anthropic.com',
    protocol: 'anthropic', iconKey: 'claude',
    fallbackModels: ['claude-fable-5', 'claude-opus-4-8', 'claude-sonnet-4-6', 'claude-haiku-4-5'] },
  { id: 'moonshot',  label: 'Moonshot',         baseUrl: 'https://api.moonshot.cn/v1',
    protocol: 'openai',    iconKey: 'moonshot',
    fallbackModels: ['moonshot-v1-128k', 'moonshot-v1-32k', 'kimi-k2-0905-preview'] },
  { id: 'qwen',      label: '通义千问',          baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    protocol: 'openai',    iconKey: 'qwen',
    fallbackModels: ['qwen-max', 'qwen-plus', 'qwen-turbo', 'qwen-vl-max'] },
  { id: 'gemini',    label: 'Google Gemini',    baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai',
    protocol: 'openai',    iconKey: 'google',
    fallbackModels: ['gemini-2.5-pro', 'gemini-2.5-flash'] },
  { id: 'ollama',    label: 'Ollama (本地)',    baseUrl: 'http://localhost:11434/v1',
    protocol: 'openai',    iconKey: 'ollama',
    fallbackModels: ['llama3', 'qwen2.5', 'codellama'] },
  { id: 'custom',    label: '自定义',            baseUrl: '',
    protocol: 'openai',    iconKey: 'custom',
    fallbackModels: [] },
])

const DEFAULT_PROVIDER = 'deepseek'
const DEFAULT_MODEL = 'deepseek-v4-pro'

// 旧 chat.js 散装 localStorage 键 (迁移用, 迁入 blob 后不再写入)
const LEGACY_KEY_PROVIDER = 'kmatch-chat-provider'
const LEGACY_KEY_APIKEY = 'kmatch-chat-apikey'

function fallbackModels(pid) {
  // custom:<uuid> 走 customProviders.models
  if (isCustomProvider(pid)) {
    try {
      const cp = useCustomProvidersStore().get(customProviderUuid(pid))
      return Array.isArray(cp?.models) ? [...cp.models] : []
    } catch { return [] }
  }
  const meta = PROVIDERS.find((p) => p.id === pid)
  return meta ? [...meta.fallbackModels] : []
}

function loadLegacyStr(key) {
  try { return localStorage.getItem(key) || '' } catch { return '' }
}

/** 从 blob 读取厂商配置; 缺失时从旧 chat 散装键迁移 (一次性, 不删旧键)。
 *  另：旧 customBaseUrl + provider='custom' → customProviders[id=default] 一次性迁移。 */
function loadProviderConfig(saved) {
  const s = saved && typeof saved === 'object' ? saved : {}
  if (s.provider !== undefined || s.apiKey !== undefined || s.customBaseUrl !== undefined) {
    const out = {
      provider: typeof s.provider === 'string' && s.provider ? s.provider : DEFAULT_PROVIDER,
      apiKey: typeof s.apiKey === 'string' ? s.apiKey : '',
      model: typeof s.model === 'string' ? s.model : DEFAULT_MODEL,
    }
    // 一次性迁移: 旧 customBaseUrl → customProviders[id=default]
    if (typeof s.customBaseUrl === 'string' && s.customBaseUrl) {
      const cps = useCustomProvidersStore()
      cps.add({
        id: 'default',
        name: '自定义',
        baseUrl: s.customBaseUrl,
        apiKey: out.provider === 'custom' ? out.apiKey : '',
        protocol: 'openai',
      })
      if (out.provider === 'custom') {
        out.provider = 'custom:default'
        out.apiKey = ''   // 已挪到 customProviders[default].apiKey
      }
    }
    return out
  }
  // 旧键迁移
  return {
    provider: loadLegacyStr(LEGACY_KEY_PROVIDER) || DEFAULT_PROVIDER,
    apiKey: loadLegacyStr(LEGACY_KEY_APIKEY),
    model: DEFAULT_MODEL,
  }
}

function safeJsonParse(raw) {
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

function loadState() {
  try {
    return safeJsonParse(localStorage.getItem(STORAGE_KEY)) || {}
  } catch {
    return {}
  }
}

function saveState(state) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  } catch {
    // localStorage can fail in private mode or quota exhaustion; settings remain in memory.
  }
}

function nowIso() {
  return new Date().toISOString()
}

function normalizeToolPermissions(input) {
  const normalized = { ...DEFAULT_TOOL_PERMISSIONS }
  const source = input && typeof input === 'object' && !Array.isArray(input) ? input : {}
  const validModes = Object.values(TOOL_PERMISSION)

  Object.keys(DEFAULT_TOOL_PERMISSIONS).forEach((tool) => {
    if (validModes.includes(source[tool])) {
      normalized[tool] = source[tool]
    }
  })

  return normalized
}

function normalizeText(value) {
  if (value == null) return ''
  if (typeof value === 'string') return value.trim()
  if (['number', 'boolean', 'bigint'].includes(typeof value)) return String(value).trim()
  return ''
}

function normalizeMemory(input) {
  const source = input && typeof input === 'object' ? input : {}
  const id = source.id || `mem_${Date.now()}_${Math.random().toString(16).slice(2)}`
  const createdAt = source.createdAt || nowIso()

  return {
    id,
    type: source.type || 'preference',
    title: normalizeText(source.title),
    content: normalizeText(source.content),
    source: source.source || 'manual',
    enabled: source.enabled !== false,
    createdAt,
    updatedAt: source.updatedAt || createdAt,
  }
}

export const useAiSettingsStore = defineStore('aiSettings', () => {
  const saved = loadState()

  const providerCfg = loadProviderConfig(saved.providerConfig)
  const provider = ref(providerCfg.provider)
  const apiKey = ref(providerCfg.apiKey)
  const model = ref(providerCfg.model)
  const models = ref([])

  const proxy = ref({ ...DEFAULT_PROXY, ...(saved.proxy || {}) })
  const toolPermissions = ref(normalizeToolPermissions(saved.toolPermissions))
  const memories = ref(Array.isArray(saved.memories) ? saved.memories.map(normalizeMemory) : [])
  const reasoningMode = ref(Object.values(REASONING_MODE).includes(saved.reasoningMode)
    ? saved.reasoningMode
    : REASONING_MODE.AUTO)

  const enabledMemories = computed(() => memories.value.filter((m) => m.enabled && m.title && m.content))

  function persist() {
    saveState({
      providerConfig: {
        provider: provider.value,
        apiKey: apiKey.value,
        model: model.value,
      },
      proxy: proxy.value,
      toolPermissions: toolPermissions.value,
      memories: memories.value,
      reasoningMode: reasoningMode.value,
    })
  }

  // ---- 厂商 & 模型 ----
  function providerMeta() {
    if (isCustomProvider(provider.value)) {
      const uuid = customProviderUuid(provider.value)
      const cp = useCustomProvidersStore().get(uuid)
      return cp
        ? { id: provider.value, label: cp.name, baseUrl: cp.baseUrl,
            protocol: cp.protocol || 'openai', iconKey: 'custom',
            fallbackModels: cp.models || [] }
        : PROVIDERS[0]
    }
    return PROVIDERS.find((p) => p.id === provider.value) || PROVIDERS[0]
  }

  function getBaseUrl() { return providerMeta().baseUrl || '' }

  async function fetchModels() {
    const key = apiKey.value.trim()
    if (!key) {
      models.value = fallbackModels(provider.value)
      if (!model.value || !models.value.find((m) => m === model.value)) {
        model.value = models.value[0] || ''
      }
      return
    }
    const base = getBaseUrl()
    if (!base) {
      models.value = fallbackModels(provider.value)
      // 无 base (custom 未填 URL): 仍校正 model 到 fallback, 避免残留跨厂商旧值
      if (!model.value || !models.value.find((m) => m === model.value)) {
        model.value = models.value[0] || ''
      }
      return
    }
    try {
      // 走 IPC 代理 (window.api.http), 桌面应用无需浏览器 fetch
      const res = await window.api.http.request('POST', '/api/chat/models', { base_url: base, api_key: key })
      const data = res.body
      if (!res.ok) throw new Error(typeof data === 'string' ? data : (data?.error || `HTTP ${res.status}`))
      if (data.models?.length) {
        models.value = data.models.sort()
        if (!model.value || !data.models.includes(model.value)) {
          model.value = data.models[0]
        }
      } else {
        models.value = fallbackModels(provider.value)
        if (!model.value || !models.value.find((m) => m === model.value)) {
          model.value = models.value[0] || ''
        }
      }
    } catch {
      // 离线/失败: 回退并校正 model, 避免向当前厂商发送跨厂商残留 model id
      models.value = fallbackModels(provider.value)
      if (!model.value || !models.value.find((m) => m === model.value)) {
        model.value = models.value[0] || ''
      }
    }
  }

  // setters: 立即 persist provider/apiKey (同步落盘, 不依赖网络),
  // 再 fetchModels 校正 model 并二次 persist (避免把旧/跨厂商 model 写进 blob)。
  // 审查 #1 修了 model 竞态, 但把 persist 整体 gate 在 fetch 后会导致慢网络下丢失 provider/key —— 拆开。
  async function setProvider(pid) {
    provider.value = pid
    if (isCustomProvider(pid)) {
      const cp = useCustomProvidersStore().get(customProviderUuid(pid))
      apiKey.value = cp?.apiKey || ''
    }
    persist()
    await fetchModels()
    persist()
  }

  async function setApiKey(key) {
    apiKey.value = key
    if (isCustomProvider(provider.value)) {
      const uuid = customProviderUuid(provider.value)
      useCustomProvidersStore().update(uuid, { apiKey: key })
    }
    persist()
    await fetchModels()
    persist()
  }

  function setProxy(next) {
    proxy.value = { ...proxy.value, ...(next || {}) }
    persist()
  }

  function setToolPermission(tool, mode) {
    if (!Object.prototype.hasOwnProperty.call(DEFAULT_TOOL_PERMISSIONS, tool)) return
    if (!Object.values(TOOL_PERMISSION).includes(mode)) return
    toolPermissions.value = { ...toolPermissions.value, [tool]: mode }
    persist()
  }

  function permissionFor(tool) {
    if (!Object.prototype.hasOwnProperty.call(DEFAULT_TOOL_PERMISSIONS, tool)) return TOOL_PERMISSION.DENY
    return toolPermissions.value[tool] || TOOL_PERMISSION.DENY
  }

  function isToolAllowed(tool) {
    return permissionFor(tool) !== TOOL_PERMISSION.DENY
  }

  function shouldAskForTool(tool) {
    return permissionFor(tool) === TOOL_PERMISSION.ASK
  }

  function setReasoningMode(mode) {
    reasoningMode.value = Object.values(REASONING_MODE).includes(mode) ? mode : REASONING_MODE.AUTO
    persist()
  }

  function modelReasoningSupport(provider, model) {
    const id = String(model || '').toLowerCase()
    // DeepSeek-V4 系列 + deepseek-reasoner 走 extra_body.thinking (后端 _is_deepseek_thinking_model)
    if (provider === 'deepseek' && (id.startsWith('deepseek-v4') || id === 'deepseek-reasoner')) return 'native'
    if (id.includes('claude-opus-4') || id.includes('claude-fable-5') || id.includes('claude-mythos-5')) {
      return 'native-when-supported-by-backend'
    }
    if (!id) return 'unknown'
    return 'prompt-only'
  }

  function reasoningInstruction(provider, model) {
    const support = modelReasoningSupport(provider, model)
    if (reasoningMode.value === REASONING_MODE.FAST) {
      return '思考模式: 快速。请直接给出简洁实用的回答，不展开冗长推理。'
    }
    if (reasoningMode.value === REASONING_MODE.DEEP) {
      if (support === 'native') return '思考模式: 深度。当前模型支持 reasoning，请进行更充分的分析，并在最终回答中保持结论清晰。'
      return '思考模式: 深度。当前模型未确认支持原生 thinking 参数，请更仔细地分析问题，先内部推理，再给出简洁结论。'
    }
    return ''
  }

  function addMemory(input) {
    const memory = normalizeMemory(input || {})
    if (!memory.title || !memory.content) return null
    memories.value = [...memories.value, memory]
    persist()
    return memory
  }

  function updateMemory(id, patch) {
    let updated = null
    memories.value = memories.value.map((memory) => {
      if (memory.id !== id) return memory
      updated = normalizeMemory({
        ...memory,
        ...(patch || {}),
        id: memory.id,
        createdAt: memory.createdAt,
        updatedAt: nowIso(),
      })
      return updated
    })
    persist()
    return updated
  }

  function removeMemory(id) {
    memories.value = memories.value.filter((memory) => memory.id !== id)
    persist()
  }

  function formatEnabledMemories(limit = 10, maxChars = 220) {
    const selected = enabledMemories.value.slice(0, limit)
    if (!selected.length) return ''

    const lines = selected.map((memory) => {
      const content = memory.content.length > maxChars
        ? `${memory.content.slice(0, maxChars)}…`
        : memory.content
      return `- [${memory.type}] ${memory.title}: ${content}`
    })

    return `\n\n## 用户记忆\n${lines.join('\n')}`
  }

  // 初始化: 拉取模型列表 (无 apiKey 时走 fallback, 不触网)
  fetchModels()

  return {
    proxy,
    toolPermissions,
    memories,
    enabledMemories,
    reasoningMode,
    setProxy,
    setToolPermission,
    permissionFor,
    isToolAllowed,
    shouldAskForTool,
    setReasoningMode,
    modelReasoningSupport,
    reasoningInstruction,
    addMemory,
    updateMemory,
    removeMemory,
    formatEnabledMemories,
    // 厂商 & 模型 (C1.1: 从 chat.js 迁入)
    provider,
    apiKey,
    model,
    models,
    providerMeta,
    getBaseUrl,
    fetchModels,
    setProvider,
    setApiKey,
  }
})
