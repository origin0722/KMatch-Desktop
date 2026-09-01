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
    // 正在回看的快照被删除 → 一并退出回看态 (避免展示已删除的数据)
    if (learningViewing.value?.id === id) backToLiveLearning()
    _persist()
  }

  // ============================================================
  // 学习图谱历史回看态 (只读查看, 不改写 live 数据)
  // 问题背景: 此前点历史直接 store.knowledgeGraph = snapshot 覆盖当前图谱,
  // 用户"钻进去就回不来"——现改为显示层覆写: live 仍在 assessment store,
  // 视图渲染 learningSnapshot || live, 任意时刻可"返回当前图谱"。
  // ============================================================
  /** null = 当前 (live) 图谱; 否则 { id, name, ts } 标识正在回看的快照 */
  const learningViewing = ref(null)
  /** 回看中的快照本体 (item.snapshot), 渲染优先级高于 live */
  const learningSnapshot = ref(null)

  /** 进入历史回看 (返回 false=快照无效); 链式切换历史仅换快照, live 始终不动。 */
  function viewLearning(item) {
    if (!item?.snapshot?.learning_path?.length) return false
    learningViewing.value = { id: item.id, name: item.name || '学情图谱', ts: item.ts }
    learningSnapshot.value = item.snapshot
    return true
  }

  /** 返回当前 (live) 图谱; 新测评产出 live 图谱时也调它自动退出回看态。 */
  function backToLiveLearning() {
    learningViewing.value = null
    learningSnapshot.value = null
  }

  return {
    items, addProject, addLearning, remove,
    learningViewing, learningSnapshot, viewLearning, backToLiveLearning,
  }
})
