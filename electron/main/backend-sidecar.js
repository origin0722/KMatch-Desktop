/**
 * 后端 sidecar 管理 (Python FastAPI + uvicorn)
 * - 开发期: attach 优先 (探测 8000 已在跑则复用), 否则 spawn `python -m uvicorn app.main:app`
 * - 生产期 (app.isPackaged): spawn PyInstaller 产物 resources/backend/KMatchBackend.exe
 *
 * Neo4j 仍由用户用 Docker 起 (scripts/start_all.py), 本模块不拉 Neo4j。
 */
import { spawn } from 'child_process'
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'
import { app } from 'electron'
import { proxyEnv } from './ipc/proxy.js'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
// 127.0.0.1 而非 localhost: 本机 localhost 优先解析 ::1, 后端只绑 IPv4 (uvicorn --host 127.0.0.1),
// Node fetch 走 localhost 会随机撞 ::1 连接拒绝 → 健康检查误判后端未起 (实测)
const BACKEND_URL = 'http://127.0.0.1:8000'
const HEALTH_PATH = '/api/health'

let backendProc = null

async function fetchHealth() {
  try {
    const resp = await fetch(`${BACKEND_URL}${HEALTH_PATH}`, { signal: AbortSignal.timeout(2000) })
    return resp.ok
  } catch {
    return false
  }
}

async function waitForReady(maxMs = 30000) {
  const start = Date.now()
  while (Date.now() - start < maxMs) {
    if (await fetchHealth()) return true
    await new Promise((r) => setTimeout(r, 1000))
  }
  return false
}

/** 开发期: 定位 backend 目录 (含 app/main.py, uvicorn cwd) */
function resolveDevBackendDir() {
  // out/main/ (打包) 或 electron/main/ (dev 源) → 仓库根 → backend
  const repoRoot = path.resolve(__dirname, '..', '..')
  return path.join(repoRoot, 'backend')
}

/** 生产期: 定位 PyInstaller 产物 (electron-builder extraResources → resources/backend) */
function resolvePackagedBackendExe() {
  // process.resourcesPath = 安装目录/resources/
  return path.join(process.resourcesPath, 'backend', 'KMatchBackend', 'KMatchBackend.exe')
}

function spawnBackend() {
  // 生产判定: 不再盲信 app.isPackaged (electron-vite dev 下部分环境仍为 true, 会误走
  // KMatchBackend.exe 分支 → ENOENT 崩溃, 实测黑屏根因)。改为"exe 真实存在"才算生产。
  const exe = resolvePackagedBackendExe()
  const usePackaged = app.isPackaged && fs.existsSync(exe)
  const cwd = usePackaged ? path.dirname(exe) : resolveDevBackendDir()

  // PYTHONIOENCODING=utf-8: 后端日志含 ✅/❌ 等字符, 管道下 Python 默认按 GBK 编码会
  // UnicodeEncodeError 刷 "Logging error" 噪音 (实测)。
  // issue-49: 注入已落盘的代理 env (Spec B 18-19), 使 LLM/搜索出站走代理; NO_PROXY 排除本地回环
  const env = { ...process.env, PYTHONIOENCODING: 'utf-8', ...proxyEnv() }
  // 端用户免 Docker (ADR-0008): 安装包 resources/data 只读, 嵌入式运行时可变数据
  // (掌握状态/项目图谱/向量缓存) 落用户 appData 可写目录, 否则 Program Files 安装会写失败
  if (usePackaged) {
    env.KMATCH_LOCAL_DIR = path.join(app.getPath('userData'), 'data', 'local')
  }
  const proc = usePackaged
    ? spawn(exe, [], { cwd, stdio: ['ignore', 'pipe', 'pipe'], env })
    : spawn(process.env.PYTHON || 'python', [
        '-m', 'uvicorn', 'app.main:app',
        '--host', '127.0.0.1', '--port', '8000',
      ], { cwd, stdio: ['ignore', 'pipe', 'pipe'], env })

  // 必须挂 'error' 处理器: spawn 目标不存在 (ENOENT) 时若不加, 会触发未捕获异常,
  // 直接弹 "A JavaScript error occurred in the main process" + 黑屏 (实测根因)。
  proc.on('error', (err) => {
    console.error(`[backend] spawn 失败 (${usePackaged ? exe : 'python -m uvicorn'}): ${err.message}`)
    backendProc = null
  })
  proc.stdout?.on('data', (d) => process.stdout.write(`[backend] ${d}`))
  proc.stderr?.on('data', (d) => process.stderr.write(`[backend] ${d}`))
  proc.on('exit', (code) => {
    console.log(`[backend] ${usePackaged ? 'KMatchBackend' : 'uvicorn'} 退出, code=${code}`)
    backendProc = null
  })
  return proc
}

export async function startBackend() {
  // 1. attach 优先: 探测是否已有后端在跑 (用户手动起的或上次遗留)
  if (await fetchHealth()) {
    console.log('[backend] 检测到已在运行, attach 复用')
    return
  }
  // 2. spawn
  const exe = resolvePackagedBackendExe()
  const usePackaged = app.isPackaged && fs.existsSync(exe)
  console.log(`[backend] 启动 sidecar (${usePackaged ? 'packaged exe' : 'uvicorn dev'})...`)
  backendProc = spawnBackend()
  const ready = await waitForReady()
  if (ready) {
    console.log('[backend] 就绪 ✓')
  } else {
    const hint = usePackaged
      ? '打包后端启动失败 (检查 resources/backend/KMatchBackend.exe 是否存在)'
      : '请确认 backend 依赖已装 (pip install -r requirements.txt) + .env 已配 + Neo4j 已起'
    console.warn(`[backend] 30s 内未就绪, 业务功能不可用。${hint}`)
  }
}

export async function stopBackend() {
  if (backendProc) {
    console.log('[backend] 停止 sidecar')
    backendProc.kill()
    backendProc = null
  }
}

/** issue-49: 重启 sidecar (改代理后生效); 返回是否就绪。 */
export async function restartBackend() {
  if (backendProc) {
    backendProc.kill()
    backendProc = null
  }
  // 等 Windows 下端口释放后, 先做 attach 探测 (避免刚 kill 的旧进程被误探测)
  await new Promise((r) => setTimeout(r, 800))
  if (await fetchHealth()) {
    console.log('[backend] restart: 检测到已有后端, attach 复用')
    return true
  }
  const exe = resolvePackagedBackendExe()
  const usePackaged = app.isPackaged && fs.existsSync(exe)
  console.log(`[backend] restart sidecar (${usePackaged ? 'packaged exe' : 'uvicorn dev'})...`)
  backendProc = spawnBackend()
  const ready = await waitForReady()
  console.log(ready ? '[backend] restart 就绪 ✓' : '[backend] restart 30s 未就绪, 业务功能不可用')
  return ready
}

export async function getBackendHealth() {
  return { ok: await fetchHealth(), url: BACKEND_URL }
}

