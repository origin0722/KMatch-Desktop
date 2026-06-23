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

export const useBackendHealthStore = defineStore('backendHealth', () => {
  // null=未知, true=就绪, false=宕机
  const status = ref(null)
  const lastError = ref('')
  let _timer = null
  let _started = false

  const backendUp = computed(() => status.value === true)
  const backendUnknown = computed(() => status.value === null)
  const label = computed(() => {
    if (status.value === null) return '后端检测中'
    return status.value ? '后端就绪' : '后端未起'
  })

  async function check() {
    try {
      const res = await window.api.http.request('GET', '/api/health')
      status.value = !!res.ok
      if (res.ok) lastError.value = ''
      else lastError.value = `HTTP ${res.status}`
    } catch (e) {
      status.value = false
      lastError.value = e?.message || '连接失败'
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

  return { status, backendUp, backendUnknown, label, lastError, check, start, stop }
})
