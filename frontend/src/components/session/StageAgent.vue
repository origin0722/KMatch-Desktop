<template>
  <section class="stage-card stage-agent km-surface" :class="{ active: isActive }">
    <header class="stage-head" @click="toggleExpand">
      <span class="stage-no">03</span>
      <h4>Agent 协同</h4>
      <span v-if="collabOn && !isActive" class="collab-pill">协同已就绪</span>
      <span v-else-if="hasLogs && !isActive" class="stage-done">✓ 已完成</span>
      <span v-if="status.pipelineRunning.value" class="running-pill">运行中</span>
      <span class="expand-toggle">{{ expanded ? '▾' : '▸' }}</span>
    </header>
    <transition name="agent-expand">
      <div v-show="expanded && hasLogs" class="stage-body">
        <!-- #30: 答题完成默认展示 AI 协同 - 下一步建议横幅, 可点击收起 -->
        <div v-if="collabOn" class="collab-tip">
          <span class="collab-icon" aria-hidden="true"></span>
          <span class="collab-msg"><strong>下一步建议</strong>　{{ nextSuggestion }}</span>
          <button class="collab-fold" title="收起协同" @click.stop="toggleExpand">收起 ▴</button>
        </div>

        <!-- 总进度 + 实时动作: 告诉用户"完成情况"与"现在在做什么" -->
        <div class="progress-bar">
          <span class="progress-done">{{ status.completedCount.value }} 项完成</span>
          <span v-if="status.pendingCount.value" class="progress-pending">· {{ status.pendingCount.value }} 项{{ status.deferredCount.value ? '待后续资源流程启动' : '待触发' }}</span>
          <span v-if="status.pipelineRunning.value && status.currentAction.value" class="progress-live">
            · {{ status.currentAction.value.label }} 正在{{ status.currentAction.value.action }}…
          </span>
        </div>

        <!-- Phase 3a: 只读流程进度 DAG (当前步/完成阶段可视化) -->
        <div v-if="flow.stages.value.length" class="flow-block">
          <div class="flow-head">
            <span class="flow-title">流程进度</span>
            <span class="flow-count">
              ✅ {{ flow.doneCount.value }}/{{ flow.stages.value.length }}
              <template v-if="flow.currentLabel.value"> · 正在 {{ flow.currentLabel.value }}</template>
            </span>
          </div>
          <FlowDiagram :stages="flow.stages.value" :edges="flow.edges.value || undefined" class="flow-canvas" :height="150" />
        </div>

        <!-- 每 Agent 产出概览 (主视图, 替代原三栏 cockpit) -->
        <div class="prod-list">
          <div v-for="agent in status.agentNodes.value" :key="agent.key"
               class="prod-row" :class="[`status-${agent.status}`]">
            <span class="status-dot" :class="`dot-${agent.status}`" aria-hidden="true"></span>
            <div class="prod-main">
              <div class="prod-head">
                <span class="prod-label">{{ agent.label }}</span>
                <span class="prod-badge" :class="`badge-${agent.status}`">{{ statusBadge(agent.status) }}</span>
                <span v-if="agent.retryCount > 0" class="prod-retry">打回 ×{{ agent.retryCount }}</span>
              </div>
              <p class="prod-summary">{{ status.productions.value[agent.key] || agent.activationHint || agent.role }}</p>
            </div>
          </div>
        </div>

        <!-- 原始日志 (可折叠细节, 默认收起) -->
        <details class="log-detail">
          <summary>协同对话流 · 原始日志 {{ rawLogs.length }} 条</summary>
          <div class="thread-body">
            <article v-for="(entry, idx) in parsedLogs" :key="idx" class="thread-message" :class="{ reject: entry.isReject }">
              <span class="thread-time">{{ entry.time || '--:--' }}</span>
              <p>{{ entry.msg }}</p>
            </article>
          </div>
          <!-- Phase 1: 按上次 demo 流程一键续跑 -->
          <button v-if="canResume" class="resume-btn" type="button" @click="onResume">↻ 按此流程重新执行</button>
        </details>
      </div>
    </transition>
    <div v-if="!hasLogs" class="stage-empty">尚无协同记录</div>
  </section>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useAssessmentStore } from '@/stores/assessment'
