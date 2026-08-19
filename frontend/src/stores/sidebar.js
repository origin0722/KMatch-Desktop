/**
 * IDE 布局状态 store — VS Code 风格单一指示模型
 *
 * 活动栏指示同一时间只亮一个 = activeView (code/learning-session/chat/graph/learning/dashboard/settings)
 * 文件树显隐由 sidebarVisible 控制, 点击已激活视图可折叠 (VS Code 行为)
 */
import { ref } from 'vue'
import { defineStore } from 'pinia'

// 活动栏视图条目 (顺序即显示顺序) — 每个对应主区一个视图, 指示单一
export const ACTIVITY_ITEMS = [
  { id: 'code', icon: 'Document', title: '代码' },
  { id: 'learning-session', icon: 'ChatDotRound', title: '学习会话' },
  { id: 'chat', icon: 'ChatLineRound', title: 'AI 助手' },
  { id: 'graph', icon: 'Share', title: '知识图谱' },
  { id: 'project-graph', icon: 'Connection', title: '项目图谱' },
  { id: 'learning', icon: 'Reading', title: '学习资源' },
  { id: 'dashboard', icon: 'DataAnalysis', title: '数据看板' },
  { id: 'runs', icon: 'Clock', title: '运行历史' }, // 后台任务页: P1 耐久 run + 协同事件复用
  // 流程工作台 (workflow-studio) 导航默认隐藏: 用户反馈非必需; 代码/数据/API 保留
  // (MainArea 分支仍在, 未来"定义驱动执行"接线后可恢复)
]

export const useSidebarStore = defineStore('sidebar', () => {
  const activeView = ref('code') // 主区视图 = 活动栏唯一指示
  const prevView = ref('code') // 上一个视图 (设置页返回用)
  const sidebarVisible = ref(true) // 文件树显隐 (代码视图内)
  const aiPanelVisible = ref(true) // AI 助手面板
  const persona = ref('beginner') // 学习角色: beginner/intermediate/advanced, 调整图谱节点详略
  const onboardingActive = ref(false) // 首次引导覆盖层 (设置页「重新引导」可再触发)

  function setView(id) {
    if (id !== activeView.value) prevView.value = activeView.value
    activeView.value = id
  }

  function back() {
    activeView.value = prevView.value
  }

  function toggleSidebar() {
    sidebarVisible.value = !sidebarVisible.value
  }

  function toggleAiPanel() {
    aiPanelVisible.value = !aiPanelVisible.value
  }

  function setPersona(p) { persona.value = p }

  // 首次引导: 完成时写 onboarded 标记 (OnboardingOverlay emit done -> 此处收口)
  function startOnboarding() { onboardingActive.value = true }
  function finishOnboarding() {
    localStorage.setItem('kmatch-onboarded', '1')
    onboardingActive.value = false
  }

  return { activeView, prevView, sidebarVisible, aiPanelVisible, persona, onboardingActive, setView, back, setPersona, toggleSidebar, toggleAiPanel, startOnboarding, finishOnboarding }
})
