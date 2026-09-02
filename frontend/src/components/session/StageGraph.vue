<template>
  <section class="stage-card stage-graph km-surface" :class="{ active: isActive }">
    <header class="stage-head">
      <span class="stage-no">04</span>
      <h4>本次学习路径图谱</h4>
      <span class="stage-done">✓ 已生成</span>
    </header>
    <div class="stage-body">
      <div class="graph-summary">
        <div class="summary-item">
          <div class="summary-val km-mono-number">{{ nodeCount }}</div>
          <div class="summary-label">路径节点</div>
        </div>
        <div class="summary-item">
          <div class="summary-val km-mono-number">{{ hours }}<span class="unit-hint">h</span></div>
          <div class="summary-label">预计学时{{ weeks ? ' · ≈' + weeks + '周' : '' }}</div>
        </div>
        <div class="summary-item">
          <div class="summary-val km-mono-number">{{ mastery }}%</div>
          <div class="summary-label">综合掌握度</div>
        </div>
      </div>
      <div class="graph-actions">
        <el-button @click="openFull">查看完整图谱</el-button>
        <el-button type="primary" @click="splitGraph">对照分屏查看</el-button>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { useAssessmentStore } from '@/stores/assessment'
import { useSidebarStore } from '@/stores/sidebar'
import { useSessionStore } from '@/stores/session'

const store = useAssessmentStore()
const sidebar = useSidebarStore()
const session = useSessionStore()

const isActive = computed(() => session.activeStage === 'graph')
const kg = computed(() => store.knowledgeGraph || {})
const nodeCount = computed(() => (kg.value.learning_path || []).length)
const hours = computed(() => {
  const h = kg.value.estimated_total_hours
  return h != null ? Number(h).toFixed(1) : '--'
})
// issue-78: 节奏语境 — 按每周 6h 折周 (与 report pacing 口径一致)
const weeks = computed(() => {
  const h = Number(kg.value.estimated_total_hours || 0)
  return h > 0 ? Math.max(1, Math.ceil(h / 6)) : 0
})
const mastery = computed(() => {
  const p = store.profile || {}
  const all = [...(p.known_topics || []), ...(p.weak_topics || [])]
  if (!all.length) return 0
  const sum = all.reduce((s, t) => s + (t.mastery || 0), 0)
  return Math.round((sum / all.length) * 100)
})

function openFull() { sidebar.setView('graph') }
function splitGraph() { session.setSplitView('graph') }
</script>

<style scoped>
.stage-card { border-left: 3px solid var(--km-border-light); border-radius: var(--km-radius); overflow: hidden; transition: border-color 0.3s var(--km-ease); }
.stage-card.active { border-left-color: var(--km-primary); }
.stage-head { display: flex; align-items: center; gap: 10px; padding: 12px 16px; border-bottom: 1px solid var(--km-border-light); }
.stage-no { font-family: var(--km-font-mono); font-size: 12px; color: var(--km-gray-500); }
.stage-head h4 { margin: 0; font-size: 14px; color: var(--km-gray-800); }
.stage-done { margin-left: auto; color: var(--km-success); font-size: 12px; }
.stage-body { padding: 16px; }
.graph-summary { display: flex; gap: 24px; margin-bottom: 16px; }
.summary-item { text-align: center; }
.summary-val { font-size: 24px; font-weight: 700; color: var(--km-gray-800); }
.summary-label { font-size: 12px; color: var(--km-gray-500); margin-top: 2px; }
.graph-actions { display: flex; gap: 10px; }
</style>
