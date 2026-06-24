import { ref } from 'vue'
import { defineStore } from 'pinia'

const STORAGE_KEY = 'kmatch-ai-custom-providers'

function nowIso() { return new Date().toISOString() }
function uuid() { return `cp_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}` }

function loadList() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const arr = JSON.parse(raw)
    return Array.isArray(arr) ? arr : []
  } catch { return [] }
}

function saveList(list) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(list)) } catch { /* quota / private mode */ }
}

function normalize(input, prev) {
  const ts = nowIso()
  return {
    id: input.id || prev?.id || uuid(),
    name: input.name ?? prev?.name ?? '自定义',
    baseUrl: input.baseUrl ?? prev?.baseUrl ?? '',
    apiKey: input.apiKey ?? prev?.apiKey ?? '',
    models: Array.isArray(input.models) ? input.models : (prev?.models || []),
    protocol: input.protocol ?? prev?.protocol ?? 'openai',
    description: input.description ?? prev?.description ?? '',
    createdAt: prev?.createdAt || ts,
    updatedAt: ts,
  }
}

export const useCustomProvidersStore = defineStore('customProviders', () => {
  const list = ref(loadList())

  function persist() { saveList(list.value) }

  function add(input) {
    const id = input?.id
    if (id) {
      const existing = list.value.find((c) => c.id === id)
      if (existing) return update(id, input)  // upsert by id
    }
    const item = normalize(input || {})
    list.value = [...list.value, item]
    persist()
    return item
  }

  function update(id, patch) {
    let next = null
    list.value = list.value.map((c) => {
      if (c.id !== id) return c
      next = normalize({ ...patch, id }, c)
      return next
    })
    persist()
    return next
  }

  function remove(id) {
    list.value = list.value.filter((c) => c.id !== id)
    persist()
  }

  function get(id) { return list.value.find((c) => c.id === id) }

  async function autoFetchModels(id) {
    const cp = get(id)
    if (!cp || !cp.baseUrl) return { ok: false, error: 'baseUrl 未配置' }
    try {
      const res = await window.api.http.request('POST', '/api/chat/models', {
        base_url: cp.baseUrl, api_key: cp.apiKey || '', protocol: cp.protocol || 'openai',
      })
      const data = res.body
      if (!res.ok || data?.error) return { ok: false, error: data?.error || `HTTP ${res.status}` }
      const models = Array.isArray(data.models) ? data.models : []
      update(id, { models })
      return { ok: true, models }
    } catch (e) {
      return { ok: false, error: e.message || '请求失败' }
    }
  }

  return { list, add, update, remove, get, autoFetchModels }
})
