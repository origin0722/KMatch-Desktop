/**
 * 后端健康状态 store (F14)
 *
 * 此前 backend 健康只活在 StatusBar 组件本地 ref, 其他组件 (chat/diagnostics/工具) 在后端
 * 宕机时各自静默失败, 无统一态。抽为 store 作单一真相源: StatusBar 展示, AssistantPanel 据此
 * 禁用发送 + 提示, chat/_delegate 等可读 backendUp 做兜底文案。
 *
 * 健康检查: GET /api/health, 8s 轮询 (与原 StatusBar 行为一致)。
 */
import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import http from '@/api/index'

export const useBackendHealthStore = defineStore('backendHealth', () => {
  // null=未知, true=就绪, false=宕机
  const status = ref(null)
  const lastError = ref('')
  // Neo4j 状态: 'unknown'=后端未确认 / 'connected'=后端已连上图库 / 'down'=后端活着但图库不可用
  const neo4jStatus = ref('unknown')
  // 图存储后端 (embedded=嵌入式无 Docker / neo4j / ''=未知) — 端用户免 Docker 改造
  const graphStore = ref('')
  // 语义检索状态: ready / degraded / unavailable
  const semanticState = ref('')
  let _timer = null
  let _started = false

  const backendUp = computed(() => status.value === true)
  const backendUnknown = computed(() => status.value === null)
  const neo4jConnected = computed(() => neo4jStatus.value === 'connected')
  const label = computed(() => {
    if (status.value === null) return '后端检测中'
    return status.value ? '后端就绪' : '后端未起'
  })

  function applyHealth(body) {
    const b = body || {}
    const neo4j = b.neo4j || ''
    neo4jStatus.value = typeof neo4j === 'string' && neo4j.startsWith('connected')
      ? 'connected'
      : 'down'
    graphStore.value = b.graph_store || ''
    semanticState.value = b.semantic_search || 'unavailable'
  }

  async function check() {
    try {
      if (window.api?.http) {
        // Electron: 经 IPC 代理 (主进程 → 后端)
        const res = await window.api.http.request('GET', '/api/health')
        status.value = !!res.ok
        if (res.ok) {
          lastError.value = ''
          applyHealth(res.body)
        } else {
          lastError.value = `HTTP ${res.status}`
        }
      } else {
        // 浏览器 dev: 走 axios → Vite proxy。原实现无条件走 window.api,
        // 浏览器下直接 TypeError → 永远显示"后端未起" (实测)
        const ret = await http.get('/api/health')
        status.value = true
        lastError.value = ''
        applyHealth(ret.data)
      }
    } catch (e) {
      status.value = false
      lastError.value = e?.message || '连接失败'
      neo4jStatus.value = 'unknown'
    }
  }

  /** 启动轮询 (幂等, 多组件 onMounted 调用安全)。 */
  function start() {
    if (_started) return
    _started = true
    check()
    _timer = setInterval(check, 8000)
  }

  function stop() {
    if (_timer) { clearInterval(_timer); _timer = null }
    _started = false
  }

  return { status, backendUp, backendUnknown, neo4jStatus, neo4jConnected, graphStore, semanticState, label, lastError, check, start, stop }
})