import { useSessionStore } from '@/stores/session'
import { useAgentStatus } from '@/composables/useAgentStatus'
import { useFlowStatus } from '@/composables/useFlowStatus'
import FlowDiagram from '@/ide/workflow/FlowDiagram.vue'

const store = useAssessmentStore()
const session = useSessionStore()
const status = useAgentStatus()
// 有 run 落盘的 workflow 快照 → 协同 DAG 用真实阶段拓扑/label; 直播/无快照回退线性链
const flowDef = computed(() => store.lastRun?.workflow || null)
const flow = useFlowStatus(flowDef)

const expanded = ref(false)

const isActive = computed(() => session.activeStage === 'agent')
const rawLogs = computed(() => store.orchestrationLog || [])
const hasLogs = computed(() => rawLogs.value.length > 0)

// Phase 1: 上次有 demo run 请求 meta 且非运行中 → 可"按此流程重跑"
const canResume = computed(() => !!store.lastRun?.request?.target_direction && !store.loading)
async function onResume() {
  await store.resumeRunDemo()
}

// #30: 答题完成默认展示 AI 协同 - showCollab 点亮 (session store 由 assessment.phase=feedback 自动触发)
const collabOn = computed(() => session.showCollab && hasLogs.value)

// #30: 下一步建议 - 由反馈策略驱动, 指向协同产出与后续动作 (v1.3.3: 三条句式差异化, 去同构模板腔)
const NEXT_STEP = {
  advance: '基础扎实。协同产出的进阶资源已就绪，可以直接开始；也可以在右侧图谱里挑一个进阶节点深入。',
  remediate: '有几个知识点掌握得不够牢。协同已经用另一种讲法重讲了薄弱点并配了练习，换个角度再过一遍。',
  scaffold: '先补前置会更顺——这次的薄弱点卡在前置知识上。协同已生成补基础方案（含溯源），按顺序过一遍再回来。',
}
const nextSuggestion = computed(() => NEXT_STEP[store.feedbackStrategy]
  || '协同已完成，各 Agent 产出已就绪，可继续获取针对性反馈或查看右侧图谱。')

const parsedLogs = computed(() => {
  const result = []
  let lastTime = ''
  for (const entry of rawLogs.value) {
    const m = entry?.match(/^\[(.+?)\]/)
    const time = m ? m[1] : lastTime
    const msgStart = entry?.indexOf('] ')
    const raw = msgStart >= 0 ? entry.slice(msgStart + 2) : entry
    lastTime = time
    // v1.3.3: 日志 emoji 仅展示层转译为文字标签 (log_events 事件契约不动 —
    // useAgentStatus 状态推导正则仍依赖原始 emoji), 用户界面不再出现符号刷屏
    const msg = stripEmojiForDisplay(raw)
    result.push({ time, msg, isReject: entry?.includes('❌') || entry?.includes('打回') })
  }
  return result
})

const EMOJI_LABELS = [
  ['✅', '[完成]'], ['❌', '[未通过]'], ['⚠️', '[注意]'], ['⚠', '[注意]'],
  ['🔧', '[学情]'], ['📚', '[生成]'], ['🗺️', '[路径]'], ['🗺', '[路径]'],
  ['🔍', '[审核]'], ['📊', '[报告]'], ['📋', '[画像]'], ['🔁', '[重试]'], ['⏹', '[停止]'], ['⏱', '[计时]'],
]
function stripEmojiForDisplay(text) {
  let out = String(text || '')
  for (const [emoji, label] of EMOJI_LABELS) out = out.split(emoji).join(label)
  return out
}

