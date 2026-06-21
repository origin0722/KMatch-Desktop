# Learning Session 三合一 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把答题 + Agent 协同 cockpit + 专属图谱三合一成一条纵向学习会话流 (LearningSession 视图), 会话流主体 + 至多 1 个右侧分屏视图对照, 与右侧 AI 助手双向联动。

**Architecture:** 新建 LearningSession.vue 主视图 + 4 个阶段卡子组件 (StageGoal/StageQuiz/StageAgent/StageGraph) + SplitPane 分屏容器 + session store (activeStage 为 computed, 派生自 assessment store, 不独立存状态)。从 Assessment.vue / AgentView.vue 搬运逻辑, 删除原视图。复用 --km-* token 与 km-workbench 原语。所有动画 transform/opacity 为主, honor prefers-reduced-motion。

**Tech Stack:** Vue 3 + Pinia + Element Plus + ECharts/G6 (现有), Vitest 2.1, --km-* CSS token, 无新依赖。

**Spec:** `docs/superpowers/specs/2026-06-22-learning-session-design.md`

---

## File Structure

**新增:**
- `frontend/src/stores/session.js` — 会话流状态: `activeStage` (computed from assessment store), `splitView` (null|'graph'|'learning'|'dashboard'), `setSplitView/closeSplit`
- `frontend/src/views/LearningSession.vue` — 主视图, 装载 4 阶段卡 + SplitPane
- `frontend/src/components/session/StageGoal.vue` — 阶段①目标设定 (搬自 Assessment 输入区)
- `frontend/src/components/session/StageQuiz.vue` — 阶段②答题 (搬自 Assessment interactive 三阶段)
- `frontend/src/components/session/StageAgent.vue` — 阶段③协同 (搬自 AgentView cockpit, 折叠展开)
- `frontend/src/components/session/StageGraph.vue` — 阶段④图谱摘要 + 分屏触发
- `frontend/src/components/session/SplitPane.vue` — 主从分屏容器 (右半 v-show 渲染左侧栏视图)
- `frontend/src/__tests__/session-store.test.js` — activeStage 派生 + 分屏控制
- `frontend/src/__tests__/learning-session.test.js` — 阶段卡渲染 + 推进 + 分屏

**修改:**
- `frontend/src/stores/sidebar.js` — ACTIVITY_ITEMS 替换 assessment 为 learning-session, 移除 agents
- `frontend/src/ide/MainArea.vue` — 装载 LearningSession; 移除 AgentView 装载
- `frontend/src/stores/chat.js` — buildSystemPrompt 注入学情画像 (扩展 tutorMode 分支为无条件注入)
- `frontend/src/__tests__/titlebar-menu.test.js` — 断言更新 (答题测评→学习会话, Agent 协同移除)

**删除:**
- `frontend/src/views/Assessment.vue` (逻辑搬进 StageGoal/StageQuiz)
- `frontend/src/views/AgentView.vue` (逻辑搬进 StageAgent)
- `frontend/src/__tests__/assessment-redesign.test.js` (被 session-store + learning-session 测试取代)
- `frontend/src/__tests__/agent-view-redesign.test.js` (同上)

---

## Task 1: session store (activeStage 派生 + 分屏控制)

**Files:**
- Create: `frontend/src/stores/session.js`
- Test: `frontend/src/__tests__/session-store.test.js`

- [ ] **Step 1: Write the failing test**

Create `frontend/src/__tests__/session-store.test.js`:

```js
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

// mock assessment store (session.activeStage 派生自它)
vi.mock('@/stores/assessment', () => ({
  useAssessmentStore: () => ({
    hasResults: false,
    loading: false,
    phase: 'idle',
    orchestrationLog: [],
  }),
}))

const { useSessionStore } = await import('@/stores/session')

describe('session store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('activeStage=goal 当无结果无日志无 loading', () => {
    const s = useSessionStore()
    expect(s.activeStage).toBe('goal')
  })

  it('splitView 默认 null, setSplitView/closeSplit 控制', () => {
    const s = useSessionStore()
    expect(s.splitView).toBeNull()
    s.setSplitView('graph')
    expect(s.splitView).toBe('graph')
    s.closeSplit()
    expect(s.splitView).toBeNull()
  })

  it('setSplitView 拒绝非法视图名', () => {
    const s = useSessionStore()
    s.setSplitView('code')
    expect(s.splitView).toBeNull() // code 不在允许列表
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- session-store.test.js`
Expected: FAIL — `Cannot find module '@/stores/session'`

