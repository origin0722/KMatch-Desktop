import { app, BrowserWindow, ipcMain } from 'electron'

export function createOpenDevToolsHandler({ app, BrowserWindow, getMainWindow }) {
  return (event) => {
    if (app.isPackaged) return false
    if (event.sender !== getMainWindow()?.webContents) return false
    const win = BrowserWindow.fromWebContents(event.sender)
    if (!win) return false
    win.webContents.openDevTools({ mode: 'detach' })
    return true
  }
}

export function registerWindowIpc({
  getMainWindow,
  appRef = app,
  BrowserWindowRef = BrowserWindow,
  ipcMainRef = ipcMain,
}) {
  ipcMainRef.handle('window:openDevTools', createOpenDevToolsHandler({
    app: appRef,
    BrowserWindow: BrowserWindowRef,
    getMainWindow,
  }))
}
