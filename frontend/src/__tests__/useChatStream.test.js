/**
 * 场景：Chat SSE 传输层 composable (C1.3, 从 chat.js 抽出)。
 *
 * 只测传输：IPC 代理路（window.api.http.stream/onChunk/onDone/onError）与浏览器 fetch 回退路。
 * 验证：跨 chunk 的 \n\n 分帧、onBlock 逐块回调、onBlock 返回 Error 中止并 reject、
 * onDone resolve、onError reject、abort 结束等待、F3 reqId 过滤 (并发流不串扰)。
 */
import { describe, it, expect, afterEach, vi } from 'vitest'
import { streamChat } from '@/ide/chat/useChatStream'

/** 装一个 window.api.http mock, 捕获 stream 调用的 reqId 与三个回调注册器。 */
function mockIpc(streamImpl = () => Promise.resolve()) {
  let onChunk, onDone, onError
  let capturedReqId
  window.api = {
    http: {
      stream: vi.fn((urlPath, body, reqId) => { capturedReqId = reqId; return streamImpl() }),
      onChunk: (cb) => { onChunk = cb; return () => {} },
      onDone: (cb) => { onDone = cb; return () => {} },
      onError: (cb) => { onError = cb; return () => {} },
    },
  }
  return {
    get reqId() { return capturedReqId },
    emitChunk: (rid, block) => onChunk(rid, block),
    emitDone: (rid) => onDone(rid),
    emitError: (rid, err) => onError(rid, err),
  }
}

describe('useChatStream — SSE 传输层 (C1.3)', () => {
  afterEach(() => { vi.unstubAllGlobals(); delete window.api })

  it('IPC 路: 每个 http:stream:chunk 是完整 block (http-proxy 已分帧), 逐块回调', async () => {
    // http-proxy 已按 \n\n 分帧, 每个 chunk 就是一个完整 SSE block (无 \n\n 定界符)。
    // 渲染层不再二次 split, 直接交 onBlock。
    const m = mockIpc()
    const blocks = []
    const p = streamChat({ body: {}, signal: new AbortController().signal, onBlock: (b) => blocks.push(b) })
    const rid = m.reqId
    m.emitChunk(rid, 'data: {"delta":"hello"}')
    m.emitChunk(rid, 'data: {"delta":"world"}')
    m.emitDone(rid)
    await p
    expect(blocks).toEqual(['data: {"delta":"hello"}', 'data: {"delta":"world"}'])
  })

  it('IPC 路: onBlock 返回 Error 立即中止并 reject, 后续 block 不再回调 (F2)', async () => {
    const m = mockIpc()
    const blocks = []
    const p = streamChat({
      body: {},
      signal: new AbortController().signal,
      onBlock: (b) => { blocks.push(b); return b.includes('bad') ? new Error('bad') : undefined },
    })
    const rid = m.reqId
    m.emitChunk(rid, 'data: {"delta":"ok"}')
    m.emitChunk(rid, 'data: {"error":"bad"}')
    m.emitChunk(rid, 'data: {"delta":"unreached"}')
    m.emitDone(rid)
    await expect(p).rejects.toThrow('bad')
    expect(blocks).toHaveLength(2) // 第三个 block 中止后不再回调
    expect(blocks[1]).toContain('bad')
  })

  it('IPC 路: onError reject', async () => {
    const m = mockIpc()
    const p = streamChat({ body: {}, signal: new AbortController().signal, onBlock: () => {} })
    m.emitError(m.reqId, 'HTTP 500: boom')
    await expect(p).rejects.toThrow('boom')
  })

  it('IPC 路: stream() 本身 reject 时透传', async () => {
    const m = mockIpc(() => Promise.reject(new Error('stream init failed')))
    await expect(
      streamChat({ body: {}, signal: new AbortController().signal, onBlock: () => {} }),
    ).rejects.toThrow('stream init failed')
  })

  it('IPC 路: abort signal 结束等待 (resolve)', async () => {
    const m = mockIpc()
    const ac = new AbortController()
    const p = streamChat({ body: {}, signal: ac.signal, onBlock: () => {} })
    ac.abort() // 用户点停止
    await expect(p).resolves.toBeUndefined()
  })

  it('F3: 仅处理本流 reqId, 忽略其他并发流的事件', async () => {
    const m = mockIpc()
    const blocks = []
    const p = streamChat({ body: {}, signal: new AbortController().signal, onBlock: (b) => blocks.push(b) })
    const rid = m.reqId
    // 其他流的 chunk (reqId 不匹配) 应被忽略
    m.emitChunk('other-stream', 'data: {"delta":"not mine"}')
    // 本流的 chunk 正常处理
    m.emitChunk(rid, 'data: {"delta":"mine"}')
    m.emitDone(rid)
    await p
    expect(blocks).toEqual(['data: {"delta":"mine"}'])
  })

  it('F3: 其他流的 done/error 不影响本流', async () => {
    const m = mockIpc()
    const p = streamChat({ body: {}, signal: new AbortController().signal, onBlock: () => {} })
    const rid = m.reqId
    m.emitDone('other-stream') // 忽略
    m.emitError('other-stream', '别的流出错') // 忽略
    m.emitDone(rid)
    await expect(p).resolves.toBeUndefined()
  })

  it('浏览器回退路: fetch + ReadableStream 分帧, onBlock 逐块', async () => {
    delete window.api // 无 IPC → 走 fetch 回退
    const encoder = new TextEncoder()
    const body = encoder.encode('data: {"delta":"a"}\n\ndata: {"delta":"b"}\n\n')
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      ok: true,
      body: { getReader: () => {
        let read = false
        return { read: async () => (read ? { done: true } : (read = true, { done: false, value: body })) }
      } },
    })))
    const blocks = []
    await streamChat({ body: {}, signal: new AbortController().signal, onBlock: (b) => blocks.push(b) })
    expect(blocks).toEqual(['data: {"delta":"a"}', 'data: {"delta":"b"}'])
  })

  it('浏览器回退路: onBlock 返回 Error → reject (F2)', async () => {
    delete window.api
    const encoder = new TextEncoder()
    const body = encoder.encode('data: {"error":"boom"}\n\n')
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      ok: true,
      body: { getReader: () => { let read = false; return { read: async () => (read ? { done: true } : (read = true, { done: false, value: body })) } } },
    })))
    await expect(
      streamChat({ body: {}, signal: new AbortController().signal, onBlock: (b) => new Error('boom') }),
    ).rejects.toThrow('boom')
  })

  it('浏览器回退路: 非 2xx 抛 HTTP 错', async () => {
    delete window.api
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 500, text: async () => 'server down' })))
    await expect(
      streamChat({ body: {}, signal: new AbortController().signal, onBlock: () => {} }),
    ).rejects.toThrow('server down')
  })
})
