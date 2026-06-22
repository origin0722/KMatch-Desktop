/**
 * useChatStream — Chat SSE 传输层 composable (C1.3, 从 chat.js 抽出)
 *
 * 只管"把后端 SSE 流逐 block 交给调用方"，不碰消息状态/chunk 累积：
 *  - Electron: 走 window.api.http.stream IPC 代理 (onChunk/onDone/onError)
 *  - 浏览器 dev 回退: fetch + ReadableStream 直连 /api (经 Vite proxy → 8000)
 *
 * 两路共用同一个 \n\n 分帧逻辑（一个 block 可跨两次 reader.read()/IPC chunk）。
 * 调用方（chat store）经 onBlock 回调解析每个 block 并累积进消息 chunks。
 *
 * 这是 F4 的解法：SSE framing 逻辑从 chat.js + http-proxy 双处收口到单一源
 * （http-proxy 已负责把 fetch reader 拆成 block 转发，这里只做 IPC 侧缓冲 + 浏览器回退）。
 */

/** 是否有 Electron IPC（决定走 IPC 还是浏览器 fetch 回退）。 */
function hasIpc() {
  return typeof window !== 'undefined' && !!window.api?.http
}

/**
 * 流式请求 /api/chat/completions，逐 SSE block 回调。
 *
 * @param {Object} opts
 * @param {Object} opts.body      请求体（messages/stream/model/api_key/base_url/reasoning…）
 * @param {AbortSignal} opts.signal  abort 信号（用户点停止时触发；IPC 流无法真中断，仅结束等待）
 * @param {(block: string) => ('error'|void)} opts.onBlock  每个 SSE block 的回调；返回 'error' 中止
 * @returns {Promise<void>} resolve=正常结束, reject=传输错误
 */
export async function streamChat({ body, signal, onBlock }) {
  // ---- 浏览器 dev 回退: fetch + ReadableStream ----
  if (!hasIpc()) {
    const resp = await fetch('/api/chat/completions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal,
    })
    if (!resp.ok || !resp.body) {
      const text = await resp.text().catch(() => '')
      throw new Error(text || `HTTP ${resp.status}`)
    }
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const parts = buffer.split('\n\n')
      buffer = parts.pop()
      for (const b of parts) {
        if (onBlock(b) === 'error') return
      }
    }
    return
  }

  // ---- Electron: IPC SSE 代理 ----
  return new Promise((resolve, reject) => {
    let buffer = ''
    let settled = false
    const finish = () => {
      if (settled) return
      settled = true
      offChunk(); offDone(); offError()
      resolve()
    }
    const offChunk = window.api.http.onChunk((_reqId, block) => {
      if (settled) return
      buffer += block
      const parts = buffer.split('\n\n')
      buffer = parts.pop()
      for (const b of parts) {
        if (onBlock(b) === 'error') { finish(); return }
      }
    })
    const offDone = window.api.http.onDone(() => finish())
    const offError = window.api.http.onError((_reqId, err) => {
      if (settled) return
      settled = true
      offChunk(); offDone(); offError()
      reject(new Error(err || 'SSE 流失败'))
    })
    // 用户点停止: abort 时结束等待 (IPC 流无法真正中断, 后端流自然结束)
    signal.addEventListener('abort', () => finish())

    window.api.http.stream('/api/chat/completions', body).catch((e) => {
      if (settled) return
      settled = true
      offChunk(); offDone(); offError()
      reject(e)
    })
  })
}