- [ ] **Step 3: Create session store**

Create `frontend/src/stores/session.js`:

```js
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
 */
import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { useAssessmentStore } from '@/stores/assessment'

// 允许作为分屏右半的左侧栏视图 (code 不含, 因 code 是编辑器非产出)
const SPLITTABLE = new Set(['graph', 'learning', 'dashboard'])

export const useSessionStore = defineStore('session', () => {
  const splitView = ref(null)

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

  return { activeStage, splitView, setSplitView, closeSplit }
})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- session-store.test.js`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/stores/session.js frontend/src/__tests__/session-store.test.js
git commit -m "feat(session): session store — activeStage 派生 + 分屏控制"
```

---

## Task 2: StageGoal 阶段①目标设定卡

**Files:**
- Create: `frontend/src/components/session/StageGoal.vue`

搬自 `Assessment.vue` 输入区 (form.targetDirection/scene + presetDirections + handleStart/handleQuickDemo)。无独立单测 (逻辑等价于原 Assessment, 已有 store 测覆盖 startAssessment); 由 learning-session 集成测覆盖。

- [ ] **Step 1: Create StageGoal.vue**

Create `frontend/src/components/session/StageGoal.vue`:

```vue
<template>
  <section class="stage-card stage-goal km-surface">
    <header class="stage-head">
      <span class="stage-no">01</span>
      <h4>目标设定</h4>
    </header>
    <div class="stage-body">
      <el-form :model="form" label-width="100px" label-position="left" @submit.prevent="handleStart">
        <el-form-item label="学习目标方向" required>
          <div class="preset-directions">
            <el-tag
              v-for="d in presetDirections"
              :key="d"
              :effect="form.targetDirection === d ? 'dark' : 'plain'"
              :type="form.targetDirection === d ? '' : 'info'"
              class="preset-tag"
              @click="form.targetDirection = d"
            >{{ d }}</el-tag>
          </div>
          <el-input
            v-model="form.targetDirection"
            placeholder="或自定义方向（如：Python 基础语法入门）"
            :maxlength="200"
            show-word-limit
          />
        </el-form-item>
        <el-form-item label="场景">
          <el-select v-model="form.scene" style="width: 200px;">
            <el-option label="无项目技能训练" value="no_project" />
            <el-option label="有项目二次开发" value="with_project" />
          </el-select>
          <span class="hint-text">选择学习场景类型</span>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" size="large" :disabled="!canStart" @click="handleStart">
            开始测评 →
          </el-button>
          <el-button size="large" :loading="store.loading" @click="handleQuickDemo">
            快速体验（自动作答）
          </el-button>
          <span v-if="!canStart" class="hint-text">请选择或输入学习目标方向</span>
        </el-form-item>
      </el-form>
    </div>
  </section>
</template>

<script setup>
import { reactive, computed } from 'vue'
import { useAssessmentStore } from '@/stores/assessment'

const store = useAssessmentStore()

const form = reactive({ targetDirection: '', scene: 'no_project' })
const presetDirections = [
  'Python 基础语法入门', '数据结构与算法', '面向对象编程',
  'Python 进阶', '常用库与工具', '项目实战',
]
const canStart = computed(() => form.targetDirection.trim().length > 0)

async function handleStart() {
  if (!canStart.value) return
  await store.startAssessment({ targetDirection: form.targetDirection.trim(), scene: form.scene })
}
async function handleQuickDemo() {
  if (!canStart.value) return
  await store.startDemoStream({ targetDirection: form.targetDirection.trim(), scene: form.scene })
}
</script>

