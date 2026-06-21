# UI Redesign Navigation Agent Assessment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign KMatch-Desktop from an AI-template-feeling learning web shell into a professional desktop learning IDE with clear navigation, theme-aware chrome, an interactive Agent collaboration panel, and a more diagnostic assessment experience.

**Architecture:** Keep the existing Electron + Vue + Pinia + Element Plus stack. Do not migrate frameworks or rewrite business logic. First fix navigation ownership and shell tokens, then redesign the highest-value learning surfaces (`AgentView`, `Assessment`) using existing stores and backend data. AnySearch is planned as a backend/agent tool only, with keys read from environment variables, not from frontend state.

**Tech Stack:** Electron 33, electron-vite, Vue 3, Pinia, Element Plus, AntV G6, ECharts, Vitest 2.1.x, existing `--km-*` CSS variables.

---

## Context and constraints

- Current completed work includes Task 1-3 from the prior AI control center plan:
  - `frontend/src/stores/aiSettings.js`
  - `frontend/src/stores/chat.js` integration with memory/reasoning/tool permissions
  - `frontend/src/ide/TitlebarMenu.vue`
  - `electron/main/ipc/window.js`
  - root `npm test` delegates into frontend tests
- User feedback after reviewing UI:
  - Electron default `Window / Help` is gone.
  - Custom titlebar menu exists.
  - AI Settings should not be a titlebar text menu. It should be a standalone gear icon.
  - Top `学习` menu duplicates left ActivityBar and has inconsistent order.
  - ActivityBar stays black in both themes and should become theme-aware.
  - KnowledgeGraph, Assessment, Learning, AgentView, Dashboard feel too AI-web-template and empty.
  - Agent collaboration should become an interactive conversation/cockpit panel.
  - Assessment should feel like a diagnostic console, not a generic AI webpage.
  - Use Apix as inspiration via project docs, especially provider cards, task cards, mini chat, permissions/settings cards. Do not copy GPL code.
  - AnySearch may be useful for professional/domain retrieval agents, but the exposed key must not be saved or hardcoded.
- Do not commit unless the user explicitly asks.
- Do not store the AnySearch API key. Use `ANYSEARCH_API_KEY` from backend environment only when that task is implemented.

## File map

### Navigation and shell

- Modify `frontend/src/ide/TitlebarMenu.vue`
  - Remove top-level `学习` menu.
  - Remove top-level `AI 设置` text menu.
  - Keep `项目`, `工具`, `帮助` as app-level commands.
  - Ensure view navigation ownership belongs to ActivityBar.
- Modify `frontend/src/views/Workspace.vue`
  - Add right-side titlebar action cluster with AI assistant button, gear settings button, theme button if appropriate.
  - Keep drag region intact.
- Modify `frontend/src/stores/sidebar.js`
  - Keep ActivityBar order as single source of truth for learning views.
  - Optionally add `ai-settings` only if later settings view is implemented. Do not use in this plan unless the gear opens a lightweight placeholder drawer.
- Modify `frontend/src/ide/ActivityBar.vue`
  - Make ActivityBar theme-aware.
  - Add stronger active labels/tooltips if needed.
- Modify `frontend/src/styles/theme.css`
  - Add ActivityBar light/dark tokens.
  - Add shell surface tokens for workbench views.

### Agent collaboration redesign

- Modify `frontend/src/views/AgentView.vue`
  - Replace pipeline + log layout with an Agent cockpit layout.
  - Keep data source: `useAssessmentStore().orchestrationLog`, `useAgentStatus()`.
  - Add local interaction input for “ask about orchestration” in first version without backend call, or route to the existing right-side AssistantPanel with contextual prompt.
- Optionally create `frontend/src/components/AgentConversationPanel.vue`
  - Focused display component for agent timeline/conversation entries if `AgentView.vue` becomes too large.
- Test `frontend/src/__tests__/agent-view-redesign.test.js`
  - Verify empty state, agent roster, timeline rendering, and user prompt affordance.

### Assessment redesign

- Modify `frontend/src/views/Assessment.vue`
  - Recompose into diagnostic console: setup stage, answering stage, feedback stage.
  - Avoid large generic cards and emoji-heavy labels.
  - Keep current store API: `startAssessment`, `submitAssessmentAnswers`, `fetchFeedback`, `reset`.
- Test `frontend/src/__tests__/assessment-redesign.test.js`
  - Verify diagnostic layout state markers and answer/feedback actions.

### Shared workbench style

