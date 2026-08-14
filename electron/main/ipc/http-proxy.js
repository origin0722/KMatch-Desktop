/**
 * HTTP 代理 IPC (阶段1)
 * 统一转发渲染层 → 后端 8000, 绕过 CORS + 单一审计点。
 * stream() 处理 SSE (POST + text/event-stream), 逐块转发给渲染层。
 *
 * 阶段1 实现 request; stream 供 SSE 测评用 (assess/stream)。
 */
import { ipcMain, BrowserWindow } from 'electron'

// 127.0.0.1 而非 localhost: 本机 localhost 优先解析 ::1, 后端只绑 IPv4,
// 走 localhost 会随机撞 ::1 连接拒绝 → 渲染层 API 间歇性失败 (实测)
const BACKEND_URL = 'http://127.0.0.1:8000'

export function registerHttpProxyIpc() {
  ipcMain.handle('http:request', async (_e, method, urlPath, body, params, opts) => {
    const url = new URL(BACKEND_URL + urlPath)
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        if (v !== undefined && v !== null) url.searchParams.set(k, v)
      }
    }
    const init = {
      method: (method || 'GET').toUpperCase(),
      headers: { 'Content-Type': 'application/json' },
    }
    if (body !== undefined && body !== null && init.method !== 'GET') {
      // body 可能是对象(直调 window.api.http.request)或 JSON 字符串(axios adapter 已被
      // transformRequest 序列化);字符串直接用,避免双重序列化使后端收到 str 而非 dict -> 422
      init.body = typeof body === 'string' ? body : JSON.stringify(body)
    }
    // 阶段4/#30: code_test、feedback 等 LLM 逐节点生成常超 60s。
    // 默认放宽到 120s (连接拒绝/后端宕机仍秒失败, 不受影响), 调用方可经 opts.timeoutMs 进一步放宽。
    const timeoutMs = (opts && typeof opts.timeoutMs === 'number') ? opts.timeoutMs : 120000
    try {
      const resp = await fetch(url.toString(), { ...init, signal: AbortSignal.timeout(timeoutMs) })
      const text = await resp.text()
      let parsed
      try { parsed = JSON.parse(text) } catch { parsed = text }
      return { status: resp.status, body: parsed, ok: resp.ok }
    } catch (err) {
      return { status: 0, body: { error: String(err) }, ok: false }
    }
  })

  // SSE 流式代理: 返回 reqId, 后续通过 'http:stream:chunk' 事件推 chunk。
  // F3: 渲染层可传 reqId (并发多流时按 reqId 过滤, 避免串扰); 未传则主进程生成。
  ipcMain.handle('http:stream', async (event, urlPath, body, reqId) => {
    reqId = reqId || `s${Date.now()}-${Math.floor(Math.random() * 1e6)}`
    const win = BrowserWindow.fromWebContents(event.sender)

    fetch(BACKEND_URL + urlPath, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}),
    })
      .then(async (resp) => {
        // 后端非 200 (如 422/500/503): 旧实现只静默不读 body, 渲染层永远等不到 done/error。
        // 现读 body 文本经 'http:stream:error' 回传, 让 chat 能提示真实原因。
        if (!resp.ok || !resp.body) {
          const text = await resp.text().catch(() => '')
          if (win && !win.isDestroyed()) win.webContents.send('http:stream:error', reqId, `HTTP ${resp.status}: ${text.slice(0, 200)}`)
          return
        }
        const reader = resp.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          // 按 SSE 事件块 (\n\n) 切分
          let idx
          while ((idx = buffer.indexOf('\n\n')) >= 0) {
            const block = buffer.slice(0, idx)
            buffer = buffer.slice(idx + 2)
            if (win && !win.isDestroyed()) {
              win.webContents.send('http:stream:chunk', reqId, block)
            }
          }
        }
        if (win && !win.isDestroyed()) win.webContents.send('http:stream:done', reqId)
      })
      .catch((err) => {
        if (win && !win.isDestroyed()) win.webContents.send('http:stream:error', reqId, String(err))
      })

    return reqId
  })
}
