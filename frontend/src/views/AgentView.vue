<template>
  <div class="agent-page km-workbench agent-cockpit">
    <!-- ============================================================ -->
    <!-- 页面标题栏 -->
    <!-- ============================================================ -->
    <div class="km-workbench-header">
      <div>
        <p class="km-workbench-kicker">multi-agent orchestration</p>
        <h3 class="km-workbench-title">Agent 协同 cockpit</h3>
        <p class="km-workbench-desc">
          把调度链路、Agent 状态和协作证据放在同一张工作台里。这里展示每个 Agent 为什么行动、正在处理什么、交付了什么。
        </p>
      </div>
      <el-tag
        :type="status.pipelineRunning.value ? 'warning' : 'success'"
        size="small"
      >
        {{ status.pipelineRunning.value ? '运行中' : '已完成' }}
      </el-tag>
    </div>

    <!-- ============================================================ -->
    <!-- 空状态 -->
    <!-- ============================================================ -->
    <div v-if="!hasLogs" class="km-empty-state agent-empty">
      <div>
        <h4>还没有协同记录</h4>
        <p>完成一次学情测评后，这里会显示主控调度和子 Agent 的协作过程。</p>
        <el-button type="primary" @click="sidebar.setView('assessment')">
          前往学情诊断
        </el-button>
      </div>
    </div>

    <!-- ============================================================ -->
    <!-- 三区 Agent cockpit -->
    <!-- ============================================================ -->
    <div v-else class="cockpit-grid">
      <!-- 左：Agent 花名册 -->
      <aside class="agent-roster km-surface-quiet">
        <button
          v-for="agent in status.agentNodes.value"
          :key="agent.key"
          class="agent-roster-item"
          :class="{ active: selectedAgent?.key === agent.key }"
          @click="selectedAgent = agent"
        >
          <span class="status-dot" :class="`status-${agent.status}`" />
          <span class="agent-copy">
            <strong>{{ agent.label }}</strong>
            <small>{{ agent.role }}</small>
            <span class="sr-only">状态：{{ statusLabel(agent.status) }}</span>
          </span>
        </button>
      </aside>

      <!-- 中：Agent 协作对话流 -->
      <section class="agent-thread km-surface">
        <div class="thread-header">
          <span>协同对话流</span>
          <button class="thread-mode" @click="logAutoScroll = !logAutoScroll">
            {{ logAutoScroll ? '自动滚动' : '手动浏览' }}
          </button>
        </div>
        <div ref="logContainer" class="thread-body">
          <article
            v-for="(entry, idx) in parsedLogs"
            :key="idx"
            class="thread-message"
            :class="{ reject: entry.isReject }"
          >
            <span class="thread-time">{{ entry.time || '--:--' }}</span>
            <p>{{ entry.msg }}</p>
          </article>
        </div>
        <div class="agent-question-bar">
          <input
            ref="questionInput"
            v-model="question"
            data-test="agent-question-input"
            aria-label="追问 Agent"
            placeholder="追问 Agent：为什么这样规划？"
            @keyup.enter="onAsk"
          />
          <button data-test="agent-question-button" @click="onAsk">追问</button>
        </div>
      </section>

      <!-- 右：选中 Agent 协作证据 -->
      <aside class="agent-evidence km-surface-quiet">
        <h4>{{ selectedAgent ? selectedAgent.label : '协作证据' }}</h4>
        <p class="evidence-desc">
          {{ selectedAgent ? selectedAgent.role : '点击左侧 Agent 查看职责和产出摘要。' }}
        </p>
        <div class="km-evidence-list">
          <div class="km-evidence-row">
            <span>状态</span>
            <strong>{{ selectedAgent ? statusLabel(selectedAgent.status) : '待选择' }}</strong>
          </div>
          <div class="km-evidence-row" v-if="selectedAgent?.retryCount > 0">
            <span>打回次数</span>
            <strong>{{ selectedAgent.retryCount }} 次</strong>
          </div>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup>
/**
 * KMatch Agent 协同可视化页 — Agent cockpit 布局
 *
 * 数据源：assessment store → orchestrationLog[]
 * 状态推导：useAgentStatus composable
 * 三区结构：Agent 花名册 / 协作对话流 / 协作证据
 *
 * 注：追问输入框为本地交互入口，本阶段不接后端，点击/回车仅聚焦输入框。
 */
import { ref, computed, watch, nextTick } from 'vue'
import { useAssessmentStore } from '@/stores/assessment'
import { useSidebarStore } from '@/stores/sidebar'
import { useAgentStatus } from '@/composables/useAgentStatus'

const store = useAssessmentStore()
const sidebar = useSidebarStore()
const status = useAgentStatus()

// ---------------------------------------------------------------
// 状态
// ---------------------------------------------------------------
const selectedAgent = ref(null)
const logAutoScroll = ref(true)
const logContainer = ref(null)
const question = ref('')
const questionInput = ref(null)

