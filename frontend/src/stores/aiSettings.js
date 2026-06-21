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

  const proxy = ref({ ...DEFAULT_PROXY, ...(saved.proxy || {}) })
  const toolPermissions = ref(normalizeToolPermissions(saved.toolPermissions))
  const memories = ref(Array.isArray(saved.memories) ? saved.memories.map(normalizeMemory) : [])
  const reasoningMode = ref(Object.values(REASONING_MODE).includes(saved.reasoningMode)
    ? saved.reasoningMode
    : REASONING_MODE.AUTO)

  const enabledMemories = computed(() => memories.value.filter((m) => m.enabled && m.title && m.content))

  function persist() {
    saveState({
      proxy: proxy.value,
      toolPermissions: toolPermissions.value,
      memories: memories.value,
      reasoningMode: reasoningMode.value,
    })
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
    if (provider === 'deepseek' && id === 'deepseek-reasoner') return 'native'
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
  }
})