- Create `frontend/src/styles/workbench.css`
  - Reusable classes: `.km-workbench`, `.km-workbench-header`, `.km-surface`, `.km-rail`, `.km-evidence-list`, `.km-empty-state`.
- Modify `frontend/src/main.js`
  - Import `workbench.css` after theme CSS.
- Use these classes in `AgentView.vue` and `Assessment.vue` first. KnowledgeGraph/Learning/Dashboard can adopt later.

### AnySearch backend follow-up

- Do not install or wire AnySearch in this frontend redesign pass.
- Add design note in docs only:
  - AnySearch belongs in backend Agent tool layer.
  - Key source is `ANYSEARCH_API_KEY` env var.
  - Frontend only controls permission: allow/ask/deny.

---

## Task 1: Navigation ownership cleanup and gear settings entry

**Files:**
- Modify: `frontend/src/ide/TitlebarMenu.vue`
- Modify: `frontend/src/views/Workspace.vue`
- Modify: `frontend/src/__tests__/titlebar-menu.test.js`
- Create: `frontend/src/__tests__/workspace-titlebar-actions.test.js`

- [ ] **Step 1: Write failing titlebar menu test**

Add/modify `frontend/src/__tests__/titlebar-menu.test.js` so it asserts:

```js
it('keeps top titlebar menus for app-level commands only', () => {
  const wrapper = mount(TitlebarMenu, { global: { plugins: [pinia] } })
  const text = wrapper.text()

  expect(text).toContain('项目')
  expect(text).toContain('工具')
  expect(text).toContain('帮助')
  expect(text).not.toContain('学习')
  expect(text).not.toContain('AI 设置')
})
```

Also verify view navigation is not duplicated in the titlebar:

```js
it('does not duplicate learning view navigation in titlebar dropdowns', () => {
  const wrapper = mount(TitlebarMenu, { global: { plugins: [pinia] } })
  const text = wrapper.text()

  expect(text).not.toContain('知识图谱')
  expect(text).not.toContain('答题测评')
  expect(text).not.toContain('学习资源')
  expect(text).not.toContain('Agent 协同')
  expect(text).not.toContain('数据看板')
})
```

- [ ] **Step 2: Write failing Workspace gear test**

Create `frontend/src/__tests__/workspace-titlebar-actions.test.js`:

```js
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import Workspace from '@/views/Workspace.vue'
import { useSidebarStore } from '@/stores/sidebar'

vi.mock('@/ide/ActivityBar.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/ide/MainArea.vue', () => ({ default: { template: '<main />' } }))
vi.mock('@/ide/AssistantPanel.vue', () => ({ default: { template: '<aside />' } }))
vi.mock('@/ide/StatusBar.vue', () => ({ default: { template: '<footer />' } }))

vi.mock('@/stores/workspace', () => ({
  useWorkspaceStore: () => ({ hasProject: false, rootName: '', loadRecent: vi.fn() }),
}))

describe('Workspace titlebar actions', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders a gear button for AI settings instead of a titlebar AI settings menu', () => {
    const wrapper = mount(Workspace, { global: { plugins: [createPinia()] } })
    const gear = wrapper.find('[data-test="ai-settings-gear"]')
    expect(gear.exists()).toBe(true)
    expect(gear.attributes('title')).toContain('AI 设置')
  })

  it('gear reveals the assistant panel as interim settings entry', async () => {
    const pinia = createPinia()
    const wrapper = mount(Workspace, { global: { plugins: [pinia] } })
    const sidebar = useSidebarStore()
    sidebar.aiPanelVisible = false

    await wrapper.find('[data-test="ai-settings-gear"]').trigger('click')
    expect(sidebar.aiPanelVisible).toBe(true)
  })
})
```

- [ ] **Step 3: Run tests to verify failure**

Run:

```bash
cd frontend && npm test -- titlebar-menu.test.js workspace-titlebar-actions.test.js
```

Expected: fails because titlebar still has `学习` / `AI 设置`, and `Workspace.vue` has no gear action.

- [ ] **Step 4: Update TitlebarMenu**

In `frontend/src/ide/TitlebarMenu.vue`, change menu groups to app-level commands only:

