import { describe, it, expect, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useCustomProvidersStore } from '@/stores/customProviders'

describe('customProviders store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
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
})