function toggleExpand() { expanded.value = !expanded.value }
// 面向学习者的状态文案 (idle=按需待触发, deferred=后续资源流程再启动)
function statusBadge(s) {
  return {
    idle: '待触发',
    deferred: '生成资源后启动',
    running: '执行中',
    done: '完成',
    degraded: '降级',
    failed: '失败',
  }[s] || s
}

// activeStage 进入 agent 时自动展开
watch(() => session.activeStage, (s) => {
  if (s === 'agent') expanded.value = true
}, { immediate: true })

// #30: 答题完成默认展示 AI 协同 - collabOn (showCollab && hasLogs) 成立即自动展开 (可手动收起)。
// 需同时监听两者: showCollab 可能被滚动驱动提前点亮 (日志未就绪), 提交后日志到达 hasLogs 翻真时仍要展开。
watch([() => session.showCollab, hasLogs], () => {
  if (session.showCollab && hasLogs.value) expanded.value = true
})
</script>

<style scoped>
.stage-card { border-left: 3px solid var(--km-border-light); border-radius: var(--km-radius); overflow: hidden; transition: border-color 0.3s var(--km-ease); }
.stage-card.active { border-left-color: var(--km-primary); }
.stage-head { display: flex; align-items: center; gap: 10px; padding: 12px 16px; cursor: pointer; user-select: none; }
.stage-no { font-family: var(--km-font-mono); font-size: 12px; color: var(--km-gray-500); }
.stage-head h4 { margin: 0; font-size: 14px; color: var(--km-gray-800); }
.stage-done { margin-left: auto; color: var(--km-success); font-size: 12px; }
.collab-pill { margin-left: auto; color: var(--km-primary); font-size: 12px; font-weight: 600; }
.running-pill { margin-left: auto; color: var(--km-warning); font-size: 12px; font-weight: 600; }
.expand-toggle { margin-left: 8px; color: var(--km-gray-500); }
.stage-body { padding: 12px; }

/* #30: 下一步建议横幅 - 答题完成后浮现在协同卡顶部 */
.collab-tip {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 12px; margin-bottom: 12px;
  border: 1px solid color-mix(in srgb, var(--km-primary) 35%, transparent);
  background: color-mix(in srgb, var(--km-primary-light) 45%, transparent);
  border-radius: var(--km-radius-sm);
  font-size: 13px; color: var(--km-gray-800);
}
.collab-icon { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; background: var(--km-primary); }
.collab-msg { flex: 1; line-height: 1.5; }
.collab-fold { border: 0; background: transparent; color: var(--km-gray-500); cursor: pointer; font-size: 12px; flex-shrink: 0; padding: 2px 4px; }
.collab-fold:hover { color: var(--km-gray-800); }
.stage-empty { padding: 16px; color: var(--km-gray-500); font-size: 13px; }

/* 总进度 + 实时动作 */
.progress-bar { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; padding: 8px 12px; margin-bottom: 12px; border-radius: var(--km-radius-sm); background: var(--km-bg-layer-2); font-size: 12px; color: var(--km-gray-600); }
.progress-done { color: var(--km-success); font-weight: 600; }
.progress-pending { color: var(--km-gray-500); }
.progress-live { color: var(--km-warning); font-weight: 600; }

/* Phase 3a: 只读流程进度 DAG */
.flow-block { margin-top: 4px; }
.flow-head { display: flex; align-items: center; justify-content: space-between; padding: 4px 12px; font-size: 12px; color: var(--km-gray-600); }
.flow-title { font-weight: 600; }
.flow-count { color: var(--km-gray-500); }
.flow-canvas { border: 1px solid var(--km-border-light); border-radius: var(--km-radius-sm); background: var(--km-bg-layer-2); }

