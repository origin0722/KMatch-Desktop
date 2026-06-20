/**
 * IDE 布局状态 store
 *
 * 布局: 活动栏 | 侧栏(资源管理器) | 主区(多视图切换) | AI助手面板
 *
 * - sidebarVisible: 侧栏(资源管理器)是否展开; 点活动栏 📁 切换
 * - activeView: 主区当前视图 (code/graph/assessment/agents)
 *   点活动栏对应图标 = 切主区视图 (不挤侧栏)
 */
import { ref } from 'vue'
import { defineStore } from 'pinia'

// 活动栏条目 (顺序即显示顺序)
export const ACTIVITY_ITEMS = [
  { id: 'explorer', icon: 'Files', title: '资源管理器', kind: 'sidebar' },
  { id: 'code', icon: 'Document', title: '代码', kind: 'view' },
  { id: 'graph', icon: 'Share', title: '知识图谱', kind: 'view' },
  { id: 'assessment', icon: 'Edit', title: '答题测评', kind: 'view' },
  { id: 'agents', icon: 'Connection', title: 'Agent 协同', kind: 'view' },
]

// 主区视图定义
export const MAIN_VIEWS = [
  { id: 'code', label: '代码' },
  { id: 'graph', label: '知识图谱' },
  { id: 'assessment', label: '答题测评' },
  { id: 'agents', label: 'Agent 协同' },
]

export const useSidebarStore = defineStore('sidebar', () => {
  const sidebarVisible = ref(true)
  const activeView = ref('code') // 主区视图
  const aiPanelVisible = ref(true) // AI 助手面板

  function toggleSidebar() {
    sidebarVisible.value = !sidebarVisible.value
  }

  function setView(id) {
    activeView.value = id
  }

  function toggleAiPanel() {
    aiPanelVisible.value = !aiPanelVisible.value
  }

  /** 活动栏点击: sidebar 类切换侧栏, view 类切主区视图 */
  function handleActivityClick(item) {
    if (item.kind === 'sidebar') {
      // 同一图标再点 = 折叠/展开
      if (activeView.value === null && sidebarVisible.value) {
        sidebarVisible.value = false
      } else {
        sidebarVisible.value = true
      }
    } else {
      setView(item.id)
      // 切主区视图时侧栏默认收起给主区让空间? 保留展开, 用户可手动收
    }
  }

  return { sidebarVisible, activeView, aiPanelVisible, toggleSidebar, setView, toggleAiPanel, handleActivityClick }
})
