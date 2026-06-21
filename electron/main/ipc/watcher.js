/**
 * 文件监听 IPC + 控制器 (阶段8)
 *
 * 主线程侧: 管理 worker_threads 生命周期, 把 worker 推送的 change 事件转发到渲染进程。
 * 监听逻辑抽成纯工厂 createWatcherController (依赖注入 Worker 构造器 + getMainWindow),
 * 便于单测 (传 fake), 对齐 window-ipc.test.js 验证过的纯工厂模式。
 *
 * 生命周期: workspace.js openProject/setRoot 成功后 → watcherController.start(root);
 *           关项目 / app quit → stop()。渲染层只订阅 fs:watch:change 事件, 不主动启停。
 */
import { ipcMain } from 'electron'
import { Worker } from 'worker_threads'
import { fileURLToPath } from 'url'
import path from 'path'
import { IGNORE_NAMES } from './fs.js'

// 构建后本模块被 bundle 进 out/main/index.js, worker 作为额外入口 build 到 out/main/watcher-worker.cjs。
// import.meta.url 在 CJS 输出里转成基于 __filename 的路径, 运行时 __dirname = out/main,
// 故 worker 与本模块运行时同目录。用同目录引用。
const __dirname = path.dirname(fileURLToPath(import.meta.url))
const WORKER_PATH = path.resolve(__dirname, 'watcher-worker.js')

/**
 * 纯工厂: 创建 watcher 控制器。
 * @param {object} opts
 * @param {Function} opts.Worker - Worker 构造器 (注入便于单测)
 * @param {string} opts.workerPath - Worker 入口路径
 * @param {Function} opts.getMainWindow - () => BrowserWindow | null
 * @param {Function} opts.now - 时间函数 (注入便于单测)
 */
export function createWatcherController({
  Worker: WorkerCtor = Worker,
  workerPath = WORKER_PATH,
  getMainWindow,
  now = Date.now,
} = {}) {
  let worker = null
  let currentRoot = null

  function pushToRenderer(event) {
    const win = getMainWindow?.()
    if (win && !win.isDestroyed()) {
      win.webContents.send('fs:watch:change', event)
    }
  }

  async function start(root) {
    if (!root) return false
    // 已在监听同根: 不重启
    if (worker && currentRoot === root) return true
    // 监听根变了: 先停旧的
    if (worker) await stop()

    try {
      worker = new WorkerCtor(workerPath)
    } catch (e) {
      worker = null
      throw e
    }
    worker.on('message', (msg) => {
      if (!msg || typeof msg !== 'object') return
      if (msg.type === 'change') {
        pushToRenderer(msg.event)
      } else if (msg.type === 'error') {
        // worker 内部错误不致命, 日志即可 (主线程继续运行)
        console.error('[watcher-worker]', msg.message)
      }
    })
    worker.on('error', (err) => {
      console.error('[watcher-worker] error:', err?.message || err)
    })
    worker.on('exit', (code) => {
      if (code !== 0 && worker) {
        console.warn('[watcher-worker] 非正常退出 code=' + code)
      }
      worker = null
      currentRoot = null
    })
    worker.postMessage({
      type: 'start',
      root,
      ignoreNames: [...IGNORE_NAMES],
    })
    currentRoot = root
    return true
  }

  async function stop() {
    if (!worker) return
    try {
      worker.postMessage({ type: 'stop' })
      await worker.terminate()
    } catch { /* ignore */ }
    worker = null
    currentRoot = null
  }

  function isActive() {
    return worker !== null
  }

  return { start, stop, isActive }
}

/** 单例控制器 (主进程内唯一一份) */
let _controller = null

export function getWatcherController(getMainWindow) {
  if (!_controller) {
    _controller = createWatcherController({ getMainWindow })
  }
  return _controller
}

/**
 * 注册 IPC: 渲染层可主动启停 (兜底, 主要靠 openProject 自动 start)。
 * getMainWindow 注入, 对齐 registerWindowIpc({getMainWindow}) 风格。
 */
export function registerWatcherIpc({ getMainWindow }) {
  const controller = getWatcherController(getMainWindow)

  ipcMain.handle('fs:watch:start', async (_e, root) => {
    if (!root) return { ok: false, error: '缺少 root' }
    try {
      await controller.start(root)
      return { ok: true }
    } catch (e) {
      return { ok: false, error: e?.message || String(e) }
    }
  })

  ipcMain.handle('fs:watch:stop', async () => {
    await controller.stop()
    return { ok: true }
  })
}