// ---------------------------------------------------------------
// 日志
// ---------------------------------------------------------------
const rawLogs = computed(() => store.orchestrationLog || [])
const hasLogs = computed(() => rawLogs.value.length > 0)

/** 解析后的日志：连续无时间戳行继承上行时间 */
const parsedLogs = computed(() => {
  const result = []
  let lastTime = ''
  for (const entry of rawLogs.value) {
    const m = entry?.match(/^\[(.+?)\]/)
    const time = m ? m[1] : lastTime
    const msgStart = entry?.indexOf('] ')
    const msg = msgStart >= 0 ? entry.slice(msgStart + 2) : entry
    lastTime = time
    result.push({
      time,
      msg,
      isReject: entry?.includes('❌') || entry?.includes('打回'),
    })
  }
  return result
})

watch(parsedLogs, async () => {
  if (logAutoScroll.value && logContainer.value) {
    await nextTick()
    logContainer.value.scrollTop = logContainer.value.scrollHeight
  }
})

// ---------------------------------------------------------------
// 追问入口（本地 affordance，不接后端）
// ---------------------------------------------------------------
function onAsk() {
  // 本阶段仅保留输入焦点，不触发后端调用
  questionInput.value?.focus()
}

// ---------------------------------------------------------------
// 状态映射
// ---------------------------------------------------------------
function statusLabel(s) {
  return { idle: '待命', running: '执行中', done: '完成', failed: '失败' }[s] || s
}
</script>

<style scoped>
.agent-page { padding: 0; }

/* 视觉隐藏，仅供屏幕阅读器读取（如 Agent 状态文本） */
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

.cockpit-grid {
  display: grid;
  grid-template-columns: 220px minmax(360px, 1fr) 280px;
  gap: 14px;
  min-height: 560px;
}

/* ---- 左：Agent 花名册 ---- */
.agent-roster,
.agent-evidence { padding: 12px; }
.agent-roster-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  border: 0;
  background: transparent;
  border-radius: var(--km-radius-sm);
  padding: 10px;
  text-align: left;
  color: var(--km-gray-700);
  cursor: pointer;
  transition: background 0.16s var(--km-ease), transform 0.16s var(--km-ease);
}
.agent-roster-item:hover,
.agent-roster-item.active {
  background: var(--km-primary-light);
  color: var(--km-primary-active);
}
.agent-roster-item:active { transform: translateY(1px); }
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--km-gray-400);
  flex-shrink: 0;
}
.status-dot.status-running { background: var(--km-warning); }
.status-dot.status-done { background: var(--km-success); }
.status-dot.status-failed { background: var(--km-danger); }
.agent-copy { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.agent-copy strong { font-size: 13px; }
.agent-copy small { font-size: 11px; color: var(--km-gray-500); }

/* ---- 中：协作对话流 ---- */
.agent-thread { display: flex; flex-direction: column; min-width: 0; }
.thread-header {
  height: 42px;
  padding: 0 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--km-border-light);
  font-weight: 650;
}
.thread-mode {
  border: 0;
  background: transparent;
  color: var(--km-gray-500);
  cursor: pointer;
}
.thread-body {
  flex: 1;
  overflow-y: auto;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.thread-message {
  display: grid;
  grid-template-columns: 64px 1fr;
  gap: 10px;
  padding: 10px 12px;
  border-radius: var(--km-radius-sm);
  background: var(--km-bg-layer-3);
  border: 1px solid var(--km-border-light);
}
.thread-message.reject { border-color: var(--km-danger); }
.thread-time { font-family: var(--km-font-mono); font-size: 11px; color: var(--km-gray-500); }
.thread-message p { margin: 0; font-size: 13px; line-height: 1.55; }

/* ---- 追问输入条 ---- */
.agent-question-bar {
  display: flex;
  gap: 8px;
  padding: 12px;
  border-top: 1px solid var(--km-border-light);
}
.agent-question-bar input {
  flex: 1;
  border: 1px solid var(--km-border);
  border-radius: var(--km-radius-sm);
  background: var(--km-bg-layer-3);
  color: var(--km-gray-700);
  padding: 8px 10px;
}
.agent-question-bar button {
  border: 0;
  border-radius: var(--km-radius-sm);
  background: var(--km-primary);
  color: var(--km-primary-text);
  padding: 0 14px;
  cursor: pointer;
}

/* ---- 右：协作证据 ---- */
.agent-evidence h4 { margin: 0 0 6px; font-size: 14px; font-weight: 700; }
.evidence-desc { color: var(--km-gray-500); font-size: 12px; line-height: 1.6; margin: 0 0 12px; }

/* ---- 空状态 ---- */
.agent-empty { text-align: center; }
.agent-empty h4 { margin: 0 0 6px; font-size: 15px; }
.agent-empty p { margin: 0 0 12px; color: var(--km-gray-500); font-size: 13px; }

@media (max-width: 1100px) {
  .cockpit-grid { grid-template-columns: 180px 1fr; }
  .agent-evidence { grid-column: 1 / -1; }
}
</style>
