import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

const STORAGE_KEY = 'kmatch-ai-settings'

export const TOOL_PERMISSION = Object.freeze({
  ALLOW: 'allow',
  ASK: 'ask',
  DENY: 'deny',
})

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

const DEFAULT_TOOL_PERMISSIONS = Object.freeze({
  read_file: TOOL_PERMISSION.ALLOW,
  list_directory: TOOL_PERMISSION.ALLOW,
  write_file: TOOL_PERMISSION.ASK,
  generate_project_graph: TOOL_PERMISSION.ALLOW,
  code_review: TOOL_PERMISSION.ALLOW,
  code_test: TOOL_PERMISSION.ALLOW,
})

// ---- 厂商 & 模型 (C1.1: 从 chat.js 迁入, 统一 AI 配置单一源) ----
export const PROVIDERS = Object.freeze([
  { id: 'deepseek', label: 'DeepSeek', baseUrl: 'https://api.deepseek.com/v1' },
  { id: 'openai', label: 'OpenAI', baseUrl: 'https://api.openai.com/v1' },
  { id: 'ollama', label: 'Ollama (本地)', baseUrl: 'http://localhost:11434/v1' },
  { id: 'custom', label: '自定义', baseUrl: '' },
])

const DEFAULT_PROVIDER = 'deepseek'
const DEFAULT_MODEL = 'deepseek-v4-pro'

// 旧 chat.js 散装 localStorage 键 (迁移用, 迁入 blob 后不再写入)
const LEGACY_KEY_PROVIDER = 'kmatch-chat-provider'
const LEGACY_KEY_APIKEY = 'kmatch-chat-apikey'
const LEGACY_KEY_BASEURL = 'kmatch-chat-baseurl'

function fallbackModels(pid) {
  const map = {
    deepseek: ['deepseek-v4-pro', 'deepseek-v3', 'deepseek-reasoner'],
    openai: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo'],
    ollama: ['llama3', 'qwen2.5', 'codellama'],
    custom: [],
  }
  return map[pid] || []
}

function loadLegacyStr(key) {
  try { return localStorage.getItem(key) || '' } catch { return '' }
}

/** 从 blob 读取厂商配置; 缺失时从旧 chat 散装键迁移 (一次性, 不删旧键)。 */
function loadProviderConfig(saved) {
  const s = saved && typeof saved === 'object' ? saved : {}
  if (s.provider !== undefined || s.apiKey !== undefined || s.customBaseUrl !== undefined) {
    return {
      provider: typeof s.provider === 'string' && s.provider ? s.provider : DEFAULT_PROVIDER,
      apiKey: typeof s.apiKey === 'string' ? s.apiKey : '',
      customBaseUrl: typeof s.customBaseUrl === 'string' ? s.customBaseUrl : '',
      model: typeof s.model === 'string' ? s.model : DEFAULT_MODEL,
    }
  }
  // 旧键迁移
  return {
    provider: loadLegacyStr(LEGACY_KEY_PROVIDER, ) || DEFAULT_PROVIDER,
    apiKey: loadLegacyStr(LEGACY_KEY_APIKEY),
    customBaseUrl: loadLegacyStr(LEGACY_KEY_BASEURL),
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
  const customBaseUrl = ref(providerCfg.customBaseUrl)
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
        customBaseUrl: customBaseUrl.value,
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
    return PROVIDERS.find((p) => p.id === provider.value) || PROVIDERS[0]
  }

  function getBaseUrl() {
    const meta = providerMeta()
    return meta.baseUrl || customBaseUrl.value || ''
  }

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
      }
    } catch {
      models.value = fallbackModels(provider.value)
    }
  }

  function setProvider(pid) {
    provider.value = pid
    persist()
    fetchModels()
  }

  function setApiKey(key) {
    apiKey.value = key
    persist()
    fetchModels()
  }

  function setCustomBaseUrl(url) {
    customBaseUrl.value = (url || '').trim()
    persist()
    if (provider.value === 'custom') fetchModels()
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
    customBaseUrl,
    model,
    models,
    providerMeta,
    getBaseUrl,
    fetchModels,
    setProvider,
    setApiKey,
    setCustomBaseUrl,
  }
})
