/**
 * 主题 store — 亮/暗切换 (TRAE 风格)
 * 控制 <html> 的 dark class, Element Plus 暗色 CSS + IDE 自定义组件变量统一跟随。
 * 持久化到 localStorage, 默认跟随系统 prefers-color-scheme。
 */
import { ref, watch } from 'vue'
import { defineStore } from 'pinia'

const STORAGE_KEY = 'kmatch-theme'

function detectInitial() {
  const saved = localStorage.getItem(STORAGE_KEY)
  if (saved === 'dark' || saved === 'light') return saved
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export const useThemeStore = defineStore('theme', () => {
  const mode = ref(detectInitial())
  // issue-82: 强调色/撞色方案 (default=靛蓝+琥珀 / teal=深青+珊瑚 / violet=紫罗兰+青柠), localStorage 持久化
  // v1.1.0: 默认皮肤改为「深青珊瑚」(teal) — 与品牌色一致; 旧用户已存 kmatch-accent 则保持其选择。
  const accent = ref((() => {
    try { return localStorage.getItem('kmatch-accent') || 'teal' } catch { return 'teal' }
  })())

  function apply(m) {
    const root = document.documentElement
    if (m === 'dark') root.classList.add('dark')
    else root.classList.remove('dark')
    root.dataset.theme = m
  }

  /** issue: 通知主进程切换窗口按钮配色 (白主题按钮从此不再黑)。 */
  function syncWindowOverlay() {
    try { window.api?.window?.setOverlayTheme?.(mode.value === 'dark') } catch { /* 浏览器 dev 无 IPC */ }
  }

  function applyAccent(a) {
    if (a && a !== 'default') document.documentElement.dataset.kmatchAccent = a
    else delete document.documentElement.dataset.kmatchAccent
  }

  // 立即应用一次 (store 初始化时 DOM 可能已就绪)
  if (typeof document !== 'undefined') {
    apply(mode.value)
    applyAccent(accent.value)
    syncWindowOverlay()
  }

  watch(mode, (m) => {
    apply(m)
    syncWindowOverlay()
    localStorage.setItem(STORAGE_KEY, m)
  })

  watch(accent, (a) => {
    applyAccent(a)
    try { localStorage.setItem('kmatch-accent', a || 'default') } catch { /* ignore */ }
  })

  function toggle() {
    mode.value = mode.value === 'dark' ? 'light' : 'dark'
  }

  function set(m) {
    mode.value = m
  }

  function setAccent(a) {
    accent.value = a || 'default'
  }

  return { mode, accent, toggle, set, setAccent }
})