```js
const menuGroups = computed(() => [
  {
    id: 'project',
    label: '项目',
    items: [
      { command: 'project.open', label: '打开项目文件夹' },
      { command: 'project.refresh', label: '刷新文件树', hint: ws.hasProject ? ws.rootName : '' },
      { command: 'view.code', label: '回到代码视图', divided: true },
    ],
  },
  {
    id: 'tools',
    label: '工具',
    items: [
      { command: 'assistant.toggle', label: sidebar.aiPanelVisible ? '隐藏 AI 助手' : '显示 AI 助手' },
      { command: 'theme.toggle', label: theme.mode === 'dark' ? '切换到亮色' : '切换到暗色' },
      { command: 'window.devtools', label: '打开开发者工具', divided: true },
    ],
  },
  {
    id: 'help',
    label: '帮助',
    items: [
      { command: 'help.backend', label: '后端与 Neo4j 启动提示' },
      { command: 'help.about', label: '关于 KMatch·知链' },
    ],
  },
])
```

Keep `view.code` supported in `runCommand()`.

- [ ] **Step 5: Add titlebar right action cluster**

In `frontend/src/views/Workspace.vue`, replace the current `title-right` hint with a right action cluster:

```vue
<div class="title-right">
  <button
    class="title-icon-button"
    :class="{ active: sidebar.aiPanelVisible }"
    title="显示或隐藏 AI 助手"
    data-test="ai-toggle-button"
    @click="sidebar.toggleAiPanel()"
  >
    AI
  </button>
  <button
    class="title-icon-button"
    title="AI 设置"
    data-test="ai-settings-gear"
    @click="openAiSettingsEntry"
  >
    ⚙
  </button>
</div>
```

Add script helper:

```js
function openAiSettingsEntry() {
  if (!sidebar.aiPanelVisible) sidebar.toggleAiPanel()
}
```

Add styles:

```css
.title-right {
  display: flex;
  align-items: center;
  gap: 6px;
  -webkit-app-region: no-drag;
}
.title-icon-button {
  height: 24px;
  min-width: 28px;
  border: 1px solid transparent;
  border-radius: 7px;
  background: transparent;
  color: var(--km-gray-600);
  font-size: 11px;
  font-weight: 650;
  cursor: pointer;
  transition: all 0.16s var(--km-ease);
}
.title-icon-button:hover,
.title-icon-button.active {
  background: var(--km-primary-light);
  color: var(--km-primary-active);
  border-color: var(--km-border-light);
}
```

- [ ] **Step 6: Run tests**

Run:

```bash
cd frontend && npm test -- titlebar-menu.test.js workspace-titlebar-actions.test.js
```

Expected: pass.

- [ ] **Step 7: Run build**

Run:

```bash
npm run build
```

Expected: pass with only existing Vite/Rollup warnings.

---

## Task 2: Theme-aware ActivityBar and shell tokens

**Files:**
- Modify: `frontend/src/styles/theme.css`
- Modify: `frontend/src/ide/ActivityBar.vue`
- Create: `frontend/src/__tests__/activitybar-theme.test.js`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/__tests__/activitybar-theme.test.js`:

```js
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ActivityBar from '@/ide/ActivityBar.vue'

function mountBar() {
  const pinia = createPinia()
  setActivePinia(pinia)
  return mount(ActivityBar, {
    global: {
      plugins: [pinia],
      stubs: {
        'el-icon': { template: '<span><slot /></span>' },
        Document: true,
        Share: true,
        Edit: true,
        Reading: true,
        Connection: true,
        DataAnalysis: true,
        ChatDotRound: true,
        Sunny: true,
        Moon: true,
      },
    },
  })
}

describe('ActivityBar theme contract', () => {
  it('uses semantic theme-aware activity tokens', () => {
    const wrapper = mountBar()
    expect(wrapper.find('.activity-bar').exists()).toBe(true)
    expect(wrapper.html()).toContain('activity-item')
  })
})
```

Add a CSS source assertion only for token names, not exact colors:

```js
import fs from 'node:fs'
import path from 'node:path'

