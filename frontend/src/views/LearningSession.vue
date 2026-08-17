<template>
  <div class="learning-session km-workbench">
    <div class="session-layout">
      <!-- 会话流: 进度轨(左) + 阶段卡(右), grid 每行同高 -> 进度点对齐阶段卡中心 -->
      <div class="session-flow" ref="flowRef">
        <div class="stages-grid">
          <div v-for="st in visibleStages" :key="st.key" class="stage-row">
            <div class="rail-cell">
              <span class="rail-node" :class="railClass(st.key)" />
            </div>
            <div class="stage-cell">
              <component :is="st.component" :class="stageClass(st.key)" />
            </div>
          </div>
        </div>
      </div>
      <!-- 右:主从分屏 (可选) -->
      <SplitPane />
    </div>
  </div>
</template>

<script setup>
import { watch, nextTick, ref, computed, onBeforeUnmount } from 'vue'
import { useAssessmentStore } from '@/stores/assessment'
import { useSessionStore } from '@/stores/session'
import StageGoal from '@/components/session/StageGoal.vue'
import StageQuiz from '@/components/session/StageQuiz.vue'
import StageAgent from '@/components/session/StageAgent.vue'
import StageGraph from '@/components/session/StageGraph.vue'
import SplitPane from '@/components/session/SplitPane.vue'

const store = useAssessmentStore()
const session = useSessionStore()

// 阶段顺序: goal -> quiz -> agent -> graph
const STAGES = [
  { key: 'goal', component: StageGoal },
  { key: 'quiz', component: StageQuiz },
  { key: 'agent', component: StageAgent },
  { key: 'graph', component: StageGraph },
]
const ORDER = ['goal', 'quiz', 'agent', 'graph']

// graph 阶段仅在有结果时显示 (与进度轨节点数量同步, 避免错位)
const visibleStages = computed(() =>
  STAGES.filter((s) => s.key !== 'graph' || store.hasResults),
)

// 阶段卡 3 态: done (已过) / active (当前) / pending (未到)
// 命名与 railNode、stage-card 既有 .active CSS 一致, 避免双套样式
function stageClass(key) {
  const curIdx = ORDER.indexOf(session.activeStage)
  const idx = ORDER.indexOf(key)
  return {
    done: idx < curIdx,
    active: idx === curIdx,
    pending: idx > curIdx,
  }
}

function railClass(key) {
  const curIdx = ORDER.indexOf(session.activeStage)
  const idx = ORDER.indexOf(key)
  if (idx < curIdx) return 'done'
  if (idx === curIdx) return 'active'
  return 'pending'
}

// 自动滚动到当前阶段卡
const flowRef = ref(null)
watch(() => session.activeStage, async () => {
  await nextTick()
  const el = flowRef.value?.querySelector('.stage-card.active')
  el?.scrollIntoView?.({ behavior: 'smooth', block: 'center' })
})

// #30: 滚动驱动激活 — 答题区滚动到底 (提交按钮可见) 自动点亮 AI 协同入口。
// 提交后 session store 已由 phase=feedback 置 showCollab, 此处负责"提前点亮"与回退清理。
const collabObserver = ref(null)
function bindCollabObserver() {
  collabObserver.value?.disconnect()
  const submitEl = flowRef.value?.querySelector('.quiz-submit')
  if (!submitEl || typeof IntersectionObserver === 'undefined') return
  collabObserver.value = new IntersectionObserver((entries) => {
    if (entries.some((e) => e.isIntersecting)) session.setShowCollab(true)
  }, { root: flowRef.value, threshold: 0.4 })
  collabObserver.value.observe(submitEl)
}
watch(() => store.phase, async (p) => {
  if (p === 'answering') {
    await nextTick()
    bindCollabObserver()
  } else {
    collabObserver.value?.disconnect()
  }
})
onBeforeUnmount(() => collabObserver.value?.disconnect())
</script>

<style scoped>
.learning-session { padding: 0; height: 100%; display: flex; flex-direction: column; }
.session-layout { flex: 1; display: flex; min-height: 0; overflow: hidden; }
.session-flow { flex: 1; min-width: 0; overflow-y: auto; padding: 0 20px 20px; }

/* 阶段网格: 每行 = 进度轨单元格 + 阶段卡单元格, grid 行同高 -> rail-node 垂直居中对齐阶段卡中心 */
.stages-grid { display: flex; flex-direction: column; gap: 12px; padding-top: 12px; position: relative; }
.stage-row { display: grid; grid-template-columns: 24px 1fr; gap: 16px; align-items: stretch; }
.rail-cell { display: flex; align-items: center; justify-content: center; position: relative; }

/* 纵向轨道线: 贯穿 rail-cell 列中央 (首尾对齐首末节点圆心) */
.stages-grid::before {
  content: ''; position: absolute; left: 12px; top: 24px; bottom: 24px;
  width: 2px; transform: translateX(-50%);
  background: var(--km-border-light); border-radius: 1px; z-index: 0;
}

.rail-node {
  width: 12px; height: 12px; border-radius: 50%;
  border: 2px solid var(--km-border); background: var(--km-bg-layer-3);
  flex-shrink: 0; position: relative; z-index: 1;
}
.rail-node.done { background: var(--km-success); border-color: var(--km-success); }
.rail-node.active { background: var(--km-primary); border-color: var(--km-primary); box-shadow: 0 0 0 4px rgba(108,124,224,0.2); animation: rail-pulse 2s ease-in-out infinite; }
.rail-node.pending { background: var(--km-bg-layer-3); border-color: var(--km-border); border-style: dashed; }

.stage-cell { min-width: 0; }

/* 阶段卡 3 态 (子组件根元素经 class 穿透落入父作用域, 可直接选中) */
.stage-card.done { opacity: 0.72; }
.stage-card.active { border-left-color: var(--km-primary); box-shadow: 0 4px 16px rgba(108,124,224,0.12); }
.stage-card.pending { opacity: 0.55; }

@keyframes rail-pulse { 0%, 100% { box-shadow: 0 0 0 4px rgba(108,124,224,0.2); } 50% { box-shadow: 0 0 0 8px rgba(108,124,224,0.08); } }
@media (prefers-reduced-motion: reduce) {
  .rail-node.active { animation: none; }
  .session-flow { scroll-behavior: auto; }
}
</style>
