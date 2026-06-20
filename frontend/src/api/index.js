/**
 * KMatch 前端 API 层 — Axios 实例 + 统一拦截器
 *
 * 双环境适配:
 *  - Electron (window.api 存在): 自定义 adapter 经 IPC 代理 → main → localhost:8000,
 *    绕过 CORS, 渲染层不直连后端。
 *  - 浏览器 dev (无 window.api): fallback 走 Vite proxy (/api → 8000)。
 */
import axios from 'axios'
import { ElMessage } from 'element-plus'

const hasIpc = typeof window !== 'undefined' && !!window.api?.http

const http = axios.create({
  baseURL: '',
  timeout: 60_000, // LLM 调用可能 15~30 秒
  headers: { 'Content-Type': 'application/json' },
})

// ============================================================
// 自定义 adapter — Electron 经 IPC 代理后端
// ============================================================
if (hasIpc) {
  http.defaults.adapter = async (config) => {
    const method = (config.method || 'get').toLowerCase()
    const url = config.url || ''
    const body = config.data
    const params = config.params
    const res = await window.api.http.request(method, url, body, params)
    const data = res.body
    if (!res.ok) {
      const err = new Error(`HTTP ${res.status}`)
      err.response = { status: res.status, data }
      throw err
    }
    return {
      data,
      status: res.status,
      statusText: 'OK',
      headers: {},
      config,
      request: {},
    }
  }
}

// ============================================================
// 请求拦截器 — 开发期打印日志
// ============================================================
http.interceptors.request.use(
  (config) => {
    if (import.meta.env.DEV) {
      console.debug(`[API] ${config.method?.toUpperCase()} ${config.url}`)
    }
    return config
  },
  (error) => Promise.reject(error),
)

// ============================================================
// 响应拦截器 — 统一错误处理
// ============================================================
http.interceptors.response.use(
  (response) => {
    // 直接返回 data，调用方无需 .data
    return response.data
  },
  (error) => {
    const status = error.response?.status
    const detail = error.response?.data?.detail || error.message

    if (status === 503) {
      ElMessage.error(`服务未就绪：${detail}`)
    } else if (status === 500) {
      ElMessage.error(`服务器错误：${detail}`)
    } else if (status === 422) {
      ElMessage.error(`参数错误：${detail}`)
    } else if (status === 404) {
      // submit/feedback 的 session_id 失效（后端 LRU 缓存被挤掉或服务重启）会落到这里。
      // 业务方可在调用处单独 catch 404 引导用户重新发起 assess。
      ElMessage.error(`资源不存在：${detail || '会话已失效，请重新开始测评'}`)
    } else if (error.code === 'ECONNABORTED') {
      ElMessage.error('请求超时，请检查后端服务是否启动')
    } else {
      ElMessage.error(`网络错误：${detail}`)
    }

    return Promise.reject(error)
  },
)

export default http
