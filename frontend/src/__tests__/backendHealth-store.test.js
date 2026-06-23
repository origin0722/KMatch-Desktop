/**
 * 场景：后端健康状态 store (F14)。
 *
 * 此前 backend 健康只活在 StatusBar 组件本地 ref; 抽为 store 作单一真相源。
 * 验证: check() 据 /api/health 设 status; start() 幂等 (多次调用不重复轮询);
 * backendUp/label 派生正确; 连接失败标 false。
 */
import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useBackendHealthStore } from '@/stores/backendHealth'

function mockHealth(ok, status = 200) {
  globalThis.window = globalThis.window || {}
  globalThis.window.api = {
    http: { request: vi.fn().mockResolvedValue({ ok, status }) },
  }
}

describe('backendHealth store (F14)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
    delete globalThis.window.api
  })

  it('初始 status=null (未知), label=检测中', () => {
    mockHealth(true)
    const b = useBackendHealthStore()
    expect(b.status).toBeNull()
    expect(b.backendUnknown).toBe(true)
    expect(b.label).toBe('后端检测中')
  })

  it('check() 成功 → status=true, backendUp=true, label=后端就绪', async () => {
    mockHealth(true)
    const b = useBackendHealthStore()
    await b.check()
    expect(b.status).toBe(true)
    expect(b.backendUp).toBe(true)
    expect(b.label).toBe('后端就绪')
  })

  it('check() 失败 (非 2xx) → status=false, label=后端未起', async () => {
    mockHealth(false, 503)
    const b = useBackendHealthStore()
    await b.check()
    expect(b.status).toBe(false)
    expect(b.backendUp).toBe(false)
    expect(b.label).toBe('后端未起')
    expect(b.lastError).toContain('503')
  })

  it('check() 抛异常 (连接拒绝) → status=false', async () => {
    globalThis.window = globalThis.window || {}
    globalThis.window.api = { http: { request: vi.fn().mockRejectedValue(new Error('ECONNREFUSED')) } }
    const b = useBackendHealthStore()
    await b.check()
    expect(b.status).toBe(false)
    expect(b.lastError).toContain('ECONNREFUSED')
  })

  it('start() 幂等: 多次调用只启一个轮询; stop() 清除', async () => {
    mockHealth(true)
    const b = useBackendHealthStore()
    b.start()
    b.start() // 幂等, 不重复
    expect(window.api.http.request).toHaveBeenCalledTimes(1) // start 触发一次 check
    b.stop()
  })
})
