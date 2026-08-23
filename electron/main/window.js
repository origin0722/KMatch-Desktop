/**
 * BrowserWindow 创建
 * dev: 加载 electron-vite 渲染层 dev server (5173)
 * prod: 加载打包后 file:// 资源
 */
import { app, BrowserWindow, shell } from 'electron'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

/** 应用图标 (dev: 项目根/electron/assets; 打包: asar 内同路径)。 */
export function appIconPath() {
  return path.join(app.getAppPath(), 'electron/assets/icon.png')
}

/**
 * issue: 白/暗主题下窗口按钮 (titleBarOverlay) 颜色联动。
 * 渲染层 theme store 调用 IPC window:setOverlayTheme → 主进程此函数。
 */
export function setWindowOverlayTheme(win, dark) {
  if (process.platform !== 'win32' || !win) return
  try {
    win.setTitleBarOverlay(dark
      ? { color: '#1a1817', symbolColor: '#c8c5c2', height: 32 }
      : { color: '#f2f1ef', symbolColor: '#44403e', height: 32 })
  } catch { /* 旧版 Electron 无此 API, 忽略 */ }
}

export function createMainWindow() {
  const win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 960,
    minHeight: 600,
    show: false,
    backgroundColor: '#1e1e1e',
    title: 'KMatch·知链',
    icon: appIconPath(), // dev/任务栏图标 (打包后 exe 自带同款)
    // issue-85: 去掉顶部黑色标题长框 — 隐藏原生标题栏, Windows 用 overlay 悬浮原生命令按钮
    titleBarStyle: 'hidden',
    ...(process.platform === 'win32'
      ? { titleBarOverlay: { color: '#1a1817', symbolColor: '#c8c5c2', height: 32 } }
      : {}),
    webPreferences: {
      // electron-vite: preload 编译输出到 out/preload/ (CJS: index.js)
      preload: path.join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      nodeIntegration: false,
      // #60 加固: preload 仅用 electron 的 contextBridge/ipcRenderer, 与 sandbox:true 兼容
      // (sandboxed preload 可 require electron 子集, 无需 Node 内置模块)。
      // 渲染层另经 CSP meta 收紧 (frontend/index.html)。
      sandbox: true,
    },
  })

  win.once('ready-to-show', () => { console.log('[window] ready-to-show'); win.show() })

  // 渲染层加载时序诊断 (阶段1 调试)
  win.webContents.on('did-start-loading', () => console.log('[wc] did-start-loading'))
  win.webContents.on('did-stop-loading', () => console.log('[wc] did-stop-loading'))
  win.webContents.on('dom-ready', () => console.log('[wc] dom-ready'))
  win.webContents.on('did-finish-load', () => console.log('[wc] did-finish-load'))
  win.webContents.on('console-message', (_e, _lvl, msg, line, src) => {
    console.log(`[renderer] ${msg}${src ? ` (${src}:${line})` : ''}`)
  })
  win.webContents.on('did-fail-load', (_e, code, desc, url) => {
    console.error(`[wc] did-fail-load code=${code} desc=${desc} url=${url}`)
  })
  win.webContents.on('render-process-gone', (_e, d) => {
    console.error('[wc] render-process-gone', JSON.stringify(d))
  })
  win.webContents.on('preload-error', (_e, p, err) => {
    console.error(`[wc] preload-error ${p}: ${err}`)
  })
  win.on('closed', () => console.log('[window] closed'))
  win.on('unresponsive', () => console.log('[window] unresponsive'))
  win.on('close', (e) => {
    console.log('[window] close-event (default prevented:', e.defaultPrevented, ')')
  })

  // 外链在系统浏览器打开, 不在应用内导航
  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url)
    return { action: 'deny' }
  })

  // dev 判断: 优先 ELECTRON_RENDERER_URL (electron-vite dev 必注入, packaged 不注入);
  // 不只靠 app.isPackaged (部分环境下 dev 模式 isPackaged 仍为 true, 会导致 loadFile 黑屏)。
  const rendererUrl = process.env.ELECTRON_RENDERER_URL
  if (rendererUrl) {
    win.loadURL(rendererUrl)
    win.webContents.openDevTools({ mode: 'detach' })
  } else if (app.isPackaged) {
    win.loadFile(path.join(__dirname, '../renderer/index.html'))
  } else {
    // 兜底 dev (无 ELECTRON_RENDERER_URL, 非 packaged): 用默认 dev server
    win.loadURL('http://localhost:5173')
    win.webContents.openDevTools({ mode: 'detach' })
  }

  return win
}
