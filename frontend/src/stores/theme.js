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

  function apply(m) {
    const root = document.documentElement
    if (m === 'dark') root.classList.add('dark')
    else root.classList.remove('dark')
    root.dataset.theme = m
  }

  // 立即应用一次 (store 初始化时 DOM 可能已就绪)
  if (typeof document !== 'undefined') apply(mode.value)

  watch(mode, (m) => {
    apply(m)
    localStorage.setItem(STORAGE_KEY, m)
  })

  function toggle() {
    mode.value = mode.value === 'dark' ? 'light' : 'dark'
  }

  function set(m) {
    mode.value = m
  }

  return { mode, toggle, set }
})
