import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useModelVisionStore } from '@/stores/modelVision'

function mockHttp(impl) {
  globalThis.window = globalThis.window || {}
  window.api = window.api || {}
  window.api.http = { request: vi.fn(impl) }
}

describe('modelVision store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('hasVision returns undefined before probe', () => {
    const s = useModelVisionStore()
    expect(s.hasVision('u', 'm')).toBeUndefined()
  })

  it('probe writes cache and returns bool', async () => {
    mockHttp(async (_, __, body) => ({
      ok: true, body: { vision: true, cached: false },
    }))
    const s = useModelVisionStore()
    const v = await s.probe('http://x/v1', 'sk-X', 'gpt-4o', 'openai')
    expect(v).toBe(true)
    expect(s.hasVision('http://x/v1', 'gpt-4o')).toBe(true)
  })

  it('isPending true during probe, false after', async () => {
    let resolve
    mockHttp(() => new Promise(r => { resolve = r }))
    const s = useModelVisionStore()
    const p = s.probe('u', 'k', 'm', 'openai')
    expect(s.isPending('u', 'm')).toBe(true)
    resolve({ ok: true, body: { vision: false } })
    await p
    expect(s.isPending('u', 'm')).toBe(false)
  })

  it('probe dedupes concurrent calls for same key', async () => {
    let calls = 0
    mockHttp(() => { calls++; return Promise.resolve({ ok: true, body: { vision: true } }) })
    const s = useModelVisionStore()
    const [a, b] = await Promise.all([
      s.probe('u', 'k', 'm', 'openai'),
      s.probe('u', 'k', 'm', 'openai'),
    ])
    expect(calls).toBe(1)
    expect(a).toBe(b)
  })

  it('clearForBaseUrl drops only entries with that baseUrl', async () => {
    mockHttp(async () => ({ ok: true, body: { vision: true } }))
    const s = useModelVisionStore()
    await s.probe('u1', 'k', 'm1', 'openai')
    await s.probe('u2', 'k', 'm2', 'openai')
    s.clearForBaseUrl('u1')
    expect(s.hasVision('u1', 'm1')).toBeUndefined()
    expect(s.hasVision('u2', 'm2')).toBe(true)
  })

  it('clearAll calls DELETE /probe-vision/cache and clears memory', async () => {
    const calls = []
    mockHttp(async (method, url) => { calls.push([method, url]); return { ok: true, body: {} } })
    const s = useModelVisionStore()
    await s.probe('u', 'k', 'm', 'openai')
    await s.clearAll()
    expect(calls).toContainEqual(['DELETE', '/api/chat/probe-vision/cache'])
    expect(s.hasVision('u', 'm')).toBeUndefined()
  })
})
