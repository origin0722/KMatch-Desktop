/**
 * 场景：DevTools IPC 安全守卫（主进程侧）。
 *
 * createOpenDevToolsHandler 是 window:openDevTools IPC 的主进程 handler。
 * 安全约束：打包后的生产构建（app.isPackaged=true）必须拒绝打开 DevTools，
 * 防止终端用户调出开发者工具。开发模式（isPackaged=false）才允许。
 * handler 被抽成可注入依赖（app/BrowserWindow/getMainWindow），故可直接单测，无需起 Electron。
 */
import { describe, it, expect } from 'vitest'
import { createOpenDevToolsHandler } from '../../../electron/main/ipc/window.js'

describe('window DevTools IPC guard', () => {
  it('does not expose DevTools opening in packaged builds', () => {
    const handler = createOpenDevToolsHandler({
      app: { isPackaged: true },
      BrowserWindow: { fromWebContents: () => ({ webContents: { openDevTools: () => {} } }) },
      getMainWindow: () => ({ webContents: {} }),
    })

    expect(handler({ sender: {} })).toBe(false)
  })

  it('only accepts requests from the current main window webContents', () => {
    const currentWebContents = { openDevTools: () => {} }
    const staleWebContents = { openDevTools: () => {} }
    const handler = createOpenDevToolsHandler({
      app: { isPackaged: false },
      BrowserWindow: { fromWebContents: () => ({ webContents: currentWebContents }) },
      getMainWindow: () => ({ webContents: currentWebContents }),
    })

    expect(handler({ sender: staleWebContents })).toBe(false)
  })

  it('opens detached DevTools for the current main window in development', () => {
    const opened = []
    const currentWebContents = {
      openDevTools: (options) => opened.push(options),
    }
    const handler = createOpenDevToolsHandler({
      app: { isPackaged: false },
      BrowserWindow: { fromWebContents: () => ({ webContents: currentWebContents }) },
      getMainWindow: () => ({ webContents: currentWebContents }),
    })

    expect(handler({ sender: currentWebContents })).toBe(true)
    expect(opened).toEqual([{ mode: 'detach' }])
  })
})
