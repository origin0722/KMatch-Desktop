/**
 * 学习会话 store (阶段8三合一)
 *
 * activeStage 是 computed, 派生自 assessment store (不独立存状态, 避免双源真相):
 *   goal  — 无结果/无协同日志/无 loading (阶段①目标设定)
 *   quiz  — phase==='answering' 或 phase==='feedback' (阶段②答题, 含反馈)
 *   agent — loading 且有 orchestrationLog (阶段③协同, demo SSE 流期间)
 *   graph — hasResults (阶段④图谱摘要)
 *
 * splitView: null | 'graph' | 'learning' | 'dashboard' (主从分屏右半视图)
 *
 * showCollab: #30 答题完成后默认展示 AI 协同。纯布局状态 (可手动收起)——
 *   由 assessment.phase watch 自动点亮 (feedback→true, idle→复位), 用户可 setShowCollab(false) 收起。
 *
 * 优先级 (高→低): graph > agent > quiz > goal
 *
 * 边界 (C4 决策: 保留为独立 store):
 *   本 store 近 pass-through (41 行, 仅拥 splitView; activeStage 纯派生), 曾被质疑是否
 *   值得独立。决定保留——splitView 是 IDE 布局状态, 与 assessment (学情领域) 非同一关注点;
 *   并入 assessment 会让领域 store 混入布局职责, 反增耦合。session 作为"学习会话布局"独立
 *   store 合理; activeStage 派生自 assessment 是有意为之 (单一真相源, 见重构方案_解耦.md C4)。
 */
import { ref, computed, watch } from 'vue'
import { defineStore } from 'pinia'
import { useAssessmentStore } from '@/stores/assessment'

// 允许作为分屏右半的左侧栏视图 (code 不含, 因 code 是编辑器非产出)
const SPLITTABLE = new Set(['graph', 'learning', 'dashboard'])

export const useSessionStore = defineStore('session', () => {
  const splitView = ref(null)

  /**
   * #30 答题完成后默认展示 AI 协同 (可手动收起)。
   * 派生自 assessment.phase (单一真相源): feedback 自动点亮, idle 复位。
   * 手动收起走 setShowCollab(false), 不随 phase 重复点亮 (phase 不变回 idle 不会重置)。
   */
  const showCollab = ref(false)
  watch(
    () => {
      const a = useAssessmentStore()
      return a.phase
    },
    (p) => {
      if (p === 'feedback') showCollab.value = true
      else if (p === 'idle') showCollab.value = false
    },
    { flush: 'sync' },
  )

  function setShowCollab(v) {
    showCollab.value = !!v
  }

  const activeStage = computed(() => {
    const a = useAssessmentStore()
    if (a.hasResults) return 'graph'
    if (a.loading && (a.orchestrationLog?.length || 0) > 0) return 'agent'
    if (a.phase === 'answering' || a.phase === 'feedback') return 'quiz'
    return 'goal'
  })

  function setSplitView(view) {
    if (SPLITTABLE.has(view)) splitView.value = view
  }

  function closeSplit() {
    splitView.value = null
  }

  return { activeStage, splitView, showCollab, setSplitView, closeSplit, setShowCollab }
})
