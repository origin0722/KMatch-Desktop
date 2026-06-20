/**
 * HTTP 代理 IPC (阶段1)
 * 统一转发渲染层 → localhost:8000, 绕过 CORS + 单一审计点。
 * stream() 处理 SSE (POST + text/event-stream), 逐块转发给渲染层。
 *
 * 阶段1 实现 request; stream 供 SSE 测评用 (assess/stream)。
 */
import { ipcMain, BrowserWindow } from 'electron'

const BACKEND_URL = 'http://localhost:8000'

export function registerHttpProxyIpc() {
  ipcMain.handle('http:request', async (_e, method, urlPath, body, params) => {
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
      init.body = JSON.stringify(body)
    }
    try {
      const resp = await fetch(url.toString(), { ...init, signal: AbortSignal.timeout(60000) })
      const text = await resp.text()
      let parsed
      try { parsed = JSON.parse(text) } catch { parsed = text }
      return { status: resp.status, body: parsed, ok: resp.ok }
    } catch (err) {
      return { status: 0, body: { error: String(err) }, ok: false }
    }
  })

  // SSE 流式代理: 返回 reqId, 后续通过 'http:stream:chunk' 事件推 chunk
  ipcMain.handle('http:stream', async (event, urlPath, body) => {
    const reqId = `s${Date.now()}-${Math.floor(Math.random() * 1e6)}`
    const win = BrowserWindow.fromWebContents(event.sender)

    fetch(BACKEND_URL + urlPath, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}),
    })
      .then(async (resp) => {
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
