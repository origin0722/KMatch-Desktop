/**
 * 侧栏面板 store — IDE 左侧多面板切换 (类 VS Code)
 * 资源管理器 / 学情测评 / 知识图谱 / 学习资源 / Agent协同 / 数据看板
 * 取代原 /learn 独立界面, 赛题场景一功能收编进 IDE 侧栏。
 */
import { ref } from 'vue'
import { defineStore } from 'pinia'

// 面板定义: id → { icon, title, component }
export const PANELS = [
  { id: 'explorer', icon: 'Files', title: '资源管理器' },
  { id: 'assessment', icon: 'Edit', title: '学情测评' },
  { id: 'graph', icon: 'Share', title: '知识图谱' },
  { id: 'learning', icon: 'Reading', title: '学习资源' },
  { id: 'agents', icon: 'Connection', title: 'Agent 协同' },
  { id: 'dashboard', icon: 'DataAnalysis', title: '数据看板' },
]

export const useSidebarStore = defineStore('sidebar', () => {
  const activePanel = ref('explorer')
  const collapsed = ref(false) // 侧栏折叠 (阶段1 暂不实现折叠按钮)

  function setPanel(id) {
    activePanel.value = id
    if (collapsed.value) collapsed.value = false
  }

  function toggleCollapse() {
    collapsed.value = !collapsed.value
  }

  return { activePanel, collapsed, setPanel, toggleCollapse }
})
