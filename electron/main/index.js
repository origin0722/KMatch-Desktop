/**
 * Electron 主进程入口
 * 阶段1: 窗口生命周期 + backend sidecar + IPC 注册(fs/workspace/http-proxy)
 * tray 常驻: 关闭窗口 → 隐藏到系统托盘 (进程仍在, 托盘图标可恢复/退出)
 */
import { app, BrowserWindow, Menu, Tray, ipcMain, nativeImage } from 'electron'
import path from 'path'
import { fileURLToPath } from 'url'

import { createMainWindow, setWindowOverlayTheme, appIconPath } from './window.js'
import { startBackend, stopBackend, getBackendHealth, restartBackend } from './backend-sidecar.js'
import { registerFsIpc } from './ipc/fs.js'
import { registerWorkspaceIpc } from './ipc/workspace.js'
import { registerHttpProxyIpc } from './ipc/http-proxy.js'
import { registerWindowIpc } from './ipc/window.js'
import { registerWatcherIpc, getWatcherController } from './ipc/watcher.js'
import { registerDockerIpc } from './ipc/docker.js'
import { registerProxyIpc } from './ipc/proxy.js'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// 全局窗口引用, 防止被 GC
let mainWindow = null
// 托盘常驻: 关闭窗口 → hide 而非 quit; isQuitting 置位后才允许真正退出
let tray = null
let isQuitting = false

function registerAllIpc() {
  registerFsIpc()
  // workspace 启停文件监听, 需 getMainWindow 推送事件到渲染层
  registerWorkspaceIpc({ getMainWindow: () => mainWindow })
  registerHttpProxyIpc()
  registerWindowIpc({ getMainWindow: () => mainWindow })
  registerWatcherIpc({ getMainWindow: () => mainWindow })
  registerDockerIpc()
  // Spec B 18-19 / issue-49: 网络代理落盘 + 后端重启
  registerProxyIpc(restartBackend)
  // 主题联动: 渲染层 theme store 通知窗口按钮配色 (亮/暗)
  ipcMain.handle('window:setOverlayTheme', (_e, dark) => {
    setWindowOverlayTheme(mainWindow, !!dark)
  })
}

/** 系统托盘 (桌面导航栏): 恢复窗口 / 退出; 关闭窗口时进程常驻。 */
function createTray() {
  if (tray) return
  try {
    const icon = nativeImage.createFromPath(appIconPath())
    tray = new Tray(icon.isEmpty() ? nativeImage.createEmpty() : icon)
    tray.setToolTip('KMatch·知链')
    tray.setContextMenu(Menu.buildFromTemplate([
      { label: '显示主界面', click: () => showMainWindow() },
      { type: 'separator' },
      { label: '退出', click: () => { isQuitting = true; app.quit() } },
    ]))
    tray.on('click', () => showMainWindow())
  } catch (e) {
    console.error('[main] 托盘创建失败 (不影响主流程):', e)
  }
}

function showMainWindow() {
  if (!mainWindow) return
  if (mainWindow.isMinimized()) mainWindow.restore()
  mainWindow.show()
  mainWindow.focus()
}

app.whenReady().then(async () => {
  Menu.setApplicationMenu(null)
  registerAllIpc()

  // 拉起后端 sidecar(开发期: 探测已运行则 attach, 否则尝试 spawn)
  startBackend().catch((err) => {
    console.error('[main] backend sidecar 启动失败, 业务功能将不可用:', err)
  })

  mainWindow = createMainWindow()
  // 关闭 → 隐藏到托盘 (进程常驻; 托盘「退出」或 app.quit 才真正退出)
  mainWindow.on('close', (e) => {
    if (!isQuitting) {
      e.preventDefault()
      mainWindow.hide()
    }
  })
  mainWindow.on('closed', () => {
    mainWindow = null
  })
  createTray()
})

app.on('window-all-closed', () => {
  // 托盘常驻模式: 窗口被隐藏而非关闭; 真正关闭意味着退出流程中, 直接 quit
  if (isQuitting) {
    stopBackend()
    app.quit()
  }
})

app.on('before-quit', async () => {
  isQuitting = true
  // 停文件监听 worker, 避免退出时未关闭的 watcher 句柄阻塞退出
  try { await getWatcherController(() => mainWindow).stop() } catch { /* ignore */ }
  await stopBackend()
})

// macOS: 点 dock 图标无窗口时重建
app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    mainWindow = createMainWindow()
  }
})
