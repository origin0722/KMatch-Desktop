<template>
  <section class="stage-card stage-agent km-surface" :class="{ active: isActive }">
    <header class="stage-head" @click="toggleExpand">
      <span class="stage-no">03</span>
      <h4>Agent 协同</h4>
      <span v-if="hasLogs && !isActive" class="stage-done">✓ 已完成</span>
      <span v-if="status.pipelineRunning.value" class="running-pill">运行中</span>
      <span class="expand-toggle">{{ expanded ? '▾' : '▸' }}</span>
    </header>
    <transition name="agent-expand">
      <div v-show="expanded && hasLogs" class="stage-body">
        <div class="cockpit-grid">
          <aside class="agent-roster">
            <button v-for="agent in status.agentNodes.value" :key="agent.key"
              class="agent-roster-item" :class="{ active: selectedAgent?.key === agent.key }"
              @click.stop="selectedAgent = agent">
              <span class="status-dot" :class="`status-${agent.status}`" />
              <span class="agent-copy"><strong>{{ agent.label }}</strong><small>{{ agent.role }}</small></span>
            </button>
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

// activeStage 进入 agent 时自动展开
watch(() => session.activeStage, (s) => {
  if (s === 'agent') expanded.value = true
}, { immediate: true })

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
.running-pill { margin-left: auto; color: var(--km-warning); font-size: 12px; font-weight: 600; }
.expand-toggle { margin-left: 8px; color: var(--km-gray-500); }
.stage-body { padding: 12px; }
.stage-empty { padding: 16px; color: var(--km-gray-500); font-size: 13px; }

.cockpit-grid { display: grid; grid-template-columns: 200px 1fr 240px; gap: 12px; min-height: 360px; }
.agent-roster-item { width: 100%; display: flex; align-items: center; gap: 8px; border: 0; background: transparent; border-radius: var(--km-radius-sm); padding: 8px; text-align: left; color: var(--km-gray-700); cursor: pointer; }
.agent-roster-item:hover, .agent-roster-item.active { background: var(--km-primary-light); color: var(--km-primary-active); }
.status-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--km-gray-400); flex-shrink: 0; }
.status-dot.status-running { background: var(--km-warning); animation: pulse 1.6s ease-in-out infinite; }
.status-dot.status-done { background: var(--km-success); }
.status-dot.status-failed { background: var(--km-danger); }
.agent-copy { display: flex; flex-direction: column; gap: 2px; }
.agent-copy strong { font-size: 12px; }
.agent-copy small { font-size: 10px; color: var(--km-gray-500); }
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
