/**
 * 响应式 Map/Set helper (F11)
 *
 * Vue 对 ref(new Map()/new Set()) 的 mutation (set/delete/add) 不触发响应式 ——
 * 必须重新赋值 new Map(...) 才让 watcher 触发。旧代码手写 new Map(...) 重赋, 易漏
 * (漏 = 静默 UI 冻结)。本 helper 封装 mutation 后自动重赋, 调用方只管业务操作。
 */

import { ref, shallowRef } from 'vue'

/**
 * 响应式 Map: 每次 mutation 后自动 trigger (重新赋值)。
 * 返回 { ref, set, delete, clear, get, has }。ref 是 ref<Map>, 供模板/watcher 读。
 */
export function useReactiveMap(initial) {
  const r = ref(new Map(initial))
  const trigger = () => { r.value = new Map(r.value) }
  return {
    ref: r,
    set: (k, v) => { r.value.set(k, v); trigger() },
    delete: (k) => { const had = r.value.delete(k); if (had) trigger(); return had },
    clear: () => { r.value = new Map() },
    get: (k) => r.value.get(k),
    has: (k) => r.value.has(k),
    get size() { return r.value.size },
  }
}

/**
 * 响应式 Set: 每次 mutation 后自动 trigger。
 * 返回 { ref, add, delete, clear, has }。
 */
export function useReactiveSet(initial) {
  const r = ref(new Set(initial))
  const trigger = () => { r.value = new Set(r.value) }
  return {
    ref: r,
    add: (v) => { r.value.add(v); trigger() },
    delete: (v) => { const had = r.value.delete(v); if (had) trigger(); return had },
    clear: () => { r.value = new Set() },
    has: (v) => r.value.has(v),
    get size() { return r.value.size },
  }
}