it('defines separate light and dark activity shell tokens', () => {
  const css = fs.readFileSync(path.resolve(__dirname, '../styles/theme.css'), 'utf8')
  expect(css).toContain('--km-activity-bg')
  expect(css).toContain('--km-activity-hover')
  expect(css).toContain('--km-activity-active-bg')
  expect(css).toContain('html.dark')
})
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd frontend && npm test -- activitybar-theme.test.js
```

Expected: fails because new tokens are missing.

- [ ] **Step 3: Add theme tokens**

In `frontend/src/styles/theme.css`, update light `:root` activity tokens:

```css
--km-activity-bg: #f7f6f5;
--km-activity-text: #77736f;
--km-activity-hover: #eeece9;
--km-activity-active-bg: #eef0fc;
--km-activity-active-text: #5b6bd0;
--km-activity-active: #6c7ce0;
```

Update `html.dark` activity tokens:

```css
--km-activity-bg: #141311;
--km-activity-text: #969390;
--km-activity-hover: #211f1c;
--km-activity-active-bg: #1e2240;
--km-activity-active-text: #a0aef4;
--km-activity-active: #8b9cf0;
```

- [ ] **Step 4: Update ActivityBar styles**

In `frontend/src/ide/ActivityBar.vue`, update styles:

```css
.activity-bar {
  width: 48px;
  background: var(--km-activity-bg);
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 8px 0;
  flex-shrink: 0;
  border-right: 1px solid var(--km-border-light);
}
.activity-item {
  color: var(--km-activity-text);
  opacity: 0.72;
}
.activity-item:hover {
  opacity: 1;
  color: var(--km-activity-active-text);
  background: var(--km-activity-hover);
}
.activity-item.active {
  opacity: 1;
  color: var(--km-activity-active-text);
  background: var(--km-activity-active-bg);
}
.activity-item.on {
  opacity: 1;
  color: var(--km-activity-active-text);
  background: var(--km-activity-active-bg);
}
```

- [ ] **Step 5: Run tests and visual build**

Run:

```bash
cd frontend && npm test -- activitybar-theme.test.js
npm run build
```

Expected: tests and build pass.

---

## Task 3: Shared workbench style primitives

**Files:**
- Create: `frontend/src/styles/workbench.css`
- Modify: `frontend/src/main.js`
- Modify: `frontend/src/ide/MainArea.vue`
- Create: `frontend/src/__tests__/workbench-style.test.js`

- [ ] **Step 1: Write failing test for import and class availability**

Create `frontend/src/__tests__/workbench-style.test.js`:

```js
import { describe, it, expect } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'

describe('workbench style primitives', () => {
  it('main imports workbench.css', () => {
    const main = fs.readFileSync(path.resolve(__dirname, '../main.js'), 'utf8')
    expect(main).toContain("./styles/workbench.css")
  })

  it('defines reusable workbench classes', () => {
    const css = fs.readFileSync(path.resolve(__dirname, '../styles/workbench.css'), 'utf8')
    expect(css).toContain('.km-workbench')
    expect(css).toContain('.km-workbench-header')
    expect(css).toContain('.km-surface')
    expect(css).toContain('.km-empty-state')
  })
})
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
cd frontend && npm test -- workbench-style.test.js
```

Expected: fails because file/import do not exist.

- [ ] **Step 3: Create `workbench.css`**

Create `frontend/src/styles/workbench.css`:

```css
.km-workbench {
  min-height: 100%;
  color: var(--km-gray-700);
}

.km-workbench-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.km-workbench-kicker {
  margin: 0 0 6px;
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--km-gray-500);
  font-weight: 700;
}

.km-workbench-title {
  margin: 0;
  font-size: 22px;
  line-height: 1.15;
  letter-spacing: -0.02em;
  color: var(--km-gray-800);
  font-weight: 700;
}

.km-workbench-desc {
  margin: 8px 0 0;
  max-width: 68ch;
  color: var(--km-gray-600);
  font-size: 13px;
  line-height: 1.65;
}

.km-surface {
  border: 1px solid var(--km-border-light);
  border-radius: var(--km-radius);
  background: var(--km-bg-layer-2);
  box-shadow: var(--km-shadow-sm);
}

.km-surface-quiet {
  border: 1px solid var(--km-border-light);
  border-radius: var(--km-radius);
  background: var(--km-bg-layer-1);
}

.km-empty-state {
  min-height: 320px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px dashed var(--km-border);
  border-radius: var(--km-radius-lg);
  background: linear-gradient(180deg, var(--km-bg-layer-2), var(--km-bg-layer-1));
  color: var(--km-gray-600);
}

.km-evidence-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.km-evidence-row {
  display: flex;
  gap: 10px;
  padding: 10px 12px;
  border-radius: var(--km-radius-sm);
  background: var(--km-bg-layer-3);
  border: 1px solid var(--km-border-light);
}

