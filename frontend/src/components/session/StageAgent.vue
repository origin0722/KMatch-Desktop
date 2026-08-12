<template>
  <section class="stage-card stage-agent km-surface" :class="{ active: isActive }">
    <header class="stage-head" @click="toggleExpand">
      <span class="stage-no">03</span>
      <h4>Agent 协同</h4>
      <span v-if="collabOn && !isActive" class="collab-pill">✨ 协同已就绪</span>
      <span v-else-if="hasLogs && !isActive" class="stage-done">✓ 已完成</span>
      <span v-if="status.pipelineRunning.value" class="running-pill">运行中</span>
      <span class="expand-toggle">{{ expanded ? '▾' : '▸' }}</span>
    </header>
    <transition name="agent-expand">
      <div v-show="expanded && hasLogs" class="stage-body">
        <!-- #30: 答题完成默认展示 AI 协同 — 下一步建议横幅, 可点击收起 -->
        <div v-if="collabOn" class="collab-tip">
          <span class="collab-icon">🤖</span>
          <span class="collab-msg"><strong>下一步建议</strong>　{{ nextSuggestion }}</span>
          <button class="collab-fold" title="收起协同" @click.stop="toggleExpand">收起 ▴</button>
        </div>
        <div class="cockpit-grid">
          <aside class="agent-flow">
            <template v-for="(agent, i) in status.agentNodes.value" :key="agent.key">
              <button class="flow-node" :class="[`status-${agent.status}`, { active: selectedAgent?.key === agent.key }]"
                      @click.stop="selectedAgent = agent">
                <span class="flow-icon">{{ agent.icon }}</span>
                <span class="flow-label">{{ agent.label }}</span>
                <span v-if="agent.retryCount > 0" class="flow-retry">×{{ agent.retryCount }}</span>
              </button>
              <span v-if="i < status.agentNodes.value.length - 1" class="flow-arrow">↓</span>
            </template>
          </aside>
          <section class="agent-thread">
            <div class="thread-header"><span>协同对话流</span></div>
            <div ref="logContainer" class="thread-body">
              <article v-for="(entry, idx) in parsedLogs" :key="idx" class="thread-message" :class="{ reject: entry.isReject }">
                <span class="thread-time">{{ entry.time || '--:--' }}</span>
                <p>{{ entry.msg }}</p>
              </article>
            </div>
          </section>
          <aside class="agent-evidence">
            <h5>{{ selectedAgent ? selectedAgent.label : '协作证据' }}</h5>
            <p class="evidence-desc">{{ selectedAgent ? selectedAgent.role : '点击左侧 Agent 查看。' }}</p>
            <div class="evidence-meta">
              <div><span class="label">状态</span> <strong>{{ selectedAgent ? statusLabel(selectedAgent.status) : '待选择' }}</strong></div>
              <div v-if="selectedAgent?.retryCount > 0"><span class="label">打回次数</span> <strong>{{ selectedAgent.retryCount }} 次</strong></div>
            </div>
          </aside>
        </div>
      </div>
    </transition>
    <div v-if="!hasLogs" class="stage-empty">尚无协同记录</div>
  </section>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { useAssessmentStore } from '@/stores/assessment'
import { useSessionStore } from '@/stores/session'
import { useAgentStatus } from '@/composables/useAgentStatus'

const store = useAssessmentStore()
const session = useSessionStore()
const status = useAgentStatus()

const selectedAgent = ref(null)
const logContainer = ref(null)
const expanded = ref(false)

const isActive = computed(() => session.activeStage === 'agent')
const rawLogs = computed(() => store.orchestrationLog || [])
const hasLogs = computed(() => rawLogs.value.length > 0)

// #30: 答题完成默认展示 AI 协同 — showCollab 点亮 (session store 由 assessment.phase=feedback 自动触发)
const collabOn = computed(() => session.showCollab && hasLogs.value)

// #30: 下一步建议 — 由反馈策略驱动, 指向协同产出与后续动作
const NEXT_STEP = {
  advance: '正确率高，建议进入进阶挑战：直接查看协同产出的进阶资源，或在右侧图谱定位进阶节点继续深入。',
  remediate: '掌握度一般，建议换个角度理解：协同已生成降维讲解与配套练习，可从中选取继续学习。',
  scaffold: '仍有基础薄弱点，建议先补前置基础：协同已生成补基础方案与知识点溯源，按序巩固即可。',
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
    const msg = msgStart >= 0 ? entry.slice(msgStart + 2) : entry
    lastTime = time
    result.push({ time, msg, isReject: entry?.includes('❌') || entry?.includes('打回') })
  }
  return result
})

function toggleExpand() { expanded.value = !expanded.value }
function statusLabel(s) { return { idle: '待命', running: '执行中', done: '完成', failed: '失败' }[s] || s }

// activeStage 进入 agent 时自动展开
watch(() => session.activeStage, (s) => {
  if (s === 'agent') expanded.value = true
}, { immediate: true })