/* 每 Agent 产出概览行 */
.prod-list { display: flex; flex-direction: column; gap: 8px; }
.prod-row { display: flex; gap: 10px; padding: 10px 12px; border: 1px solid var(--km-border-light); border-left: 3px solid var(--km-border-light); border-radius: var(--km-radius-sm); background: var(--km-bg-layer-2); transition: border-color 0.2s var(--km-ease); }
.prod-row.status-running { border-left-color: var(--km-warning); background: rgba(240,160,64,0.06); }
.prod-row.status-done { border-left-color: var(--km-success); }
.prod-row.status-deferred { border-left-color: var(--km-primary); background: color-mix(in srgb, var(--km-primary) 5%, transparent); }
.prod-row.status-degraded { border-left-color: #d98b3c; background: rgba(217,139,60,0.07); }
.prod-row.status-failed { border-left-color: var(--km-danger); }
.status-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; margin-top: 6px; background: var(--km-gray-400); }
.status-dot.dot-running { background: var(--km-warning); box-shadow: 0 0 0 3px rgba(240,160,64,0.15); }
.status-dot.dot-done { background: var(--km-success); }
.status-dot.dot-deferred { background: var(--km-primary); }
.status-dot.dot-degraded { background: #d98b3c; }
.status-dot.dot-failed { background: var(--km-danger); }
.prod-main { flex: 1; min-width: 0; }
.prod-head { display: flex; align-items: center; gap: 8px; margin-bottom: 2px; }
.prod-label { font-size: 13px; font-weight: 650; color: var(--km-gray-800); }
.prod-badge { font-size: 11px; padding: 1px 6px; border-radius: 8px; background: var(--km-bg-layer-3); color: var(--km-gray-600); }
.prod-badge.badge-running { background: rgba(240,160,64,0.15); color: var(--km-warning); }
.prod-badge.badge-done { background: rgba(52,179,126,0.12); color: var(--km-success); }
.prod-badge.badge-deferred { background: color-mix(in srgb, var(--km-primary) 12%, transparent); color: var(--km-primary); }
.prod-badge.badge-degraded { background: rgba(217,139,60,0.15); color: #b9680d; }
.prod-badge.badge-failed { background: rgba(224,85,85,0.12); color: var(--km-danger); }
.prod-badge.badge-idle { background: var(--km-bg-layer-3); color: var(--km-gray-500); }
.prod-retry { font-size: 11px; color: var(--km-danger); font-weight: 600; }
.prod-summary { margin: 0; font-size: 12px; line-height: 1.5; color: var(--km-gray-600); }

/* 原始日志 (可折叠细节) */
.log-detail { margin-top: 12px; border-top: 1px solid var(--km-border-light); padding-top: 10px; }
.log-detail summary { cursor: pointer; font-size: 12px; color: var(--km-gray-500); user-select: none; }
.log-detail summary:hover { color: var(--km-gray-800); }
.thread-body { display: flex; flex-direction: column; gap: 6px; margin-top: 8px; max-height: 240px; overflow-y: auto; padding-right: 4px; }
.thread-message { display: grid; grid-template-columns: 56px 1fr; gap: 8px; padding: 6px 10px; border-radius: var(--km-radius-sm); background: var(--km-bg-layer-3); border: 1px solid var(--km-border-light); }
.thread-message.reject { border-color: var(--km-danger); }
.thread-time { font-family: var(--km-font-mono); font-size: 10px; color: var(--km-gray-500); }
.thread-message p { margin: 0; font-size: 12px; line-height: 1.5; }

/* Phase 1: 续跑按钮 */
.resume-btn {
  margin-top: 10px; padding: 4px 10px; font-size: 12px; cursor: pointer;
  border: 1px solid var(--km-primary); color: var(--km-primary);
  background: transparent; border-radius: var(--km-radius-sm);
}
.resume-btn:hover { background: rgba(79,70,229,0.08); }

.agent-expand-enter-active, .agent-expand-leave-active { transition: all 0.3s var(--km-ease); overflow: hidden; }
.agent-expand-enter-from, .agent-expand-leave-to { opacity: 0; max-height: 0; }
.agent-expand-enter-to, .agent-expand-leave-from { opacity: 1; max-height: 700px; }

@media (prefers-reduced-motion: reduce) {
  .agent-expand-enter-active, .agent-expand-leave-active { transition: none; }
}
</style>