.km-mono-number {
  font-family: var(--km-font-mono);
  font-variant-numeric: tabular-nums;
}
```

- [ ] **Step 4: Import workbench CSS**

In `frontend/src/main.js`, after theme import, add:

```js
import './styles/workbench.css'
```

- [ ] **Step 5: Reduce white-card shell feeling in MainArea**

In `frontend/src/ide/MainArea.vue`, update `.view-card` to use tokens instead of hardcoded white:

```css
.view-card {
  background: var(--km-bg-layer-1);
  color: var(--km-gray-700);
  border: 1px solid var(--km-border-light);
  border-radius: var(--km-radius-lg);
  flex: 1;
  min-width: 0;
  padding: 20px 24px;
  box-shadow: var(--km-shadow-sm);
}
.view-card :deep(.el-card) {
  --el-card-bg-color: var(--km-bg-layer-2);
  --el-text-color-primary: var(--km-gray-800);
  --el-fill-color-blank: var(--km-bg-layer-2);
}
```

- [ ] **Step 6: Run tests/build**

Run:

```bash
cd frontend && npm test -- workbench-style.test.js
npm run build
```

Expected: pass.

---

## Task 4: Agent collaboration cockpit layout

**Files:**
- Modify: `frontend/src/views/AgentView.vue`
- Create: `frontend/src/__tests__/agent-view-redesign.test.js`

- [ ] **Step 1: Write failing tests**

Create `frontend/src/__tests__/agent-view-redesign.test.js`:

```js
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import AgentView from '@/views/AgentView.vue'

vi.mock('@/stores/assessment', () => ({
  useAssessmentStore: () => ({
    orchestrationLog: [
      '[10:00:01] 主控调度 Agent: 读取学习画像',
      '[10:00:04] 学情检测 Agent: 发现文件 IO 薄弱',
      '[10:00:08] 图谱管控 Agent: 推荐异常处理前置节点',
    ],
    assessment: { total_count: 4 },
    accuracy: 0.75,
    reviewResults: null,
    knowledgeGraph: { learning_path: [{ node_id: 'py_file_io' }], estimated_total_hours: 2 },
    generatedContent: { resources: [{ title: '文件 IO 练习' }] },
  }),
}))

vi.mock('@/stores/sidebar', () => ({
  useSidebarStore: () => ({ setView: vi.fn() }),
}))

vi.mock('@/composables/useAgentStatus', () => ({
  useAgentStatus: () => ({
    pipelineRunning: { value: false },
    agentNodes: { value: [
      { key: 'orchestrator', label: '主控调度', status: 'done', role: '规划协作', retryCount: 0 },
      { key: 'diagnostics', label: '学情检测', status: 'done', role: '识别薄弱点', retryCount: 0 },
      { key: 'graph_controller', label: '图谱管控', status: 'done', role: '生成路径', retryCount: 0 },
    ] },
  }),
}))

