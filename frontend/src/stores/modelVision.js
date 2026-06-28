import { ref } from 'vue'
import { defineStore } from 'pinia'

function keyOf(baseUrl, model) { return `${baseUrl}::${model}` }

export const useModelVisionStore = defineStore('modelVision', () => {
  const cache = ref(new Map())            // key -> bool
  const pending = ref(new Map())          // key -> Promise<bool>

  function hasVision(baseUrl, model) {
    return cache.value.get(keyOf(baseUrl, model))
  }

  function isPending(baseUrl, model) {
    return pending.value.has(keyOf(baseUrl, model))
  }

  async function probe(baseUrl, apiKey, model, protocol) {
    const k = keyOf(baseUrl, model)
    // dedupe in-flight
    const existing = pending.value.get(k)
    if (existing) return existing
    if (cache.value.has(k)) return cache.value.get(k)

    const task = (async () => {
      try {
        const res = await window.api.http.request('POST', '/api/chat/probe-vision', {
          base_url: baseUrl, api_key: apiKey, model, protocol: protocol || 'openai',
        })
        const data = res?.body || {}
        // auth 错: 不写缓存; 让用户改 key 后重探
        if (data.error === 'auth') return false
        const v = !!data.vision
        // 触发响应式: 重建 Map (Pinia 跟踪 ref 的 .value 替换)
        const next = new Map(cache.value)
        next.set(k, v)
        cache.value = next
        return v
      } catch {
        return false
      } finally {
        const np = new Map(pending.value)
        np.delete(k)
        pending.value = np
      }
    })()

    const np = new Map(pending.value)
    np.set(k, task)
    pending.value = np
    return task
  }

  async function clearAll() {
    try {
      await window.api.http.request('DELETE', '/api/chat/probe-vision/cache')
    } catch { /* 即使后端清空失败也清前端内存, 让用户能重探 */ }
    cache.value = new Map()
    pending.value = new Map()
  }

  function clearForBaseUrl(baseUrl) {
    const next = new Map()
    for (const [k, v] of cache.value) {
      if (!k.startsWith(`${baseUrl}::`)) next.set(k, v)
    }
    cache.value = next
  }

  return { cache, pending, hasVision, isPending, probe, clearAll, clearForBaseUrl }
})
