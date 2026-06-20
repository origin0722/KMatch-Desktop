/**
 * BrowserWindow 创建
 * dev: 加载 electron-vite 渲染层 dev server (5173)
 * prod: 加载打包后 file:// 资源
 */
import { app, BrowserWindow, shell } from 'electron'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

export function createMainWindow() {
  const win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 960,
    minHeight: 600,
    show: false,
    backgroundColor: '#1e1e1e',
    title: 'KMatch·知链',
    webPreferences: {
      // electron-vite: preload 编译输出到 out/preload/ (CJS: index.js)
      preload: path.join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false, // preload 需用 contextBridge; sandbox:false 让 preload 能用 require/process
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

  if (app.isPackaged) {
    win.loadFile(path.join(__dirname, '../renderer/index.html'))
  } else {
    // electron-vite dev: 渲染层 dev server (端口可能自动换, 用注入的 URL)
    const url = process.env.ELECTRON_RENDERER_URL || 'http://localhost:5173'
    win.loadURL(url)
    win.webContents.openDevTools({ mode: 'detach' })
  }

  return win
}