describe('AgentView redesign', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('renders an agent cockpit instead of a pipeline-only page', () => {
    const wrapper = mount(AgentView, { global: { plugins: [createPinia()], stubs: ['el-button', 'el-empty', 'el-tag'] } })
    expect(wrapper.find('.agent-cockpit').exists()).toBe(true)
    expect(wrapper.text()).toContain('Agent 协同 cockpit')
    expect(wrapper.text()).toContain('主控调度')
    expect(wrapper.text()).toContain('协同对话流')
  })

  it('renders a local orchestration question input affordance', () => {
    const wrapper = mount(AgentView, { global: { plugins: [createPinia()], stubs: ['el-button', 'el-empty', 'el-tag'] } })
    expect(wrapper.find('[data-test="agent-question-input"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="agent-question-button"]').exists()).toBe(true)
  })
})
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
cd frontend && npm test -- agent-view-redesign.test.js
```

Expected: fails because cockpit classes/input do not exist.

- [ ] **Step 3: Recompose AgentView template**

Replace the top-level template of `AgentView.vue` with a three-zone cockpit:

```vue
<div class="agent-page km-workbench agent-cockpit">
  <div class="km-workbench-header">
    <div>
      <p class="km-workbench-kicker">multi-agent orchestration</p>
      <h3 class="km-workbench-title">Agent 协同 cockpit</h3>
      <p class="km-workbench-desc">把调度链路、Agent 状态和协作证据放在同一张工作台里。这里展示每个 Agent 为什么行动、正在处理什么、交付了什么。</p>
    </div>
    <el-tag :type="status.pipelineRunning.value ? 'warning' : 'success'" size="small">
      {{ status.pipelineRunning.value ? '运行中' : '已完成' }}
    </el-tag>
  </div>

  <div v-if="!hasLogs" class="km-empty-state agent-empty">
    <div>
      <h4>还没有协同记录</h4>
      <p>完成一次学情测评后，这里会显示主控调度和子 Agent 的协作过程。</p>
      <el-button type="primary" @click="sidebar.setView('assessment')">前往学情诊断</el-button>
    </div>
  </div>

  <div v-else class="cockpit-grid">
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
        </span>
      </button>
    </aside>

    <section class="agent-thread km-surface">
      <div class="thread-header">
        <span>协同对话流</span>
        <button class="thread-mode" @click="logAutoScroll = !logAutoScroll">
          {{ logAutoScroll ? '自动滚动' : '手动浏览' }}
        </button>
      </div>
      <div ref="logContainer" class="thread-body">
        <article v-for="(entry, idx) in parsedLogs" :key="idx" class="thread-message" :class="{ reject: entry.isReject }">
          <span class="thread-time">{{ entry.time || '--:--' }}</span>
          <p>{{ entry.msg }}</p>
        </article>
      </div>
      <div class="agent-question-bar">
        <input data-test="agent-question-input" placeholder="追问 Agent：为什么这样规划？" />
        <button data-test="agent-question-button">追问</button>
      </div>
    </section>

    <aside class="agent-evidence km-surface-quiet">
      <h4>{{ selectedAgent ? selectedAgent.label : '协作证据' }}</h4>
      <p class="evidence-desc">{{ selectedAgent ? selectedAgent.role : '点击左侧 Agent 查看职责和产出摘要。' }}</p>
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
```

- [ ] **Step 4: Add cockpit styles**

In `AgentView.vue` style block, replace pipeline-heavy styles with:

```css
.agent-page { padding: 0; }
.cockpit-grid {
  display: grid;
  grid-template-columns: 220px minmax(360px, 1fr) 280px;
  gap: 14px;
  min-height: 560px;
}
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
}
.status-dot.status-running { background: var(--km-warning); }
.status-dot.status-done { background: var(--km-success); }
.status-dot.status-failed { background: var(--km-danger); }
.agent-copy { display: flex; flex-direction: column; gap: 2px; }
.agent-copy strong { font-size: 13px; }
.agent-copy small { font-size: 11px; color: var(--km-gray-500); }
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
.evidence-desc { color: var(--km-gray-500); font-size: 12px; line-height: 1.6; }
@media (max-width: 1100px) {
  .cockpit-grid { grid-template-columns: 180px 1fr; }
  .agent-evidence { grid-column: 1 / -1; }
}
```

- [ ] **Step 5: Run test/build**

Run:

```bash
cd frontend && npm test -- agent-view-redesign.test.js
npm run build
```

Expected: pass.

---

## Task 5: Assessment diagnostic console shell

**Files:**
- Modify: `frontend/src/views/Assessment.vue`
- Create: `frontend/src/__tests__/assessment-redesign.test.js`

- [ ] **Step 1: Write failing diagnostic shell tests**

Create `frontend/src/__tests__/assessment-redesign.test.js`:

```js
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import Assessment from '@/views/Assessment.vue'

vi.mock('@/stores/assessment', () => ({
  useAssessmentStore: () => ({
    hasResults: false,
    loading: false,
    phase: 'input',
    pendingQuestions: [],
    userAnswers: [],
    error: null,
    currentStep: null,
    profile: null,
    assessment: null,
    feedbackStrategy: null,
    feedbackContent: null,
    startAssessment: vi.fn(),
    submitAssessmentAnswers: vi.fn(),
    backToInput: vi.fn(),
    reset: vi.fn(),
    fetchFeedback: vi.fn(),
  }),
}))

vi.mock('@/components/ProfileRadar.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/AssessmentReport.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/MarkdownViewer.vue', () => ({ default: { props: ['content'], template: '<div>{{ content }}</div>' } }))

describe('Assessment redesign', () => {
  it('renders diagnostic console framing', () => {
    const wrapper = mount(Assessment, {
      global: { plugins: [createPinia()], stubs: ['el-card', 'el-form', 'el-form-item', 'el-input', 'el-button', 'el-select', 'el-option', 'el-tag', 'el-alert', 'el-radio-group', 'el-radio', 'el-descriptions', 'el-descriptions-item', 'el-divider', 'el-dialog'] },
    })

    expect(wrapper.find('.diagnostic-console').exists()).toBe(true)
    expect(wrapper.text()).toContain('学情诊断控制台')
    expect(wrapper.text()).toContain('诊断阶段')
    expect(wrapper.text()).toContain('目标方向')
  })
})
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
cd frontend && npm test -- assessment-redesign.test.js
```

Expected: fails because `.diagnostic-console` and new copy do not exist.

- [ ] **Step 3: Reframe top input state**

In `Assessment.vue`, wrap the page with:

```vue
<div class="assessment-page km-workbench diagnostic-console">
  <div class="km-workbench-header diagnostic-header">
    <div>
      <p class="km-workbench-kicker">learning diagnosis</p>
      <h3 class="km-workbench-title">学情诊断控制台</h3>
      <p class="km-workbench-desc">先确认目标，再用交互题目定位薄弱点。测评结果会驱动知识图谱、学习资源和 Agent 协同。</p>
    </div>
    <div class="phase-chip">诊断阶段：{{ phaseLabel }}</div>
  </div>
