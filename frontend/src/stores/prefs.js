/**
 * 用户偏好 store (issue-73) — 学习节奏/界面偏好, localStorage 持久化。
 *
 * hoursPerWeek: 每周可投入学习小时数, 用于前端"折周"展示 (1-20)。
 */
import { ref } from 'vue'
import { defineStore } from 'pinia'

function loadNum(key, fallback) {
  try {
    const v = Number(localStorage.getItem(key))
    return Number.isFinite(v) && v > 0 ? v : fallback
  } catch { return fallback }
}

export const usePrefsStore = defineStore('prefs', () => {
  // issue-73: 每周可学时长 (默认 6h, 与后端 pacing 口径一致; 改后前端折周展示即时生效)
  const hoursPerWeek = ref(loadNum('kmatch-hours-per-week', 6))

  function setHoursPerWeek(v) {
    const n = Math.min(20, Math.max(1, Math.round(Number(v) || 6)))
    hoursPerWeek.value = n
    try { localStorage.setItem('kmatch-hours-per-week', String(n)) } catch { /* ignore */ }
  }

  return { hoursPerWeek, setHoursPerWeek }
})
