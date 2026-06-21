<template>
  <div class="learning-session km-workbench">
    <div class="km-workbench-header">
      <div>
        <p class="km-workbench-kicker">learning session</p>
        <h3 class="km-workbench-title">学习会话</h3>
        <p class="km-workbench-desc">答题、Agent 协同、专属图谱串成一条会话流,由 Agent 推动阶段推进。</p>
      </div>
    </div>

    <div class="session-layout">
      <!-- 左:会话流 + 进度连线 -->
      <div class="session-flow" ref="flowRef">
        <div class="progress-rail">
          <span v-for="st in STAGES" :key="st.key" class="rail-node"
            :class="railClass(st.key)" />
        </div>
        <div class="stages">
          <StageGoal :class="stageClass('goal')" />
          <StageQuiz :class="stageClass('quiz')" />
          <StageAgent :class="stageClass('agent')" />
          <StageGraph v-if="store.hasResults" :class="stageClass('graph')" />
        </div>
      </div>
      <!-- 右:主从分屏 (可选) -->
      <SplitPane />
    </div>
  </div>
</template>

<script setup>
import { watch, nextTick, ref } from 'vue'
import { useAssessmentStore } from '@/stores/assessment'
import { useSessionStore } from '@/stores/session'
import StageGoal from '@/components/session/StageGoal.vue'
import StageQuiz from '@/components/session/StageQuiz.vue'
import StageAgent from '@/components/session/StageAgent.vue'
import StageGraph from '@/components/session/StageGraph.vue'
import SplitPane from '@/components/session/SplitPane.vue'

const store = useAssessmentStore()
const session = useSessionStore()

// 阶段顺序: goal → quiz → agent → graph
const STAGES = [
  { key: 'goal' }, { key: 'quiz' }, { key: 'agent' }, { key: 'graph' },
]
const ORDER = ['goal', 'quiz', 'agent', 'graph']

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
  el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
})
</script>

<style scoped>
.learning-session { padding: 0; height: 100%; display: flex; flex-direction: column; }
.session-layout { flex: 1; display: flex; min-height: 0; overflow: hidden; }
.session-flow { flex: 1; min-width: 0; overflow-y: auto; padding: 0 20px 20px; display: flex; gap: 16px; }
.progress-rail { display: flex; flex-direction: column; align-items: center; padding-top: 20px; gap: 0; position: relative; }
/* 进度连线: 节点背后的纵向轨道 (首尾对齐节点圆心) */
.progress-rail::before { content: ''; position: absolute; left: 50%; top: 26px; bottom: 26px; width: 2px; transform: translateX(-50%); background: var(--km-border-light); border-radius: 1px; z-index: 0; }
.progress-rail .rail-node { width: 12px; height: 12px; border-radius: 50%; border: 2px solid var(--km-border); background: var(--km-bg-layer-3); flex-shrink: 0; position: relative; z-index: 1; }
.progress-rail .rail-node + .rail-node { margin-top: 80px; }
.progress-rail .rail-node.done { background: var(--km-success); border-color: var(--km-success); }
.progress-rail .rail-node.active { background: var(--km-primary); border-color: var(--km-primary); box-shadow: 0 0 0 4px rgba(108,124,224,0.2); animation: rail-pulse 2s ease-in-out infinite; }
.progress-rail .rail-node.pending { background: var(--km-bg-layer-3); border-color: var(--km-border); border-style: dashed; }
.stages { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 12px; padding-top: 12px; }

/* 阶段卡 3 态 (子组件根元素经 class 穿透落入父作用域, 可直接选中) */
.stage-card.done { opacity: 0.72; }
.stage-card.active { border-left-color: var(--km-primary); box-shadow: 0 4px 16px rgba(108,124,224,0.12); }
.stage-card.pending { opacity: 0.55; }

@keyframes rail-pulse { 0%, 100% { box-shadow: 0 0 0 4px rgba(108,124,224,0.2); } 50% { box-shadow: 0 0 0 8px rgba(108,124,224,0.08); } }
@media (prefers-reduced-motion: reduce) {
  .progress-rail .rail-node.active { animation: none; }
  .session-flow { scroll-behavior: auto; }
}
</style>