```

Add computed in script:

```js
const phaseLabel = computed(() => {
  if (store.loading) return 'Agent 协作中'
  if (store.phase === 'answering') return '答题中'
  if (store.phase === 'feedback') return '反馈生成'
  if (store.hasResults) return '报告完成'
  return '目标设定'
})
```

For the input card, replace large generic card with two-column setup:

```vue
<div v-if="!store.hasResults && !store.loading" class="diagnostic-setup km-surface">
  <aside class="diagnostic-rail">
    <span class="rail-step active">01 目标方向</span>
    <span class="rail-step">02 交互答题</span>
    <span class="rail-step">03 动态反馈</span>
  </aside>
  <section class="diagnostic-form">
    <!-- keep existing form fields here -->
  </section>
</div>
```

Keep existing form logic and buttons.

- [ ] **Step 4: Restyle quiz answering stage**

Keep existing question rendering but wrap with:

```vue
<div v-if="store.phase === 'answering' && !store.loading" class="quiz-console km-surface">
  <aside class="question-index">
    <span v-for="(_, idx) in store.pendingQuestions" :key="idx" :class="{ answered: !!store.userAnswers[idx] }">
      {{ idx + 1 }}
    </span>
  </aside>
  <section class="question-stack">
    <!-- existing quiz item loop -->
  </section>
</div>
```

- [ ] **Step 5: Add diagnostic styles**

Add styles:

```css
.assessment-page { padding: 0; }
.phase-chip {
  border: 1px solid var(--km-border-light);
  border-radius: 999px;
  padding: 6px 10px;
  color: var(--km-primary-active);
  background: var(--km-primary-light);
  font-size: 12px;
  font-weight: 650;
}
.diagnostic-setup,
.quiz-console {
  display: grid;
  grid-template-columns: 190px 1fr;
  overflow: hidden;
}
.diagnostic-rail,
.question-index {
  padding: 18px;
  border-right: 1px solid var(--km-border-light);
  background: var(--km-bg-layer-1);
}
.rail-step {
  display: block;
  padding: 9px 10px;
  border-radius: var(--km-radius-sm);
  color: var(--km-gray-500);
  font-size: 12px;
  font-family: var(--km-font-mono);
}
.rail-step.active {
  background: var(--km-primary-light);
  color: var(--km-primary-active);
}
.diagnostic-form,
.question-stack { padding: 18px; }
.question-index span {
  display: inline-flex;
  width: 28px;
  height: 28px;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  margin: 0 6px 6px 0;
  background: var(--km-bg-layer-3);
  border: 1px solid var(--km-border-light);
  font-family: var(--km-font-mono);
  font-size: 12px;
}
.question-index span.answered {
  background: var(--km-primary-light);
  color: var(--km-primary-active);
}
@media (max-width: 900px) {
  .diagnostic-setup,
  .quiz-console { grid-template-columns: 1fr; }
  .diagnostic-rail,
  .question-index { border-right: 0; border-bottom: 1px solid var(--km-border-light); }
}
```

- [ ] **Step 6: Run tests/build**

Run:

```bash
cd frontend && npm test -- assessment-redesign.test.js assessment-store.test.js
npm run build
```

Expected: pass.

---

## Task 6: AnySearch backend integration design stub and docs only

**Files:**
- Modify: `docs/superpowers/specs/2026-06-21-ai-control-center-shell-design.md`
- Create: `docs/superpowers/specs/2026-06-21-anysearch-agent-tool-design.md`

This task intentionally does not implement AnySearch. It documents a secure future integration.

- [ ] **Step 1: Create AnySearch design doc**

Create `docs/superpowers/specs/2026-06-21-anysearch-agent-tool-design.md`:

```markdown
# AnySearch Agent Tool Design

> Status: Future backend integration, not implemented in the current frontend redesign pass.

