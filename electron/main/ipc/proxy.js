/**
 * 网络代理配置落盘 + sidecar env 注入 (Spec B Task 18-19, issue-49)
 *
 * - proxy:setConfig  渲染层保存代理配置 → userData/proxy.json (原子写, 幂等)
 * - proxy:getConfig  读回 (sidecar spawn 时注入 env)
 * - backend:restart  重启后端 sidecar 使新代理生效
 *
 * 注入机制说明:
 *   Node fetch (http-proxy IPC 的 127.0.0.1 转发) 不读 env 代理 → 本地链路不受影响;
 *   Python sidecar (openai/httpx/Tavily) 读 HTTP(S)_PROXY/ALL_PROXY → 代理对 LLM/搜索出站生效。
 *   NO_PROXY 排除 127.0.0.1/localhost/::1 → Neo4j 与本地 Ollama 等不回环代理。
 */
import { app, ipcMain } from 'electron'
import fs from 'fs'
import path from 'path'

const DEFAULT_PROXY = { enabled: false, type: 'http', url: '', scope: 'llm' }

function proxyFile() {
  return path.join(app.getPath('userData'), 'proxy.json')
}

export function loadProxyConfig() {
  try {
    const raw = fs.readFileSync(proxyFile(), 'utf-8')
    return { ...DEFAULT_PROXY, ...JSON.parse(raw) }
  } catch {
    return { ...DEFAULT_PROXY }
  }
}

export function saveProxyConfig(config) {
  const file = proxyFile()
  fs.mkdirSync(path.dirname(file), { recursive: true })
  const data = { ...DEFAULT_PROXY, ...(config || {}) }
  // 原子写: 同目录 tmp + rename
  const tmp = `${file}.tmp`
  fs.writeFileSync(tmp, JSON.stringify(data, null, 2))
  fs.renameSync(tmp, file)
  return data
}

/** 由已落盘的代理配置构造 sidecar spawn env 追加项 (enabled+url 才注)。 */
export function proxyEnv() {
  const p = loadProxyConfig()
  if (!p.enabled || !p.url) return {}
  return {
    HTTP_PROXY: p.url,
    HTTPS_PROXY: p.url,
    ALL_PROXY: p.url,
    http_proxy: p.url,
    https_proxy: p.url,
    all_proxy: p.url,
    // 本地回环不代理 (Neo4j / 本地 LLM sidecar 互通)
    NO_PROXY: '127.0.0.1,localhost,::1',
    no_proxy: '127.0.0.1,localhost,::1',
  }
}

/** 注册代理 IPC; restartBackendFn 由 index.js 注入 (backend-sidecar.restartBackend)。 */
export function registerProxyIpc(restartBackendFn) {
  ipcMain.handle('proxy:setConfig', (_e, config) => ({
    ok: true,
    config: saveProxyConfig(config),
  }))
  ipcMain.handle('proxy:getConfig', () => loadProxyConfig())
  ipcMain.handle('backend:restart', async () => {
    try {
      const ready = typeof restartBackendFn === 'function' ? await restartBackendFn() : false
      return { ok: !!ready, ready: !!ready }
    } catch (e) {
      return { ok: false, ready: false, error: String(e) }
    }
  })
}