<style scoped>
.stage-card { border-left: 3px solid var(--km-border-light); border-radius: var(--km-radius); overflow: hidden; }
.stage-head { display: flex; align-items: center; gap: 10px; padding: 12px 16px; border-bottom: 1px solid var(--km-border-light); }
.stage-no { font-family: var(--km-font-mono); font-size: 12px; color: var(--km-gray-500); }
.stage-head h4 { margin: 0; font-size: 14px; color: var(--km-gray-800); }
.stage-body { padding: 16px; }
.preset-directions { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 10px; }
.preset-tag { cursor: pointer; font-size: 13px; user-select: none; }
.preset-tag:hover { opacity: 0.85; }
.hint-text { margin-left: 12px; color: var(--km-gray-500); font-size: 13px; }
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/session/StageGoal.vue
git commit -m "feat(session): StageGoal 阶段①目标设定卡"
```

---

## Task 3: StageQuiz 阶段②答题卡

**Files:**
- Create: `frontend/src/components/session/StageQuiz.vue`

搬自 Assessment.vue 的 answering + feedback 两段 (interactive 三阶段的 2、3)。含 loading SSE 进度展示 (interactive 判分 loading 也在此卡内, 不进阶段③)。

- [ ] **Step 1: Create StageQuiz.vue**

Create `frontend/src/components/session/StageQuiz.vue`:

```vue
<template>
  <section class="stage-card stage-quiz km-surface" :class="{ active: isActive }">
    <header class="stage-head">
      <span class="stage-no">02</span>
      <h4>学情答题</h4>
      <span v-if="store.phase === 'feedback'" class="stage-done">✓ 已完成</span>
    </header>
    <div class="stage-body">
      <!-- answering 阶段 -->
      <template v-if="store.phase === 'answering' && !store.loading">
        <div class="quiz-header">
          <span>共 {{ store.pendingQuestions.length }} 题</span>
          <el-button size="small" @click="store.backToInput()">← 返回</el-button>
        </div>
        <div v-for="(q, idx) in store.pendingQuestions" :key="idx" class="quiz-item">
          <div class="quiz-question">
            <el-tag size="small" type="info">{{ idx + 1 }}</el-tag>
            <el-tag size="small">{{ typeLabel(q.type) }}</el-tag>
            <span class="q-text">{{ q.question }}</span>
          </div>
          <el-radio-group v-if="q.type === 'choice'" v-model="store.userAnswers[idx]" class="quiz-options">
            <el-radio v-for="opt in q.options" :key="opt" :value="optLabel(opt)" class="quiz-option">{{ opt }}</el-radio>
          </el-radio-group>
          <el-input v-else-if="q.type === 'fill'" v-model="store.userAnswers[idx]" placeholder="请输入答案" class="quiz-fill" />
          <el-input v-else v-model="store.userAnswers[idx]" type="textarea" :rows="3" placeholder="请输入答案" />
        </div>
        <div class="quiz-submit">
          <el-button type="primary" size="large" @click="handleSubmitAnswers">提交答题 →</el-button>
          <el-button size="large" @click="autoFillDemo">一键填演示答案</el-button>
        </div>
      </template>

      <!-- feedback 阶段 -->
      <template v-if="store.phase === 'feedback'">
        <el-descriptions :column="3" border size="small" style="margin-bottom: 12px;">
          <el-descriptions-item label="正确率">
            {{ store.assessment?.correct_count }} / {{ store.assessment?.total_count }} ({{ (store.accuracy * 100).toFixed(0) }}%)
          </el-descriptions-item>
          <el-descriptions-item label="理论水平">{{ levelLabel(store.profile?.theory_level) }}</el-descriptions-item>
          <el-descriptions-item label="反馈策略">
            <el-tag :type="strategyTagType(store.feedbackStrategy)" size="small">{{ strategyLabel(store.feedbackStrategy) }}</el-tag>
          </el-descriptions-item>
        </el-descriptions>
        <el-button v-if="store.feedbackStrategy && !store.feedbackContent" size="small" type="primary" :loading="store.loading" @click="store.fetchFeedback()">
          获取针对性反馈 →
        </el-button>
        <div v-if="store.feedbackContent" class="feedback-resources">
          <el-card v-for="(r, i) in (store.feedbackContent.resources || [])" :key="i" shadow="never" class="resource-item">
            <template #header>
              <el-tag size="small">{{ contentTypeLabel(r.content_type) }}</el-tag>
              <span style="margin-left: 8px;">{{ r.title || r.target_node_id }}</span>
            </template>
            <MarkdownViewer :content="r.content" />
          </el-card>
        </div>
      </template>

      <!-- interactive loading (判分/取反馈, 不进阶段③) -->
      <div v-if="store.loading && store.phase !== 'answering'" class="quiz-loading" v-loading="true" element-loading-text="处理中…"></div>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { useAssessmentStore } from '@/stores/assessment'
import { useSessionStore } from '@/stores/session'
import MarkdownViewer from '@/components/MarkdownViewer.vue'

const store = useAssessmentStore()
const session = useSessionStore()
const isActive = computed(() => session.activeStage === 'quiz')

