/**
 * IDE 布局状态 store — 单一指示模型
 *
 * 活动栏指示同一时间只亮一个 = activeView (code/graph/assessment/agents)
 * 资源管理器侧栏独立显隐 (sidebarVisible), 由侧栏头部折叠按钮控制,
 * 不参与活动栏指示竞争 (避免 📁 与视图图标同时亮)。
 */
import { ref } from 'vue'
import { defineStore } from 'pinia'

// 活动栏视图条目 (顺序即显示顺序) — 每个对应主区一个视图, 指示单一
export const ACTIVITY_ITEMS = [
  { id: 'code', icon: 'Document', title: '代码' },
  { id: 'graph', icon: 'Share', title: '知识图谱' },
  { id: 'assessment', icon: 'Edit', title: '答题测评' },
  { id: 'agents', icon: 'Connection', title: 'Agent 协同' },
]

export const useSidebarStore = defineStore('sidebar', () => {
  const activeView = ref('code') // 主区视图 = 活动栏唯一指示
  const sidebarVisible = ref(true) // 资源管理器侧栏 (独立, 不影响指示)
  const aiPanelVisible = ref(true) // AI 助手面板

  function setView(id) {
    activeView.value = id
  }

  function toggleSidebar() {
    sidebarVisible.value = !sidebarVisible.value
  }

  function toggleAiPanel() {
    aiPanelVisible.value = !aiPanelVisible.value
  }

  return { activeView, sidebarVisible, aiPanelVisible, setView, toggleSidebar, toggleAiPanel }
})
