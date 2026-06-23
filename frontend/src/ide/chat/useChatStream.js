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
 * F3: 渲染层生成 reqId 并按之过滤 IPC 事件——chat 与 diagnostics 评估并发时各自只收自己的流。
 * F2: onBlock 返回 Error (流内错误) 时, streamChat reject 该错误, 统一错误路径 (不再 200+error 仍 resolve)。
 */

/** 是否有 Electron IPC（决定走 IPC 还是浏览器 fetch 回退）。 */
function hasIpc() {
  return typeof window !== 'undefined' && !!window.api?.http
}

/** 生成唯一 reqId (渲染层, 用于并发流过滤)。 */
function newReqId() {
  return `s${Date.now()}-${Math.floor(Math.random() * 1e6)}`
}

/**
 * 流式请求 /api/chat/completions，逐 SSE block 回调。
 *
 * @param {Object} opts
 * @param {Object} opts.body      请求体（messages/stream/model/api_key/base_url/reasoning…）
 * @param {AbortSignal} opts.signal  abort 信号（用户点停止时触发；IPC 流无法真中断，仅结束等待）
 * @param {(block: string) => (Error|void)} opts.onBlock  每个 SSE block 的回调；返回 Error 实例中止并 reject (其他返回值忽略)
 * @returns {Promise<void>} resolve=正常结束, reject=传输错误或流内错误
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
        const r = onBlock(b)
        if (r instanceof Error) throw r // F2: 流内错误 → reject
      }
    }
    return
  }

  // ---- Electron: IPC SSE 代理 ----
  // http-proxy 已按 \n\n 分帧, 每个 http:stream:chunk 就是一个完整 SSE block (无 \n\n 定界符);
  // 渲染层不再二次缓冲/拆分, 直接交 onBlock。旧实现二次 split('\n\n') 永不产出 → 流式回执空 (修)。
  const reqId = newReqId()
  return new Promise((resolve, reject) => {
    let settled = false
    const finish = () => {
      if (settled) return
      settled = true
      offChunk(); offDone(); offError()
      resolve()
    }
    const fail = (err) => {
      if (settled) return
      settled = true
      offChunk(); offDone(); offError()
      reject(err)
    }
    // F3: 仅处理本流 reqId 的事件, 忽略其他并发流
    const offChunk = window.api.http.onChunk((rid, block) => {
      if (settled || rid !== reqId) return
      const r = onBlock(block)
      if (r instanceof Error) { fail(r); return } // F2: 流内错误 → reject
    })
    const offDone = window.api.http.onDone((rid) => { if (rid === reqId) finish() })
    const offError = window.api.http.onError((rid, err) => {
      if (rid !== reqId) return
      fail(new Error(err || 'SSE 流失败'))
    })
    // 用户点停止: abort 时结束等待 (IPC 流无法真正中断, 后端流自然结束)
    signal.addEventListener('abort', () => finish())

    window.api.http.stream('/api/chat/completions', body, reqId).catch((e) => fail(e))
  })
}