function typeLabel(t) { return { choice: '选择题', fill: '填空题', code: '代码题', judge: '判断题' }[t] || t || '题' }
function optLabel(opt) { const m = String(opt).match(/^([A-Z])[.、．]/); return m ? m[1] : String(opt) }
function levelLabel(l) { return { 1: '零基础', 2: '入门', 3: '进阶', 4: '高级', 5: '专家' }[l] ?? `Lv.${l}` }
const STRATEGY = { advance: '进阶挑战', remediate: '降维解释', scaffold: '补前置基础' }
function strategyLabel(s) { return STRATEGY[s] || s || '-' }
function strategyTagType(s) { return { advance: 'success', remediate: 'warning', scaffold: 'danger' }[s] || 'info' }
const CT = { lecture: '讲义', practice: '实操指南', quiz: '测试题', explanation: '讲解', exercise: '练习' }
function contentTypeLabel(t) { return CT[t] || t || '资源' }

async function handleSubmitAnswers() {
  const unanswered = store.userAnswers.filter((a) => !a || String(a).trim() === '').length
  if (unanswered === store.pendingQuestions.length) return
  await store.submitAssessmentAnswers()
}
function autoFillDemo() {
  store.pendingQuestions.forEach((q, idx) => {
    if (q.type === 'choice' && q.options?.length) store.userAnswers[idx] = optLabel(q.options[0])
    else store.userAnswers[idx] = '示例答案'
  })
}
</script>

<style scoped>
.stage-card { border-left: 3px solid var(--km-border-light); border-radius: var(--km-radius); overflow: hidden; transition: border-color 0.3s var(--km-ease); }
.stage-card.active { border-left-color: var(--km-primary); }
.stage-head { display: flex; align-items: center; gap: 10px; padding: 12px 16px; border-bottom: 1px solid var(--km-border-light); }
.stage-no { font-family: var(--km-font-mono); font-size: 12px; color: var(--km-gray-500); }
.stage-head h4 { margin: 0; font-size: 14px; color: var(--km-gray-800); }
.stage-done { margin-left: auto; color: var(--km-success); font-size: 12px; }
.stage-body { padding: 16px; }
.quiz-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.quiz-item { padding: 12px 0; border-bottom: 1px solid var(--km-border-light); }
.quiz-question { display: flex; align-items: flex-start; gap: 8px; margin-bottom: 8px; font-size: 13px; }
.q-text { flex: 1; }
.quiz-options { display: flex; flex-direction: column; gap: 6px; padding-left: 28px; }
.quiz-option { margin-right: 0 !important; }
.quiz-fill { max-width: 360px; }
.quiz-submit { display: flex; gap: 12px; margin-top: 16px; }
.feedback-resources { display: flex; flex-direction: column; gap: 12px; margin-top: 12px; }
.resource-item { background: var(--km-bg-layer-1); }
.quiz-loading { min-height: 80px; }
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/session/StageQuiz.vue
git commit -m "feat(session): StageQuiz 阶段②答题卡 (answering+feedback)"
```

---

## Task 4: StageAgent 阶段③协同卡

**Files:**
- Create: `frontend/src/components/session/StageAgent.vue`

搬自 AgentView.vue cockpit 三栏, 默认折叠, activeStage==='agent' 或 hasLogs 时展开。

- [ ] **Step 1: Create StageAgent.vue**

Create `frontend/src/components/session/StageAgent.vue`:

```vue
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
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/session/StageAgent.vue
git commit -m "feat(session): StageAgent 阶段③协同 cockpit (折叠展开)"
```

---

## Task 5: StageGraph 阶段④图谱摘要卡 + 分屏触发

**Files:**
- Create: `frontend/src/components/session/StageGraph.vue`

图谱摘要 (节点数/学时/掌握度) + "查看完整图谱"(切左侧栏 graph) + "对照分屏"(setSplitView('graph'))。

- [ ] **Step 1: Create StageGraph.vue**

Create `frontend/src/components/session/StageGraph.vue`:

```vue
<template>
  <section class="stage-card stage-graph km-surface" :class="{ active: isActive }">
    <header class="stage-head">
      <span class="stage-no">04</span>
      <h4>专属知识图谱</h4>
      <span class="stage-done">✓ 已生成</span>
    </header>
    <div class="stage-body">
      <div class="graph-summary">
        <div class="summary-item">
          <div class="summary-val km-mono-number">{{ nodeCount }}</div>
          <div class="summary-label">路径节点</div>
        </div>
        <div class="summary-item">
          <div class="summary-val km-mono-number">{{ hours }}</div>
          <div class="summary-label">预计学时</div>
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
const hours = computed(() => kg.value.estimated_total_hours?.toFixed?.(1) ?? '--')
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
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/session/StageGraph.vue
git commit -m "feat(session): StageGraph 阶段④图谱摘要 + 分屏触发"
```

---

## Task 6: SplitPane 主从分屏容器

**Files:**
- Create: `frontend/src/components/session/SplitPane.vue`

右半 v-show 渲染左侧栏视图组件 (graph/learning/dashboard), 顶部标签 + 关闭钮。grid 列宽过渡动画。

- [ ] **Step 1: Create SplitPane.vue**

Create `frontend/src/components/session/SplitPane.vue`:

```vue
<template>
  <div class="split-pane" :class="{ open: !!view }">
    <div class="split-header">
      <span class="split-title">{{ label }}</span>
      <button class="split-close" title="关闭分屏" @click="session.closeSplit()">×</button>
    </div>
    <div class="split-content">
      <!-- v-show 常驻, 不 v-if 重建 (与 S6 治理一致, G6/Monaco 状态保留) -->
      <KnowledgeGraph v-show="view === 'graph'" />
      <Learning v-show="view === 'learning'" />
      <Dashboard v-show="view === 'dashboard'" />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useSessionStore } from '@/stores/session'
