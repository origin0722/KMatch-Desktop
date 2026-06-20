/**
 * 后端 sidecar 管理 (Python FastAPI + uvicorn)
 * 阶段1: 开发期 attach 优先 — 探测 localhost:8000 是否已在运行, 是则复用;
 *        否则尝试 spawn uvicorn 子进程并守候。生产期 spawn 打包后的可执行体。
 *
 * Neo4j 仍由用户用 Docker 起 (scripts/start_all.py), 本模块不拉 Neo4j。
 */
import { spawn } from 'child_process'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const BACKEND_URL = 'http://localhost:8000'
const HEALTH_PATH = '/api/health'

let backendProc = null
let healthPollTimer = null

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

/**
 * 定位 backend 目录 (含 app/main.py 的目录, uvicorn 以此为 cwd)
 */
function resolveBackendDir() {
  // electron/main/ → 仓库根 → backend
  const repoRoot = path.resolve(__dirname, '..', '..')
  return path.join(repoRoot, 'backend')
}

function spawnUvicorn() {
  const cwd = resolveBackendDir()
  // 开发期: 直接用系统 python -m uvicorn (假定用户已 pip install -r requirements.txt)
  const proc = spawn(process.env.PYTHON || 'python', [
    '-m', 'uvicorn', 'app.main:app',
    '--host', '127.0.0.1', '--port', '8000',
  ], { cwd, stdio: ['ignore', 'pipe', 'pipe'] })

  proc.stdout?.on('data', (d) => process.stdout.write(`[backend] ${d}`))
  proc.stderr?.on('data', (d) => process.stderr.write(`[backend] ${d}`))
  proc.on('exit', (code) => {
    console.log(`[backend] uvicorn 退出, code=${code}`)
    backendProc = null
  })
  return proc
}

export async function startBackend() {
  // 1. 先探测是否已有后端在跑 (用户手动起的或上次遗留)
  if (await fetchHealth()) {
    console.log('[backend] 检测到已在运行, attach 复用')
    return
  }
  // 2. spawn
  console.log('[backend] 启动 uvicorn sidecar...')
  backendProc = spawnUvicorn()
  const ready = await waitForReady()
  if (ready) {
    console.log('[backend] 就绪 ✓')
  } else {
    console.warn('[backend] 30s 内未就绪, 业务功能不可用 (请确认 backend 依赖已装 + .env 已配)')
  }
}

export async function stopBackend() {
  if (healthPollTimer) clearInterval(healthPollTimer)
  if (backendProc) {
    console.log('[backend] 停止 uvicorn sidecar')
    backendProc.kill()
    backendProc = null
  }
}

export async function getBackendHealth() {
  return { ok: await fetchHealth(), url: BACKEND_URL }
}
