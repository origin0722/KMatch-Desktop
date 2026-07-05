/**
 * IDE 布局状态 store — VS Code 风格单一指示模型
 *
 * 活动栏指示同一时间只亮一个 = activeView (code/learning-session/graph/learning/dashboard/settings)
 * 文件树显隐由 sidebarVisible 控制, 点击已激活视图可折叠 (VS Code 行为)
 */
import { ref } from 'vue'
import { defineStore } from 'pinia'

// 活动栏视图条目 (顺序即显示顺序) — 每个对应主区一个视图, 指示单一
export const ACTIVITY_ITEMS = [
  { id: 'code', icon: 'Document', title: '代码' },
  { id: 'learning-session', icon: 'ChatDotRound', title: '学习会话' },
  { id: 'graph', icon: 'Share', title: '知识图谱' },
  { id: 'learning', icon: 'Reading', title: '学习资源' },
  { id: 'dashboard', icon: 'DataAnalysis', title: '数据看板' },
]

export const useSidebarStore = defineStore('sidebar', () => {
  const activeView = ref('code') // 主区视图 = 活动栏唯一指示
  const sidebarVisible = ref(true) // 文件树显隐 (代码视图内)
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
