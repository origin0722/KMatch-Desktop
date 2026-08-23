/**
 * 图谱历史 store — 统一管理两类图谱的"历史记录" (本地持久化)
 *
 * type: 'project'  = 项目代码图谱 (场景二, 从后端项目图谱缓存加载)
 *       'learning' = 学情知识图谱 (场景一, 本地快照 learning_path 恢复)
 *
 * 目的: 用户无需打开项目文件/重新测评即可回看两类图谱; 空态按类型分组展示。
 */
import { ref } from 'vue'
import { defineStore } from 'pinia'

const KEY = 'kmatch-graph-history'
const MAX = 12

function load() {
  try {
    const arr = JSON.parse(localStorage.getItem(KEY) || '[]')
    return Array.isArray(arr) ? arr : []
  } catch { return [] }
}

export const useGraphHistoryStore = defineStore('graphHistory', () => {
  const items = ref(load())

  function _persist() {
    try { localStorage.setItem(KEY, JSON.stringify(items.value)) } catch { /* quota / private */ }
  }

  /** 项目图谱: 解析成功后记录 (projectId 后端缓存, 点击时 getProjectGraph 加载)。 */
  function addProject({ projectId, name }) {
    if (!projectId) return
    const id = `project:${projectId}`
    items.value = [
      { id, type: 'project', name: name || '项目', projectId, ts: Date.now() },
      ...items.value.filter((i) => i.id !== id),
    ].slice(0, MAX)
    _persist()
  }

  /** 学情图谱: 测评产出 knowledge_graph 后记录本地快照 (learning_path 可离线恢复)。 */
  function addLearning({ sessionId, name, snapshot }) {
    if (!sessionId || !snapshot?.learning_path?.length) return
    const id = `learning:${sessionId}`
    items.value = [
      { id, type: 'learning', name: name || '学情图谱', sessionId, snapshot, ts: Date.now() },
      ...items.value.filter((i) => i.id !== id),
    ].slice(0, MAX)
    _persist()
  }

  function remove(id) {
    items.value = items.value.filter((i) => i.id !== id)
    _persist()
  }

  return { items, addProject, addLearning, remove }
})