// #30: 答题完成默认展示 AI 协同 — showCollab 点亮时自动展开 (可手动收起, 不强制展开)
watch(() => session.showCollab, (v) => {
  if (v && hasLogs.value) expanded.value = true
})

watch(parsedLogs, async () => {
  if (logContainer.value) {
    await nextTick()
    logContainer.value.scrollTop = logContainer.value.scrollHeight
  }
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

/* #30: 下一步建议横幅 — 答题完成后浮现在协同卡顶部 */
.collab-tip {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 12px; margin-bottom: 12px;
  border: 1px solid color-mix(in srgb, var(--km-primary) 35%, transparent);
  background: color-mix(in srgb, var(--km-primary-light) 45%, transparent);
  border-radius: var(--km-radius-sm);
  font-size: 13px; color: var(--km-gray-800);
}
.collab-icon { font-size: 15px; flex-shrink: 0; }
.collab-msg { flex: 1; line-height: 1.5; }
.collab-fold { border: 0; background: transparent; color: var(--km-gray-500); cursor: pointer; font-size: 12px; flex-shrink: 0; padding: 2px 4px; }
.collab-fold:hover { color: var(--km-gray-800); }
.stage-empty { padding: 16px; color: var(--km-gray-500); font-size: 13px; }

.cockpit-grid { display: grid; grid-template-columns: 200px 1fr 240px; gap: 12px; min-height: 360px; }
.agent-flow { display: flex; flex-direction: column; align-items: center; gap: 0; padding-top: 12px; overflow-y: auto; }
.flow-node { display: flex; flex-direction: column; align-items: center; gap: 2px; border: 2px solid var(--km-border-light); background: var(--km-bg-layer-2); border-radius: 10px; padding: 8px 10px; min-width: 140px; cursor: pointer; transition: all 0.2s var(--km-ease); position: relative; }
.flow-node:hover { border-color: var(--km-primary); }
.flow-node.active { border-color: var(--km-primary); box-shadow: 0 0 0 3px rgba(108,124,224,0.15); }
.flow-node.status-running { border-color: var(--km-warning); background: rgba(240,160,64,0.1); animation: pulse 1.6s ease-in-out infinite; }
.flow-node.status-done { border-color: var(--km-success); background: rgba(52,179,126,0.08); }
.flow-node.status-failed { border-color: var(--km-danger); background: rgba(224,85,85,0.08); }
.flow-icon { font-size: 18px; }
.flow-label { font-size: 12px; font-weight: 600; color: var(--km-gray-800); }
.flow-retry { position: absolute; top: -6px; right: -6px; background: var(--km-danger); color: #fff; font-size: 10px; border-radius: 8px; padding: 1px 5px; }
.flow-arrow { color: var(--km-gray-400); font-size: 18px; margin: 4px 0; line-height: 1; }
.agent-thread { display: flex; flex-direction: column; min-width: 0; border: 1px solid var(--km-border-light); border-radius: var(--km-radius-sm); }
.thread-header { height: 36px; padding: 0 12px; display: flex; align-items: center; border-bottom: 1px solid var(--km-border-light); font-weight: 650; font-size: 13px; }
.thread-body { flex: 1; overflow-y: auto; padding: 10px; display: flex; flex-direction: column; gap: 8px; max-height: 320px; }
.thread-message { display: grid; grid-template-columns: 56px 1fr; gap: 8px; padding: 8px 10px; border-radius: var(--km-radius-sm); background: var(--km-bg-layer-3); border: 1px solid var(--km-border-light); }
.thread-message.reject { border-color: var(--km-danger); }
.thread-time { font-family: var(--km-font-mono); font-size: 10px; color: var(--km-gray-500); }
.thread-message p { margin: 0; font-size: 12px; line-height: 1.5; }
.agent-evidence { padding: 8px; }
.agent-evidence h5 { margin: 0 0 6px; font-size: 13px; color: var(--km-gray-800); }
.evidence-desc { color: var(--km-gray-500); font-size: 11px; line-height: 1.5; margin: 0; }
.evidence-meta { display: flex; flex-direction: column; gap: 6px; margin-top: 8px; font-size: 11px; }
.evidence-meta .label { color: var(--km-gray-500); font-size: 11px; margin-right: 4px; }

@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }

.agent-expand-enter-active, .agent-expand-leave-active { transition: all 0.3s var(--km-ease); overflow: hidden; }
.agent-expand-enter-from, .agent-expand-leave-to { opacity: 0; max-height: 0; }
.agent-expand-enter-to, .agent-expand-leave-from { opacity: 1; max-height: 600px; }

@media (prefers-reduced-motion: reduce) {
  .status-dot.status-running { animation: none; }
  .agent-expand-enter-active, .agent-expand-leave-active { transition: none; }
}
@media (max-width: 1100px) { .cockpit-grid { grid-template-columns: 160px 1fr; } .agent-evidence { grid-column: 1 / -1; } }
</style>