import KnowledgeGraph from '@/views/KnowledgeGraph.vue'
import Learning from '@/views/Learning.vue'
import Dashboard from '@/views/Dashboard.vue'

const session = useSessionStore()
const view = computed(() => session.splitView)
const labels = { graph: '知识图谱', learning: '学习资源', dashboard: '数据看板' }
const label = computed(() => labels[view.value] || '')
</script>

<style scoped>
.split-pane {
  display: flex; flex-direction: column;
  width: 0; min-width: 0; overflow: hidden;
  border-left: 1px solid var(--km-border-light);
  background: var(--km-bg-layer-1);
  transition: width 0.35s var(--km-ease), min-width 0.35s var(--km-ease), opacity 0.2s var(--km-ease);
  opacity: 0;
}
.split-pane.open { width: 50%; min-width: 360px; opacity: 1; }
.split-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 12px; border-bottom: 1px solid var(--km-border-light);
  font-size: 13px; font-weight: 650; color: var(--km-gray-800);
}
.split-close {
  border: 0; background: transparent; color: var(--km-gray-500);
  font-size: 18px; cursor: pointer; line-height: 1;
}
.split-close:hover { color: var(--km-gray-800); }
.split-content { flex: 1; min-height: 0; overflow: auto; padding: 12px; }
@media (prefers-reduced-motion: reduce) {
  .split-pane { transition: none; }
}
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/session/SplitPane.vue
git commit -m "feat(session): SplitPane 主从分屏容器 (v-show 常驻)"
```

---

## Task 7: LearningSession 主视图 + 进度连线

**Files:**
- Create: `frontend/src/views/LearningSession.vue`
- Test: `frontend/src/__tests__/learning-session.test.js`

装载 4 阶段卡 + SplitPane, 左侧进度竖线, 阶段卡按 activeStage 三态展示, 自动滚动到当前阶段。

- [ ] **Step 1: Write the failing test**

Create `frontend/src/__tests__/learning-session.test.js`:

```js
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/stores/assessment', () => ({
  useAssessmentStore: () => ({
    hasResults: false, loading: false, phase: 'idle', orchestrationLog: [],
    profile: null, knowledgeGraph: null,
  }),
}))

const LearningSession = (await import('@/views/LearningSession.vue')).default

