/**
 * 场景：Chat SSE 传输层 composable (C1.3, 从 chat.js 抽出)。
 *
 * 只测传输：IPC 代理路（window.api.http.stream/onChunk/onDone/onError）与浏览器 fetch 回退路。
 * 验证：跨 chunk 的 \n\n 分帧、onBlock 逐块回调、onBlock 返回 'error' 中止、
 * onDone resolve、onError reject、abort 结束等待。不碰消息状态（由 chat store 的 _applySseBlock 管）。
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { streamChat } from '@/ide/chat/useChatStream'

describe('useChatStream — SSE 传输层 (C1.3)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    delete window.api
  })

  it('IPC 路: 跨 onChunk 的 \n\n 分帧, 逐 block 回调, onDone resolve', async () => {
    const chunks = []
    let onChunk, onDone, onError
    window.api = {
      http: {
        stream: vi.fn(() => Promise.resolve()),
        onChunk: (cb) => { onChunk = cb; return () => {} },
        onDone: (cb) => { onDone = cb; return () => {} },
        onError: (cb) => { onError = cb; return () => {} },
      },
    }
    const blocks = []
    const p = streamChat({ body: {}, signal: new AbortController().signal, onBlock: (b) => blocks.push(b) })
    // 一个 block 拆成两次 chunk 投递 (跨 chunk 分帧)
    onChunk('1', 'data: {"delta":"hel')
    onChunk('1', 'lo"}\n\ndata: {"delta":"wo')
    onChunk('1', 'rld"}\n\n')
    onDone()
    await p
    expect(blocks).toEqual(['data: {"delta":"hello"}', 'data: {"delta":"world"}'])
  })

  it('IPC 路: onBlock 返回 "error" 立即中止, 后续 block 不再回调', async () => {
    let onChunk, onDone, onError
    window.api = {
      http: {
        stream: vi.fn(() => Promise.resolve()),
        onChunk: (cb) => { onChunk = cb; return () => {} },
        onDone: (cb) => { onDone = cb; return () => {} },
        onError: (cb) => { onError = cb; return () => {} },
      },
    }
    const blocks = []
    const p = streamChat({
      body: {},
      signal: new AbortController().signal,
      onBlock: (b) => { blocks.push(b); return b.includes('bad') ? 'error' : undefined },
    })
    onChunk('1', 'data: {"delta":"ok"}\n\ndata: {"error":"bad"}\n\ndata: {"delta":"unreached"}\n\n')
    onDone()
    await p
    expect(blocks).toHaveLength(2) // 第三个 block 中止后不再回调
    expect(blocks[1]).toContain('bad')
  })

  it('IPC 路: onError reject', async () => {
    let onChunk, onDone, onError
    window.api = {
      http: {
        stream: vi.fn(() => Promise.resolve()),
        onChunk: (cb) => { onChunk = cb; return () => {} },
        onDone: (cb) => { onDone = cb; return () => {} },
        onError: (cb) => { onError = cb; return () => {} },
      },
    }
    const p = streamChat({ body: {}, signal: new AbortController().signal, onBlock: () => {} })
    onError('1', 'HTTP 500: boom')
    await expect(p).rejects.toThrow('boom')
  })

  it('IPC 路: stream() 本身 reject 时透传', async () => {
    window.api = {
      http: {
        stream: vi.fn(() => Promise.reject(new Error('stream init failed'))),
        onChunk: () => () => {}, onDone: () => () => {}, onError: () => () => {},
      },
    }
    await expect(
      streamChat({ body: {}, signal: new AbortController().signal, onBlock: () => {} }),
    ).rejects.toThrow('stream init failed')
  })

  it('IPC 路: abort signal 结束等待 (resolve)', async () => {
    let onChunk, onDone, onError
    window.api = {
      http: {
        stream: vi.fn(() => Promise.resolve()),
        onChunk: (cb) => { onChunk = cb; return () => {} },
        onDone: (cb) => { onDone = cb; return () => {} },
        onError: (cb) => { onError = cb; return () => {} },
      },
    }
    const ac = new AbortController()
    const p = streamChat({ body: {}, signal: ac.signal, onBlock: () => {} })
    ac.abort() // 用户点停止
    await expect(p).resolves.toBeUndefined()
  })

  it('浏览器回退路: fetch + ReadableStream 分帧, onBlock 逐块', async () => {
    // 无 window.api → 走 fetch 回退
    delete window.api
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

  it('浏览器回退路: 非 2xx 抛 HTTP 错', async () => {
    delete window.api
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({ ok: false, status: 500, text: async () => 'server down' })))
    await expect(
      streamChat({ body: {}, signal: new AbortController().signal, onBlock: () => {} }),
    ).rejects.toThrow('server down')
  })
})
