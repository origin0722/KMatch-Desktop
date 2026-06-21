/**
 * 文件监听 Worker (阶段8, 借鉴 Apix worker_threads 方案)
 *
 * 跑在 Node worker_threads 内, 用 chokidar 监听项目目录, 主线程仅转发事件。
 * 选 worker_threads 因赛题泛化到其他 AI 垂直领域时, 监听含数据/模型文件的大目录
 * 会让主线程 IO 回调卡 UI, 隔离到 worker 保证主线程流畅。
 *
 * CJS 格式: electron-vite main 构建为 CJS, worker 作为额外入口一并 build 成 cjs,
 * Node worker_threads 直接 require 该路径运行。chokidar v4 支持 CJS require。
 *
 * 协议 (parentPort ↔ main):
 *   main → worker: { type:'start', root, ignoreNames:string[] } | { type:'stop' }
 *   worker → main: { type:'ready' }
 *                | { type:'change', event:{ kind:'add'|'change'|'unlink', path, absPath } }
 *                | { type:'error', message }
 *
 * 防抖: 150ms 内多次同路径变动合并一次推送 (awaitWriteFinish + 自防抖双保险)。
 */
const { parentPort, workerData } = require('worker_threads')
const chokidar = require('chokidar')
const path = require('path')

let watcher = null
let debounceTimers = new Map()
const DEBOUNCE_MS = 150

/** 构造 chokidar ignored 匹配 (复用 fs.js IGNORE_NAMES 思路, 传字符串数组避免循环依赖) */
function buildIgnored(ignoreNames) {
  const set = new Set(ignoreNames || [])
  return (filePath) => {
    if (!filePath) return false
    const parts = filePath.split(path.sep)
    return parts.some((p) => set.has(p))
  }
}

function emitChange(kind, absPath, root) {
  const rel = path.relative(root, absPath)
  parentPort?.postMessage({
    type: 'change',
    event: { kind, path: rel, absPath },
  })
}

/** 防抖: 同路径 150ms 内多次事件合并一次推送 */
function debouncedEmit(kind, absPath, root) {
  const key = absPath
  const existing = debounceTimers.get(key)
  if (existing) {
    // 已有 pending, 更新 kind (unlink 优先, 避免删除后报 change)
    if (kind === 'unlink') existing.kind = 'unlink'
    return
  }
  const entry = { kind, absPath }
  debounceTimers.set(key, entry)
  setTimeout(() => {
    debounceTimers.delete(key)
    emitChange(entry.kind, entry.absPath, root)
  }, DEBOUNCE_MS)
}

function start(root, ignoreNames) {
  if (watcher) stop()
  const ignored = buildIgnored(ignoreNames)
  watcher = chokidar.watch(root, {
    ignored,
    ignoreInitial: true,
    awaitWriteFinish: { stabilityThreshold: 150, pollInterval: 50 },
    persistent: true,
  })
  watcher.on('ready', () => {
    parentPort?.postMessage({ type: 'ready' })
  })
  watcher.on('add', (p) => debouncedEmit('add', p, root))
  watcher.on('change', (p) => debouncedEmit('change', p, root))
  watcher.on('unlink', (p) => debouncedEmit('unlink', p, root))
  // 目录增删也推 (refreshTree 需要重建树)
  watcher.on('addDir', (p) => debouncedEmit('add', p, root))
  watcher.on('unlinkDir', (p) => debouncedEmit('unlink', p, root))
  watcher.on('error', (err) => {
    parentPort?.postMessage({ type: 'error', message: err?.message || String(err) })
  })
}

function stop() {
  if (watcher) {
    try { watcher.close() } catch { /* ignore */ }
    watcher = null
  }
  for (const key of debounceTimers.keys()) {
    clearTimeout(debounceTimers.get(key))
  }
  debounceTimers = new Map()
}

// ---- 主消息循环 ----
if (parentPort) {
  parentPort.on('message', (msg) => {
    if (!msg || typeof msg !== 'object') return
    if (msg.type === 'start') {
      try {
        start(msg.root, msg.ignoreNames)
      } catch (e) {
        parentPort.postMessage({ type: 'error', message: e?.message || String(e) })
      }
    } else if (msg.type === 'stop') {
      stop()
    }
  })
}

// workerData 可带初始 start 指令 (可选)
if (workerData && workerData.type === 'start') {
  start(workerData.root, workerData.ignoreNames)
}
