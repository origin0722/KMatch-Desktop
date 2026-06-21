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
