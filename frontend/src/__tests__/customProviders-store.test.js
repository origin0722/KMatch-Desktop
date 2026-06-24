import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useCustomProvidersStore } from '@/stores/customProviders'

describe('customProviders store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    globalThis.window = globalThis.window || {}
    window.api = window.api || {}
    window.api.http = { request: vi.fn() }
  })

  it('add returns new item with id/timestamps and persists', () => {
    const s = useCustomProvidersStore()
    const cp = s.add({ name: '本地', baseUrl: 'http://localhost:8080/v1', apiKey: 'k', models: ['x'] })
    expect(cp.id).toBeTruthy()
    expect(cp.createdAt).toBeTruthy()
    expect(s.list).toHaveLength(1)

    setActivePinia(createPinia())
    const s2 = useCustomProvidersStore()
    expect(s2.list[0].baseUrl).toBe('http://localhost:8080/v1')
  })

  it('update merges patch and bumps updatedAt', async () => {
    const s = useCustomProvidersStore()
    const cp = s.add({ name: 'a', baseUrl: 'u', apiKey: 'k' })
    const t0 = cp.updatedAt
    await new Promise(r => setTimeout(r, 5))
    const next = s.update(cp.id, { apiKey: 'k2' })
    expect(next.apiKey).toBe('k2')
    expect(next.updatedAt).not.toBe(t0)
    expect(next.createdAt).toBe(cp.createdAt)
  })

  it('remove drops the item', () => {
    const s = useCustomProvidersStore()
    const a = s.add({ name: 'a', baseUrl: 'u' })
    s.add({ name: 'b', baseUrl: 'u2' })
    s.remove(a.id)
    expect(s.list).toHaveLength(1)
    expect(s.get(a.id)).toBeUndefined()
  })

  it('add with id="default" is stable across calls (used by 1-group UI)', () => {
    const s = useCustomProvidersStore()
    s.add({ id: 'default', name: '自定义', baseUrl: 'u' })
    s.add({ id: 'default', name: '自定义', baseUrl: 'u2' })  // upsert by id
    expect(s.list).toHaveLength(1)
    expect(s.get('default').baseUrl).toBe('u2')
  })

  it('autoFetchModels 成功 → 返回 models 并写回 store, 调用参数正确', async () => {
    const s = useCustomProvidersStore()
    const cp = s.add({ name: '本地', baseUrl: 'http://localhost:8080/v1', apiKey: 'k', protocol: 'openai' })
    window.api.http.request.mockResolvedValueOnce({ ok: true, body: { models: ['m1', 'm2'] } })
    const ret = await s.autoFetchModels(cp.id)
    expect(ret).toEqual({ ok: true, models: ['m1', 'm2'] })
    expect(s.get(cp.id).models).toEqual(['m1', 'm2'])
    expect(window.api.http.request).toHaveBeenCalledWith('POST', '/api/chat/models', {
      base_url: 'http://localhost:8080/v1', api_key: 'k', protocol: 'openai',
    })
  })

  it('autoFetchModels 缺 baseUrl → {ok:false, error:"baseUrl 未配置"}', async () => {
    const s = useCustomProvidersStore()
    s.add({ id: 'x', name: 'a' })
    const ret = await s.autoFetchModels('x')
    expect(ret).toEqual({ ok: false, error: 'baseUrl 未配置' })
    expect(window.api.http.request).not.toHaveBeenCalled()
  })

  it('autoFetchModels HTTP 错误 (body 含 error 字段) → 透传错误消息', async () => {
    const s = useCustomProvidersStore()
    const cp = s.add({ name: 'a', baseUrl: 'u', apiKey: 'k' })
    window.api.http.request.mockResolvedValueOnce({ ok: false, status: 500, body: { error: 'server boom' } })
    const ret = await s.autoFetchModels(cp.id)
    expect(ret.ok).toBe(false)
    expect(ret.error).toContain('server boom')
  })

  it('autoFetchModels 抛异常 → 返回 e.message', async () => {
    const s = useCustomProvidersStore()
    const cp = s.add({ name: 'a', baseUrl: 'u', apiKey: 'k' })
    window.api.http.request.mockRejectedValueOnce(new Error('network down'))
    const ret = await s.autoFetchModels(cp.id)
    expect(ret).toEqual({ ok: false, error: 'network down' })
  })
})
