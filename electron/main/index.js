/**
 * Electron 主进程入口
 * 阶段1: 窗口生命周期 + backend sidecar + IPC 注册(fs/workspace/http-proxy)
 */
import { app, BrowserWindow } from 'electron'
import path from 'path'
import { fileURLToPath } from 'url'

import { createMainWindow } from './window.js'
import { startBackend, stopBackend, getBackendHealth } from './backend-sidecar.js'
import { registerFsIpc } from './ipc/fs.js'
import { registerWorkspaceIpc } from './ipc/workspace.js'
import { registerHttpProxyIpc } from './ipc/http-proxy.js'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// 全局窗口引用, 防止被 GC
let mainWindow = null

function registerAllIpc() {
  registerFsIpc()
  registerWorkspaceIpc()
  registerHttpProxyIpc()
}

app.whenReady().then(async () => {
  registerAllIpc()

  // 拉起后端 sidecar(开发期: 探测已运行则 attach, 否则尝试 spawn)
  startBackend().catch((err) => {
    console.error('[main] backend sidecar 启动失败, 业务功能将不可用:', err)
  })

  mainWindow = createMainWindow()
  mainWindow.on('closed', () => {
    mainWindow = null
  })
})

app.on('window-all-closed', () => {
  stopBackend()
  app.quit()
})

app.on('before-quit', async () => {
  await stopBackend()
})

// macOS: 点 dock 图标无窗口时重建
app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    mainWindow = createMainWindow()
  }
})