describe('LearningSession', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('渲染 4 个阶段卡 + 进度连线', () => {
    const w = mount(LearningSession, { global: { plugins: [createPinia()], stubs: ['el-button','el-form','el-form-item','el-input','el-select','el-option','el-tag','el-descriptions','el-descriptions-item','el-card','el-radio-group','el-radio','el-divider'] } })
    expect(w.find('.session-flow').exists()).toBe(true)
    expect(w.findAll('.stage-card').length).toBe(4)
    expect(w.find('.progress-rail').exists()).toBe(true)
  })

  it('默认 activeStage=goal 时 StageGoal 可见且标记 active', () => {
    const w = mount(LearningSession, { global: { plugins: [createPinia()], stubs: ['el-button','el-form','el-form-item','el-input','el-select','el-option','el-tag','el-descriptions','el-descriptions-item','el-card','el-radio-group','el-radio','el-divider'] } })
    expect(w.find('.stage-goal.active').exists()).toBe(true)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- learning-session.test.js`
Expected: FAIL — `Cannot find module '@/views/LearningSession.vue'`

- [ ] **Step 3: Create LearningSession.vue**

Create `frontend/src/views/LearningSession.vue`:

```vue
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
      <div class="session-flow">
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
import { watch, nextTick, ref, onMounted } from 'vue'
import { useAssessmentStore } from '@/stores/assessment'
import { useSessionStore } from '@/stores/session'
import StageGoal from '@/components/session/StageGoal.vue'
import StageQuiz from '@/components/session/StageQuiz.vue'
import StageAgent from '@/components/session/StageAgent.vue'
import StageGraph from '@/components/session/StageGraph.vue'
import SplitPane from '@/components/session/SplitPane.vue'

const store = useAssessmentStore()
const session = useSessionStore()

const STAGES = [
  { key: 'goal' }, { key: 'quiz' }, { key: 'agent' }, { key: 'graph' },
]

const ORDER = ['goal', 'quiz', 'agent', 'graph']

function stageClass(key) {
  const cur = session.activeStage
  const curIdx = ORDER.indexOf(cur)
  const idx = ORDER.indexOf(key)
  return {
    'is-done': idx < curIdx,
    'is-active': idx === curIdx,
    'is-pending': idx > curIdx,
  }
}

function railClass(key) {
  const cur = session.activeStage
  const curIdx = ORDER.indexOf(cur)
  const idx = ORDER.indexOf(key)
  if (idx < curIdx) return 'done'
  if (idx === curIdx) return 'active'
  return 'pending'
}

// 自动滚动到当前阶段卡
const flowRef = ref(null)
watch(() => session.activeStage, async () => {
  await nextTick()
  const el = flowRef.value?.querySelector('.is-active')
  el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
})
onMounted(() => { flowRef.value = document.querySelector('.session-flow') })
</script>

<style scoped>
.learning-session { padding: 0; height: 100%; display: flex; flex-direction: column; }
.session-layout { flex: 1; display: flex; min-height: 0; overflow: hidden; }
.session-flow { flex: 1; min-width: 0; overflow-y: auto; padding: 0 20px 20px; display: flex; gap: 16px; }
.progress-rail { display: flex; flex-direction: column; align-items: center; padding-top: 20px; gap: 0; }
.progress-rail .rail-node { width: 12px; height: 12px; border-radius: 50%; border: 2px solid var(--km-border); background: var(--km-bg-layer-3); flex-shrink: 0; }
.progress-rail .rail-node + .rail-node { margin-top: 80px; }
.progress-rail .rail-node.done { background: var(--km-success); border-color: var(--km-success); }
.progress-rail .rail-node.active { background: var(--km-primary); border-color: var(--km-primary); box-shadow: 0 0 0 4px rgba(108,124,224,0.2); animation: rail-pulse 2s ease-in-out infinite; }
.progress-rail .rail-node.pending { background: var(--km-bg-layer-3); border-color: var(--km-border); border-style: dashed; }
.stages { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 12px; padding-top: 12px; }

@keyframes rail-pulse { 0%, 100% { box-shadow: 0 0 0 4px rgba(108,124,224,0.2); } 50% { box-shadow: 0 0 0 8px rgba(108,124,224,0.08); } }
@media (prefers-reduced-motion: reduce) {
  .progress-rail .rail-node.active { animation: none; }
  .session-flow { scroll-behavior: auto; }
}
</style>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- learning-session.test.js`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/LearningSession.vue frontend/src/__tests__/learning-session.test.js
git commit -m "feat(session): LearningSession 主视图 + 进度连线 + 自动滚动"
```

---

## Task 8: 接线 sidebar + MainArea (替换 assessment, 移除 agents)

**Files:**
- Modify: `frontend/src/stores/sidebar.js`
- Modify: `frontend/src/ide/MainArea.vue`
- Modify: `frontend/src/__tests__/titlebar-menu.test.js`

- [ ] **Step 1: Update sidebar ACTIVITY_ITEMS**

In `frontend/src/stores/sidebar.js`, replace the ACTIVITY_ITEMS array:

```js
export const ACTIVITY_ITEMS = [
  { id: 'code', icon: 'Document', title: '代码' },
  { id: 'learning-session', icon: 'ChatDotRound', title: '学习会话' },
  { id: 'graph', icon: 'Share', title: '知识图谱' },
  { id: 'learning', icon: 'Reading', title: '学习资源' },
  { id: 'dashboard', icon: 'DataAnalysis', title: '数据看板' },
]
```

(移除原 `assessment` 和 `agents`, 新增 `learning-session`)

- [ ] **Step 2: Update MainArea to load LearningSession**

In `frontend/src/ide/MainArea.vue`, replace the import block and view-host content. Change imports:

```js
import LearningSession from '@/views/LearningSession.vue'
// 移除 Assessment 和 AgentView import
```

Replace the `<div v-if="sidebar.activeView !== 'code'" class="view-host">` block's inner content:

```vue
<div v-if="sidebar.activeView !== 'code'" class="view-host">
  <div class="view-card" :class="{ 'no-pad': sidebar.activeView === 'learning-session' }">
    <LearningSession v-if="sidebar.activeView === 'learning-session'" />
    <KnowledgeGraph v-else-if="sidebar.activeView === 'graph'" />
    <Learning v-else-if="sidebar.activeView === 'learning'" />
    <Dashboard v-else-if="sidebar.activeView === 'dashboard'" />
  </div>
</div>
```

Add style (learning-session 自带 padding, view-card 不要再套):

```css
.view-card.no-pad { padding: 16px 0 0 0; background: transparent; border: 0; box-shadow: none; }
```

- [ ] **Step 3: Update titlebar-menu test**

In `frontend/src/__tests__/titlebar-menu.test.js`, find the assertions that check for `答题测评` / `Agent 协同` / `知识图谱` / `学习资源` / `数据看板` in titlebar dropdowns and update. The test asserts titlebar does NOT duplicate learning view navigation — update the `not.toContain` list:

```js
expect(text).not.toContain('学习会话')
expect(text).not.toContain('知识图谱')
expect(text).not.toContain('学习资源')
expect(text).not.toContain('数据看板')
```

(Remove `答题测评` and `Agent 协同` lines, add `学习会话`.)

- [ ] **Step 4: Run affected tests**

Run: `cd frontend && npm test -- titlebar-menu.test.js`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/stores/sidebar.js frontend/src/ide/MainArea.vue frontend/src/__tests__/titlebar-menu.test.js
git commit -m "feat(session): 接线 sidebar + MainArea (替换 assessment, 移除 agents)"
```

---

## Task 9: chat buildSystemPrompt 注入学情画像 (双向联动)

**Files:**
- Modify: `frontend/src/stores/chat.js`

扩展 `_collectContext` 让学情画像 (profile + knowledgeGraph) 无论是否 tutorMode 都注入 context, buildSystemPrompt 在非 tutorMode 分支也带上画像块。

- [ ] **Step 1: Update _collectContext in chat.js**

In `frontend/src/stores/chat.js`, find `_collectContext` (around line 762). It already imports assessment store for tutorMode. Add profile/knowledgeGraph to ctx unconditionally:

```js
async function _collectContext() {
  const ws = useWorkspaceStore()
  const ctx = { tutorMode: tutorMode.value }
  try {
    const { useAssessmentStore } = await import('@/stores/assessment')
    const a = useAssessmentStore()
    ctx.profile = a.profile
    if (a.hasResults) ctx.knowledgeGraph = a.knowledgeGraph
  } catch { /* assessment store 未就绪, 忽略 */ }
  // ... 其余 (aiSettings / ws) 不变
```

- [ ] **Step 2: Update buildSystemPrompt non-tutorMode branch**

In `buildSystemPrompt` (around line 210), the non-tutorMode return adds `memoriesBlock + reasoningBlock + ctxBlock + toolBlock`. Insert a profileBlock before memoriesBlock (mirror the tutorMode branch's profile block, lines ~181-189):

```js
  let profileBlock = ''
  const p = context?.profile
  if (p && typeof p === 'object') {
    const lines = []
    if (p.theory_level != null) lines.push(`- 理论水平: ${p.theory_level}/5`)
    if (p.practice_level != null) lines.push(`- 实操水平: ${p.practice_level}/5`)
    const weak = Array.isArray(p.weak_topics) ? p.weak_topics : []
    if (weak.length) lines.push('- 薄弱知识点: ' + weak.slice(0, 5).map((t) => t.name || t.node_id || t).join('、'))
    const kg = context?.knowledgeGraph
    if (kg?.learning_path?.length) lines.push(`- 学习路径: ${kg.learning_path.length} 个节点, 预计 ${kg.estimated_total_hours?.toFixed?.(1) ?? '?'}h`)
    if (lines.length) profileBlock = '\n\n## 学习者学情画像 (可据此回答"为什么这样规划")\n' + lines.join('\n')
  }

  return {
    role: 'system',
    content: '...existing...' + profileBlock + memoriesBlock + reasoningBlock + ctxBlock + toolBlock,
  }
```

- [ ] **Step 3: Run chat tests**

Run: `cd frontend && npm test -- chat-chunks.test.js`
Expected: PASS (纯 helper 测不受影响)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/stores/chat.js
git commit -m "feat(chat): buildSystemPrompt 注入学情画像 (双向联动, 非仅 tutorMode)"
```

---

## Task 10: 删除旧视图 + 清理旧测试

**Files:**
- Delete: `frontend/src/views/Assessment.vue`
- Delete: `frontend/src/views/AgentView.vue`
- Delete: `frontend/src/__tests__/assessment-redesign.test.js`
- Delete: `frontend/src/__tests__/agent-view-redesign.test.js`

- [ ] **Step 1: Delete the 4 files**

```bash
git rm frontend/src/views/Assessment.vue
git rm frontend/src/views/AgentView.vue
git rm frontend/src/__tests__/assessment-redesign.test.js
git rm frontend/src/__tests__/agent-view-redesign.test.js
```

- [ ] **Step 2: Grep for any remaining imports of deleted views**

Run: `cd frontend && grep -rn "views/Assessment\|views/AgentView\|assessment-redesign\|agent-view-redesign" src/`
Expected: no output (or only the deleted test files which are already gone). If any file still imports them, update to use session components.

- [ ] **Step 3: Run full test suite**

Run: `cd frontend && npm test`
Expected: all pass (93 既有 - 4 删除的 assessment-redesign/agent-view-redesign cases + 新增 session-store 3 + learning-session 2 = 调整后全过)

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor(session): 删除 Assessment/AgentView 旧视图及测试 (逻辑已搬进 session 组件)"
```

---

## Task 11: 全量验证 + 构建

- [ ] **Step 1: Run full test suite**

Run: `cd frontend && npm test`
Expected: all pass

- [ ] **Step 2: Run build**

Run: `npm run build`
Expected: pass, no new warnings

- [ ] **Step 3: Manual e2e** (`env -u ELECTRON_RUN_AS_NODE npm run dev`)
  - 进 learning-session → 阶段①填目标 → 阶段②答题 → 阶段③协同实时日志 → 阶段④图谱摘要
  - 进度连线竖线随阶段变色, 当前节点脉动
  - 点图谱摘要"对照分屏查看" → 右侧分屏出图谱, G6 可交互, 列宽平滑展开
  - 关分屏 × → 列宽收回
  - 切左侧栏 graph → 图谱独立视图正常 (与分屏同组件, 状态保留)
  - 右侧 AI 助手问"为什么这样规划" → 基于注入画像回答
  - 已完成阶段卡可点击回看 (StageAgent 头部点击展开)
  - reduced-motion (系统设置) 下脉动停止, 过渡瞬切

- [ ] **Step 4: 同步文档 (CLAUDE.md 阶段9 + devlog) + commit**

Update `CLAUDE.md` with 阶段9 entry; create `docs/devlogs/B_前端/2026-06-22_学习会话三合一.md`. Commit.

```bash
git add CLAUDE.md docs/devlogs/B_前端/2026-06-22_学习会话三合一.md
git commit -m "docs: 同步阶段9 — 学习会话三合一 devlog + CLAUDE.md"
git push origin main
```

---

## Self-Review (已执行)

1. **Spec coverage**: 核心决策表 8 项 → Task 1(session store/activeStage 派生)、Task 2-5(4 阶段卡)、Task 6(分屏)、Task 7(主视图+进度连线)、Task 8(sidebar/MainArea)、Task 9(双向联动)、Task 10(删旧)。交互与动效章节 → 各 Stage 卡样式含 active 脉动/过渡, SplitPane grid 过渡, StageAgent expand transition, 进度连线 rail-pulse, 全部 reduced-motion 兜底。YAGNI 6 项均未实现。✓
2. **Placeholder scan**: 无 TBD/TODO, 每步含完整代码或确切命令。✓
3. **Type consistency**: `activeStage` 值 `goal/quiz/agent/graph` 在 session.js / 各 Stage 卡 `isActive` computed / LearningSession `STAGES`+`ORDER`+`stageClass`+`railClass` 一致。`splitView` 值 `graph/learning/dashboard` 在 session.js `SPLITTABLE` / SplitPane `labels` / StageGraph `splitGraph` 一致。store 方法 `setSplitView/closeSplit` 一致。✓

注: Task 9 的 buildSystemPrompt 改动用 `'...existing...'` 占位代表原 content 字符串 — 执行时需保留原中文 system prompt 文本不动, 只在末尾插入 profileBlock。Task 8 的 MainArea 改动需保留原 KnowledgeGraph/Learning/Dashboard import 与 code-layout v-show 块不动。