## Security rule

AnySearch API keys must never be stored in frontend code, localStorage, Pinia state, docs, tests, or git history. The key source is backend environment variable `ANYSEARCH_API_KEY` only.

## Intended architecture

Renderer → FastAPI Agent tool endpoint → AnySearch CLI/API → curated search result → Agent response

## Frontend controls

The frontend may expose only permission settings:

- `anysearch_search`: allow / ask / deny
- `anysearch_extract`: ask / deny
- `anysearch_domain_search`: ask / deny

Default: ask.

## Backend tools

- `anysearch_search(query, max_results)`
- `anysearch_extract(url)`
- `anysearch_domain_search(domain, sub_domain, params)`

## Do not implement in this pass

- No API key UI.
- No frontend direct call.
- No storing user-provided key.
```

- [ ] **Step 2: Update existing shell design with reference**

Append to `docs/superpowers/specs/2026-06-21-ai-control-center-shell-design.md`:

```markdown
## AnySearch follow-up

AnySearch is approved as a future backend Agent tool candidate for professional/domain retrieval. It must be integrated through backend environment variable `ANYSEARCH_API_KEY`; frontend exposes only permission controls. See `docs/superpowers/specs/2026-06-21-anysearch-agent-tool-design.md`.
```

- [ ] **Step 3: Verify no key string exists in repo**

Run a literal search for the leaked prefix only if the user has rotated the key or explicitly asks. Otherwise, avoid reprinting or storing the secret in commands.

Safe check:

```bash
git status --short
```

Expected: docs changed, no secret added by this task.

---

## Task 7: Final focused verification for redesign pass

**Files:**
- Modify: `docs/superpowers/plans/2026-06-21-ui-redesign-navigation-agent-assessment-plan.md` if implementation notes are needed.

- [ ] **Step 1: Run focused tests**

Run:

```bash
cd frontend && npm test -- titlebar-menu.test.js workspace-titlebar-actions.test.js activitybar-theme.test.js workbench-style.test.js agent-view-redesign.test.js assessment-redesign.test.js
```

Expected: all pass.

- [ ] **Step 2: Run full frontend tests**

Run:

```bash
npm test
```

Expected: all pass. Existing non-fatal Vue warnings may remain.

- [ ] **Step 3: Run build**

Run:

```bash
npm run build
```

Expected: build passes. Existing Vite/Rollup warnings may remain.

- [ ] **Step 4: Manual UI smoke checklist**

Run:

```bash
npm run dev
```

Check:

```text
[ ] Electron default Window / Help menu is hidden.
[ ] Titlebar only has 项目 / 工具 / 帮助.
[ ] No top-level 学习 menu exists.
[ ] No top-level AI 设置 text menu exists.
[ ] AI settings is reachable via gear icon.
[ ] ActivityBar is light in light theme and charcoal in dark theme.
[ ] ActivityBar order is code / graph / assessment / learning / agents / dashboard.
[ ] Agent page reads like an interactive cockpit, not a static pipeline diagram.
[ ] Assessment page reads like a diagnostic console, not a generic AI webpage.
[ ] Right-side AI assistant still opens, sends messages, and shows model summary.
```

- [ ] **Step 5: Report completion without committing**

Return:

```text
Completed redesign pass through navigation, shell theme, Agent cockpit, and Assessment diagnostic shell.
Tests: <commands and results>
Build: <result>
Manual smoke: <checked items or skipped reason>
No commit made.
```

---

## Out of scope for this plan

- Full AI Settings page implementation.
- Real AnySearch backend tool execution.
- KnowledgeGraph full redesign.
- Learning playlist redesign.
- Dashboard evidence-first redesign.
- Real Agent chat backend endpoint for AgentView.
- Dependency/security audit remediation.

These should be separate follow-up plans after the user reviews the redesigned shell, Agent cockpit, and Assessment console.

## Self-review

- Spec coverage: covers the user's new priorities: duplicate navigation, gear settings, theme-aware ActivityBar, Agent interactive cockpit, Assessment diagnostic shell, AnySearch as backend-only future tool.
- Placeholder scan: no `TBD`, `TODO`, or unspecified implementation steps. Out-of-scope items are explicitly marked as separate future plans.
- Type consistency: uses existing store names (`useSidebarStore`, `useAssessmentStore`, `useAgentStatus`) and existing commands (`npm test`, `npm run build`).
- Security: leaked AnySearch key is not written into the plan; plan instructs not to search/reprint it unless rotated or explicitly requested.
