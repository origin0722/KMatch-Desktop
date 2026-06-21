# AI 控制中心外壳升级 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a polished KMatch custom titlebar menu and an AI Settings control center that manages model connection, proxy preferences, tool permissions, memory cards, and reasoning mode without breaking the existing chat flow.

**Architecture:** Keep the current Electron + Vue + Pinia architecture. Add focused UI/state modules (`TitlebarMenu.vue`, `AISettings.vue`, `aiSettings.js`) and wire them into existing shell components. Chat behavior reads AI settings through a narrow interface so permission, memory, and reasoning changes are centralized instead of making `chat.js` own every setting.

**Tech Stack:** Electron 33, electron-vite, Vue 3 Composition API, Pinia, Element Plus, Vitest, localStorage persistence.

---

## File Structure

### Files to create

- `frontend/src/stores/aiSettings.js` — Central AI settings store: proxy config, tool permissions, memory cards, reasoning mode, model capability helpers, localStorage persistence.
- `frontend/src/ide/TitlebarMenu.vue` — Custom KMatch titlebar menu used by `Workspace.vue`; routes commands to existing stores and opens AI Settings.
- `frontend/src/views/AISettings.vue` — Main settings view with cards for model connection, proxy, tool permissions, memory cards, and reasoning mode.
- `frontend/src/__tests__/ai-settings-store.test.js` — Unit tests for defaults, persistence, memory cards, tool permission checks, reasoning helpers.
- `frontend/src/__tests__/chat-ai-settings.test.js` — Unit tests for chat prompt/tool behavior influenced by AI settings.

### Files to modify

- `electron/main/index.js` — Hide the default Electron application menu.
- `electron/preload/index.js` — Add a safe `window.api.window.openDevTools()` bridge for the custom menu.
- `electron/main/index.js` or a new main IPC module — Register the `window:openDevTools` IPC handler. Keep this minimal.
- `frontend/src/views/Workspace.vue` — Replace hardcoded title-left/title-center markup with `TitlebarMenu` while preserving drag regions and project display.
- `frontend/src/stores/sidebar.js` — Add `ai-settings` as a routable view and icon/title metadata.
- `frontend/src/ide/MainArea.vue` — Mount `AISettings` when active view is `ai-settings`.
- `frontend/src/ide/AssistantPanel.vue` — Replace inline API dialog with compact settings entry; add reasoning-mode button/summary next to tutor mode.
- `frontend/src/stores/chat.js` — Import AI settings, filter tool descriptions, enforce permissions before execution, inject enabled memory cards, and apply reasoning-mode prompt/model hints.
- `frontend/src/styles/theme.css` — Add a small number of titlebar/menu/settings tokens if existing `--km-*` tokens are insufficient.

### Validation commands

- Root tests: `npm test`
- Frontend tests: `cd frontend && npm test`
- Frontend build: `cd frontend && npm run build`
- Full Electron build smoke: `npm run build`
- Manual UI smoke after implementation: `npm run dev`

> Commit note: this plan includes commit checkpoints because the writing-plans skill expects them. In this repository, only commit when the user explicitly authorizes it. During execution, treat commit steps as “show git diff/status and ask before committing.”

---

## Task 1: AI settings store foundation

**Files:**
- Create: `frontend/src/stores/aiSettings.js`
- Create: `frontend/src/__tests__/ai-settings-store.test.js`

- [ ] **Step 1: Write failing tests for defaults and persistence**

Create `frontend/src/__tests__/ai-settings-store.test.js`:

```js
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAiSettingsStore } from '@/stores/aiSettings'

function resetStorage() {
  localStorage.clear()
}

describe('aiSettings store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    resetStorage()
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-06-21T08:00:00.000Z'))
  })

  it('loads safe defaults', () => {
    const settings = useAiSettingsStore()

    expect(settings.proxy.enabled).toBe(false)
    expect(settings.proxy.type).toBe('http')
    expect(settings.proxy.url).toBe('')
    expect(settings.proxy.scope).toBe('all')

    expect(settings.toolPermissions.read_file).toBe('allow')
    expect(settings.toolPermissions.list_directory).toBe('allow')
    expect(settings.toolPermissions.write_file).toBe('ask')
    expect(settings.toolPermissions.generate_project_graph).toBe('allow')
    expect(settings.toolPermissions.code_review).toBe('ask')
    expect(settings.toolPermissions.code_test).toBe('ask')

    expect(settings.reasoningMode).toBe('auto')
    expect(settings.enabledMemories).toEqual([])
  })

  it('persists proxy, permissions, and reasoning mode', () => {
    const settings = useAiSettingsStore()

    settings.setProxy({ enabled: true, type: 'socks', url: 'socks://127.0.0.1:7890', scope: 'currentProvider' })
    settings.setToolPermission('code_test', 'deny')
    settings.setReasoningMode('deep')

    setActivePinia(createPinia())
    const restored = useAiSettingsStore()

    expect(restored.proxy).toEqual({ enabled: true, type: 'socks', url: 'socks://127.0.0.1:7890', scope: 'currentProvider' })
    expect(restored.toolPermissions.code_test).toBe('deny')
    expect(restored.reasoningMode).toBe('deep')
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd frontend && npm test -- ai-settings-store.test.js
```

Expected: FAIL because `@/stores/aiSettings` does not exist.

- [ ] **Step 3: Implement the store**

Create `frontend/src/stores/aiSettings.js`:

```js
import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

const STORAGE_KEY = 'kmatch-ai-settings'

export const TOOL_PERMISSION = Object.freeze({
  ALLOW: 'allow',
  ASK: 'ask',
  DENY: 'deny',
})

export const REASONING_MODE = Object.freeze({
  AUTO: 'auto',
  FAST: 'fast',
  DEEP: 'deep',
})

const DEFAULT_PROXY = Object.freeze({
  enabled: false,
  type: 'http',
  url: '',
  scope: 'all',
})

const DEFAULT_TOOL_PERMISSIONS = Object.freeze({
  read_file: TOOL_PERMISSION.ALLOW,
  list_directory: TOOL_PERMISSION.ALLOW,
  write_file: TOOL_PERMISSION.ASK,
  generate_project_graph: TOOL_PERMISSION.ALLOW,
  code_review: TOOL_PERMISSION.ASK,
  code_test: TOOL_PERMISSION.ASK,
})

function safeJsonParse(raw) {
  if (!raw) return null
  try { return JSON.parse(raw) } catch { return null }
}

function loadState() {
  try { return safeJsonParse(localStorage.getItem(STORAGE_KEY)) || {} } catch { return {} }
}

function saveState(state) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)) } catch { /* noop */ }
}

function nowIso() {
  return new Date().toISOString()
}

function normalizeMemory(input) {
  const id = input.id || `mem_${Date.now()}_${Math.random().toString(16).slice(2)}`
  const createdAt = input.createdAt || nowIso()
  return {
    id,
    type: input.type || 'preference',
    title: (input.title || '').trim(),
    content: (input.content || '').trim(),
    source: input.source || 'manual',
    enabled: input.enabled !== false,
    createdAt,
    updatedAt: input.updatedAt || createdAt,
  }
}

export const useAiSettingsStore = defineStore('aiSettings', () => {
  const saved = loadState()

  const proxy = ref({ ...DEFAULT_PROXY, ...(saved.proxy || {}) })
  const toolPermissions = ref({ ...DEFAULT_TOOL_PERMISSIONS, ...(saved.toolPermissions || {}) })
  const memories = ref(Array.isArray(saved.memories) ? saved.memories.map(normalizeMemory) : [])
  const reasoningMode = ref(saved.reasoningMode || REASONING_MODE.AUTO)

  const enabledMemories = computed(() => memories.value.filter((m) => m.enabled && m.title && m.content))

  function persist() {
    saveState({
      proxy: proxy.value,
      toolPermissions: toolPermissions.value,
      memories: memories.value,
      reasoningMode: reasoningMode.value,
    })
  }

  function setProxy(next) {
    proxy.value = { ...proxy.value, ...(next || {}) }
    persist()
  }

  function setToolPermission(tool, mode) {
    if (!Object.prototype.hasOwnProperty.call(DEFAULT_TOOL_PERMISSIONS, tool)) return
    if (!Object.values(TOOL_PERMISSION).includes(mode)) return
    toolPermissions.value = { ...toolPermissions.value, [tool]: mode }
    persist()
  }

  function permissionFor(tool) {
    return toolPermissions.value[tool] || TOOL_PERMISSION.DENY
  }

  function isToolAllowed(tool) {
    return permissionFor(tool) !== TOOL_PERMISSION.DENY
  }

  function shouldAskForTool(tool) {
    return permissionFor(tool) === TOOL_PERMISSION.ASK
  }

  function setReasoningMode(mode) {
    reasoningMode.value = Object.values(REASONING_MODE).includes(mode) ? mode : REASONING_MODE.AUTO
    persist()
  }

  function modelReasoningSupport(provider, model) {
    const id = String(model || '').toLowerCase()
    if (provider === 'deepseek' && id === 'deepseek-reasoner') return 'native'
    if (id.includes('claude-opus-4') || id.includes('claude-fable-5') || id.includes('claude-mythos-5')) return 'native-when-supported-by-backend'
    if (!id) return 'unknown'
    return 'prompt-only'
  }

  function reasoningInstruction(provider, model) {
    const support = modelReasoningSupport(provider, model)
    if (reasoningMode.value === REASONING_MODE.FAST) {
      return '思考模式: 快速。请直接给出简洁实用的回答，不展开冗长推理。'
    }
    if (reasoningMode.value === REASONING_MODE.DEEP) {
      if (support === 'native') return '思考模式: 深度。当前模型支持 reasoning，请进行更充分的分析，并在最终回答中保持结论清晰。'
      return '思考模式: 深度。当前模型未确认支持原生 thinking 参数，请更仔细地分析问题，先内部推理，再给出简洁结论。'
    }
    return ''
  }

  function addMemory(input) {
    const memory = normalizeMemory(input || {})
    if (!memory.title || !memory.content) return null
    memories.value = [memory, ...memories.value]
    persist()
    return memory
  }

  function updateMemory(id, patch) {
    let updated = null
    memories.value = memories.value.map((m) => {
      if (m.id !== id) return m
      updated = normalizeMemory({ ...m, ...(patch || {}), id: m.id, createdAt: m.createdAt, updatedAt: nowIso() })
      return updated
    })
    persist()
    return updated
  }

  function removeMemory(id) {
    memories.value = memories.value.filter((m) => m.id !== id)
    persist()
  }

  function formatEnabledMemories(limit = 10, maxChars = 220) {
    const selected = enabledMemories.value.slice(0, limit)
    if (!selected.length) return ''
    const lines = selected.map((m) => {
      const content = m.content.length > maxChars ? `${m.content.slice(0, maxChars)}…` : m.content
      return `- [${m.type}] ${m.title}: ${content}`
    })
    return `\n\n## 用户记忆\n${lines.join('\n')}`
  }

  return {
    proxy,
    toolPermissions,
    memories,
    enabledMemories,
    reasoningMode,
    setProxy,
    setToolPermission,
    permissionFor,
    isToolAllowed,
    shouldAskForTool,
    setReasoningMode,
    modelReasoningSupport,
    reasoningInstruction,
    addMemory,
    updateMemory,
    removeMemory,
    formatEnabledMemories,
  }
})
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd frontend && npm test -- ai-settings-store.test.js
```

Expected: PASS.

- [ ] **Step 5: Add memory and helper tests**

Append to `frontend/src/__tests__/ai-settings-store.test.js` inside the `describe` block:

```js
  it('adds, updates, disables, and removes memory cards', () => {
    const settings = useAiSettingsStore()

    const created = settings.addMemory({
      type: 'preference',
      title: '回答风格',
      content: '用户喜欢中文解释，先讲思路再给代码。',
      source: 'manual',
    })

    expect(created.id).toMatch(/^mem_/)
    expect(settings.enabledMemories).toHaveLength(1)
    expect(settings.formatEnabledMemories()).toContain('回答风格')

    settings.updateMemory(created.id, { enabled: false })
    expect(settings.enabledMemories).toHaveLength(0)

    settings.removeMemory(created.id)
    expect(settings.memories).toHaveLength(0)
  })

  it('returns model reasoning support and instructions', () => {
    const settings = useAiSettingsStore()

    expect(settings.modelReasoningSupport('deepseek', 'deepseek-reasoner')).toBe('native')
    expect(settings.modelReasoningSupport('deepseek', 'deepseek-v4-pro')).toBe('prompt-only')
    expect(settings.modelReasoningSupport('custom', 'claude-opus-4-8')).toBe('native-when-supported-by-backend')

    settings.setReasoningMode('deep')
    expect(settings.reasoningInstruction('deepseek', 'deepseek-v4-pro')).toContain('当前模型未确认支持原生 thinking 参数')

    settings.setReasoningMode('fast')
    expect(settings.reasoningInstruction('deepseek', 'deepseek-reasoner')).toContain('思考模式: 快速')
  })
```

- [ ] **Step 6: Run full store test file**

Run:

```bash
cd frontend && npm test -- ai-settings-store.test.js
```

Expected: PASS.

- [ ] **Step 7: Checkpoint**

Run:

```bash
git status --short
```

Expected: new store and test files. Ask user before committing.

---

## Task 2: Wire AI settings into chat prompt and tool permissions

**Files:**
- Modify: `frontend/src/stores/chat.js`
- Create/modify: `frontend/src/__tests__/chat-ai-settings.test.js`

- [ ] **Step 1: Export pure helpers from `chat.js` for testing**

Modify `frontend/src/stores/chat.js` so `buildSystemPrompt`, `parseToolCalls`, and `stripToolCalls` are exported:

```js
export function buildSystemPrompt(context) {
  // keep existing body; later steps add memory/reasoning support
}

export function parseToolCalls(text) {
  // keep existing body
}

export function stripToolCalls(text) {
  // keep existing body
}
```

Expected: no behavior change.

- [ ] **Step 2: Write failing prompt tests**

Create `frontend/src/__tests__/chat-ai-settings.test.js`:

```js
import { describe, expect, it } from 'vitest'
import { buildSystemPrompt, parseToolCalls, stripToolCalls } from '@/stores/chat'

describe('chat AI settings integration helpers', () => {
  it('injects enabled memory and reasoning instruction into normal prompt', () => {
    const prompt = buildSystemPrompt({
      memoriesBlock: '\n\n## 用户记忆\n- [preference] 回答风格: 先讲思路再给代码',
      reasoningInstruction: '思考模式: 深度。请更仔细地分析问题。',
    })

    expect(prompt.content).toContain('## 用户记忆')
    expect(prompt.content).toContain('先讲思路再给代码')
    expect(prompt.content).toContain('思考模式: 深度')
  })

  it('filters denied tools from tool prompt text', () => {
    const prompt = buildSystemPrompt({
      allowedTools: ['read_file', 'write_file'],
    })

    expect(prompt.content).toContain('"read_file"')
    expect(prompt.content).toContain('"write_file"')
    expect(prompt.content).not.toContain('"code_test"')
    expect(prompt.content).not.toContain('"code_review"')
  })

  it('keeps tool parsing helpers stable', () => {
    const text = '请读取文件\n```tool_call\n{"tool":"read_file","path":"a.py"}\n```\n谢谢'
    expect(parseToolCalls(text)).toEqual([{ tool: 'read_file', path: 'a.py' }])
    expect(stripToolCalls(text)).toBe('请读取文件\n\n谢谢')
  })
})
```

- [ ] **Step 3: Run tests to verify failure**

Run:

```bash
cd frontend && npm test -- chat-ai-settings.test.js
```

Expected: FAIL because `memoriesBlock`, `reasoningInstruction`, and `allowedTools` are ignored.

- [ ] **Step 4: Refactor tool prompt construction in `chat.js`**

In `frontend/src/stores/chat.js`, add helper functions near `TOOLS`:

```js
function toolCallExample(tool) {
  const examples = {
    read_file: '{"tool": "read_file", "path": "相对路径"}',
    list_directory: '{"tool": "list_directory", "path": "相对路径(可选)"}',
    write_file: '{"tool": "write_file", "path": "相对路径", "content": "完整文件内容"}',
    generate_project_graph: '{"tool": "generate_project_graph", "path": "相对路径", "write_to_neo4j": false}',
    code_review: '{"tool": "code_review", "path": "相对路径", "target_direction": "开发目标方向"}',
    code_test: '{"tool": "code_test", "path": "相对路径", "target_direction": "开发目标方向", "mode": "generate"}',
  }
  return examples[tool]
}

function buildToolBlock(allowedTools) {
  const allow = new Set(allowedTools || TOOLS.map((t) => t.name))
  const examples = TOOLS
    .filter((t) => allow.has(t.name))
    .map((t) => `\`\`\`tool_call\n${toolCallExample(t.name)}\n\`\`\``)
    .join('\n')

  return `
## 可用工具
你可以通过以下格式调用工具来读写项目文件、委派后端多 Agent 能力:
${examples}
- read_file/list_directory 调用后返回结果, 你再继续回答。
- write_file 会触发用户审批门 (Python 文件先经 AST 安全预检), 用户可能批准或拒绝;
  批准后返回写入成功, 拒绝则返回"用户拒绝写入", 你应据此调整后续回答。
  write_file 的 content 必须是完整可用的文件内容, 不要写占位符。
- generate_project_graph: 解析 Python 代码生成项目代码图谱 (函数/类/方法/调用关系),
  返回实体清单与统计; 不依赖 Neo4j (离线可用)。审查/测试工作区文件前可先调它了解结构。
- code_review: 四维度代码审查 (逻辑/安全/规范/领域合规), 需 Neo4j+LLM 在线;
  target_direction 必填 (开发目标方向, 从用户上下文推断, 缺失时先问用户)。
- code_test: LLM 生成 pytest 用例并沙箱执行, 返回通过率/覆盖率/失败用例; 需 Neo4j+LLM 在线。
- 审查/测试/解析工作区文件时优先传 path (而非贴 code), 便于编辑器符号联动。
- 后端返回 503 时表示 Neo4j 图谱引擎未就绪, 你应转告用户启动 Neo4j。`
}
```

- [ ] **Step 5: Make `buildSystemPrompt` consume settings context**

Inside `buildSystemPrompt(context)`, replace the existing hardcoded `toolBlock` with:

```js
  const toolBlock = buildToolBlock(context?.allowedTools)
  const memoriesBlock = context?.memoriesBlock || ''
  const reasoningBlock = context?.reasoningInstruction
    ? `\n\n## 思考模式\n${context.reasoningInstruction}`
    : ''
```

Then append `memoriesBlock + reasoningBlock` before `ctxBlock + toolBlock` in both normal and tutor-mode prompt branches.

For the normal branch content, use:

```js
      '你是 KMatch IDE 的 AI 编程助手。你可以阅读项目文件、解释代码、提供改进建议、帮助调试。\n'
      + '回答用中文，代码块标注语言。保持回答简洁实用。\n'
      + '如果你需要查看某个文件来更好地回答问题，使用 tool_call 格式请求读取。'
      + memoriesBlock
      + reasoningBlock
      + ctxBlock
      + toolBlock,
```

For tutor mode, insert `memoriesBlock + reasoningBlock` after `profileBlock` and before `ctxBlock`.

- [ ] **Step 6: Run prompt tests**

Run:

```bash
cd frontend && npm test -- chat-ai-settings.test.js
```

Expected: PASS.

- [ ] **Step 7: Import `aiSettings` in chat store and collect context**

Modify `frontend/src/stores/chat.js` imports:

```js
import { useAiSettingsStore } from '@/stores/aiSettings'
```

In `_collectContext()`, after profile loading, add:

```js
    try {
      const aiSettings = useAiSettingsStore()
      ctx.allowedTools = TOOLS.map((t) => t.name).filter((name) => aiSettings.isToolAllowed(name))
      ctx.memoriesBlock = aiSettings.formatEnabledMemories()
      ctx.reasoningInstruction = aiSettings.reasoningInstruction(provider.value, model.value)
    } catch { /* aiSettings store 未就绪, 忽略 */ }
```

- [ ] **Step 8: Enforce denied tools before execution**

At the start of `_executeTool(call)` inside `try`, add:

```js
      const aiSettings = useAiSettingsStore()
      if (!aiSettings.isToolAllowed(call.tool)) {
        return { error: `工具 ${call.tool} 已在 AI 设置中禁用` }
      }
```

This prevents prompt-injected or stale tool calls from bypassing the UI.

- [ ] **Step 9: Preserve write_file approval behavior**

Do not change the existing `write_file` approval path in this task. `ask` behavior for non-write tools will be handled in a later task after adding a generic permission card UI. Verify `write_file` still calls `_safetyCheck()` and `_requestApproval()`.

- [ ] **Step 10: Run related tests**

Run:

```bash
cd frontend && npm test -- ai-settings-store.test.js chat-ai-settings.test.js
```

Expected: PASS.

- [ ] **Step 11: Checkpoint**

Run:

```bash
git status --short
```

Expected: chat store and tests changed. Ask user before committing.

---

## Task 3: Custom titlebar menu and default Electron menu removal

**Files:**
- Create: `frontend/src/ide/TitlebarMenu.vue`
- Modify: `frontend/src/views/Workspace.vue`
- Modify: `electron/main/index.js`
- Modify: `electron/preload/index.js`

- [ ] **Step 1: Hide Electron default menu**

Modify `electron/main/index.js` import:

```js
import { app, BrowserWindow, Menu, ipcMain } from 'electron'
```

Inside `app.whenReady().then(async () => {` before `registerAllIpc()` add:

```js
  Menu.setApplicationMenu(null)
```

- [ ] **Step 2: Add safe devtools IPC**

Still in `electron/main/index.js`, add before `app.whenReady()`:

```js
function registerWindowIpc() {
  ipcMain.handle('window:openDevTools', (event) => {
    const win = BrowserWindow.fromWebContents(event.sender)
    if (!win) return false
    win.webContents.openDevTools({ mode: 'detach' })
    return true
  })
}
```

Then update `registerAllIpc()`:

```js
function registerAllIpc() {
  registerFsIpc()
  registerWorkspaceIpc()
  registerHttpProxyIpc()
  registerWindowIpc()
}
```

- [ ] **Step 3: Expose devtools bridge**

Modify `electron/preload/index.js` inside `contextBridge.exposeInMainWorld('api', { ... })` and add a `window` namespace after `http`:

```js
  window: {
    openDevTools: () => ipcRenderer.invoke('window:openDevTools'),
  },
```

Ensure the object commas remain valid.

- [ ] **Step 4: Create TitlebarMenu component**

Create `frontend/src/ide/TitlebarMenu.vue`:

```vue
<template>
  <div class="titlebar-menu">
    <div class="brand-block">
      <span class="brand-mark">知</span>
      <span class="brand-text">KMatch·知链</span>
    </div>

    <el-dropdown v-for="group in menuGroups" :key="group.id" trigger="click" @command="runCommand">
      <button class="menu-trigger">
        {{ group.label }}
        <span class="chevron">⌄</span>
      </button>
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item
            v-for="item in group.items"
            :key="item.command"
            :command="item.command"
            :divided="item.divided"
          >
            <span class="item-label">{{ item.label }}</span>
            <span v-if="item.hint" class="item-hint">{{ item.hint }}</span>
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useWorkspaceStore } from '@/stores/workspace'
import { useSidebarStore } from '@/stores/sidebar'
import { useThemeStore } from '@/stores/theme'

const ws = useWorkspaceStore()
const sidebar = useSidebarStore()
const theme = useThemeStore()

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
    id: 'learning',
    label: '学习',
    items: [
      { command: 'view.assessment', label: '答题测评' },
      { command: 'view.graph', label: '知识图谱' },
      { command: 'view.learning', label: '学习资源' },
      { command: 'view.agents', label: 'Agent 协同' },
      { command: 'view.dashboard', label: '数据看板' },
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
    id: 'ai',
    label: 'AI 设置',
    items: [
      { command: 'view.ai-settings', label: '打开 AI 控制中心' },
      { command: 'view.ai-settings.models', label: '模型与连接' },
      { command: 'view.ai-settings.permissions', label: '工具权限' },
      { command: 'view.ai-settings.memories', label: '记忆设置' },
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

async function runCommand(command) {
  if (command.startsWith('view.')) {
    const id = command.replace('view.', '').split('.')[0]
    sidebar.setView(id)
    return
  }
  if (command === 'project.open') {
    await ws.openProject()
    return
  }
  if (command === 'project.refresh') {
    if (!ws.hasProject) {
      ElMessage.info('请先打开项目文件夹')
      return
    }
    await ws.refreshTree()
    ElMessage.success('文件树已刷新')
    return
  }
  if (command === 'assistant.toggle') {
    sidebar.toggleAiPanel()
    return
  }
  if (command === 'theme.toggle') {
    theme.toggle()
    return
  }
  if (command === 'window.devtools') {
    await window.api?.window?.openDevTools?.()
    return
  }
  if (command === 'help.backend') {
    ElMessageBox.alert('后端需要 FastAPI sidecar 或本地 uvicorn；Neo4j 需通过 docker-compose 启动，默认密码 kmatch2026。', '后端与 Neo4j 启动提示')
    return
  }
  if (command === 'help.about') {
    ElMessageBox.alert('KMatch·知链：知识图谱驱动的多智能体协同个性化学习桌面 IDE。', '关于 KMatch·知链')
  }
}
</script>

<style scoped>
.titlebar-menu {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  -webkit-app-region: no-drag;
}
.brand-block {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-right: 8px;
}
.brand-mark {
  width: 22px;
  height: 22px;
  border-radius: 7px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--km-primary);
  color: var(--km-primary-text);
  font-size: 12px;
  font-weight: 700;
}
.brand-text {
  font-size: 13px;
  font-weight: 650;
  color: var(--km-gray-800);
  letter-spacing: 0.1px;
}
.menu-trigger {
  height: 26px;
  padding: 0 9px;
  border: none;
  border-radius: var(--km-radius-sm);
  background: transparent;
  color: var(--km-gray-600);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.18s var(--km-ease);
}
.menu-trigger:hover {
  background: var(--km-gray-200);
  color: var(--km-gray-800);
}
.chevron {
  margin-left: 3px;
  color: var(--km-gray-500);
}
.item-label {
  min-width: 96px;
}
.item-hint {
  margin-left: 16px;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--km-gray-500);
  font-size: 11px;
}
</style>
```

- [ ] **Step 5: Integrate TitlebarMenu into Workspace**

Modify `frontend/src/views/Workspace.vue` template titlebar section:

```vue
<div class="ide-titlebar">
  <div class="title-left">
    <TitlebarMenu />
  </div>
  <div class="title-center" v-if="ws.hasProject">
    <el-icon :size="13"><FolderOpened /></el-icon>
    <span>{{ ws.rootName }}</span>
  </div>
  <div class="title-right">
    <span class="title-hint">IDE · 二次开发 + 个性化学习</span>
  </div>
</div>
```

Add import:

```js
import TitlebarMenu from '@/ide/TitlebarMenu.vue'
```

Remove unused `.title-brand`, `.title-sep`, `.title-scene` styles if no longer referenced.

- [ ] **Step 6: Build to catch syntax errors**

Run:

```bash
cd frontend && npm run build
```

Expected: build succeeds.

- [ ] **Step 7: Root build to include Electron main/preload**

Run:

```bash
npm run build
```

Expected: electron-vite build succeeds.

- [ ] **Step 8: Manual smoke check**

Run:

```bash
npm run dev
```

Expected manual observations:

- Default `Window / Help` menu no longer appears.
- KMatch custom titlebar menu is visible.
- Blank titlebar area still drags the window.
- Menu clicks switch views and open AI settings after Task 4.
- DevTools command opens detached developer tools.

- [ ] **Step 9: Checkpoint**

Run:

```bash
git status --short
```

Ask user before committing.

---

## Task 4: Add AI Settings route/view shell

**Files:**
- Modify: `frontend/src/stores/sidebar.js`
- Modify: `frontend/src/ide/MainArea.vue`
- Create: `frontend/src/views/AISettings.vue`

- [ ] **Step 1: Add sidebar view entry**

Modify `frontend/src/stores/sidebar.js` and add AI settings after dashboard:

```js
  { id: 'ai-settings', icon: 'Setting', title: 'AI 设置' },
```

Full `ACTIVITY_ITEMS` becomes:

```js
export const ACTIVITY_ITEMS = [
  { id: 'code', icon: 'Document', title: '代码' },
  { id: 'graph', icon: 'Share', title: '知识图谱' },
  { id: 'assessment', icon: 'Edit', title: '答题测评' },
  { id: 'learning', icon: 'Reading', title: '学习资源' },
  { id: 'agents', icon: 'Connection', title: 'Agent 协同' },
  { id: 'dashboard', icon: 'DataAnalysis', title: '数据看板' },
  { id: 'ai-settings', icon: 'Setting', title: 'AI 设置' },
]
```

- [ ] **Step 2: Create AISettings view shell**

Create `frontend/src/views/AISettings.vue`:

```vue
<template>
  <div class="ai-settings-view">
    <header class="settings-hero">
      <div>
        <p class="eyebrow">AI Control Center</p>
        <h1>AI 设置</h1>
        <p class="summary">集中管理模型连接、网络代理、工具权限、记忆卡和思考模式。</p>
      </div>
      <el-tag type="info" effect="plain">本地配置</el-tag>
    </header>

    <section class="settings-grid">
      <el-card class="settings-card" shadow="never">
        <template #header>模型与连接</template>
        <p>供应商、模型、API Key 与 Base URL 将在下一任务接入。</p>
      </el-card>

      <el-card class="settings-card" shadow="never">
        <template #header>网络代理</template>
        <p>代理配置先本地保存，后续接入后端请求链路。</p>
      </el-card>

      <el-card class="settings-card" shadow="never">
        <template #header>工具权限</template>
        <p>控制 read_file、write_file、code_review、code_test 等工具的 allow / ask / deny 策略。</p>
      </el-card>

      <el-card class="settings-card" shadow="never">
        <template #header>记忆设置</template>
        <p>用记忆卡保存偏好、学习画像和项目上下文，让 AI 更懂用户。</p>
      </el-card>

      <el-card class="settings-card" shadow="never">
        <template #header>思考模式</template>
        <p>自动、快速、深度三档。第一轮不直接发送 Claude 原生 thinking 参数，避免兼容问题。</p>
      </el-card>
    </section>
  </div>
</template>

<style scoped>
.ai-settings-view {
  min-height: 100%;
  color: var(--km-gray-700);
}
.settings-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  padding: 4px 0 20px;
  border-bottom: 1px solid var(--km-border-light);
  margin-bottom: 20px;
}
.eyebrow {
  margin: 0 0 6px;
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--km-primary);
  font-weight: 700;
}
h1 {
  margin: 0;
  font-size: 28px;
  line-height: 1.1;
  color: var(--km-gray-800);
  letter-spacing: -0.03em;
}
.summary {
  margin: 10px 0 0;
  color: var(--km-gray-600);
  font-size: 13px;
  line-height: 1.7;
}
.settings-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}
.settings-card {
  border: 1px solid var(--km-border-light);
  background: var(--km-bg-layer-3);
  border-radius: var(--km-radius);
}
.settings-card :deep(.el-card__header) {
  padding: 12px 16px;
  font-size: 13px;
  font-weight: 650;
  color: var(--km-gray-800);
}
.settings-card :deep(.el-card__body) {
  padding: 14px 16px;
  color: var(--km-gray-600);
  font-size: 13px;
  line-height: 1.7;
}
@media (max-width: 980px) {
  .settings-grid { grid-template-columns: 1fr; }
}
</style>
```

- [ ] **Step 3: Mount view in MainArea**

Modify `frontend/src/ide/MainArea.vue` imports:

```js
import AISettings from '@/views/AISettings.vue'
```

Add in template after Dashboard:

```vue
<AISettings v-else-if="sidebar.activeView === 'ai-settings'" />
```

- [ ] **Step 4: Build**

Run:

```bash
cd frontend && npm run build
```

Expected: build succeeds.

- [ ] **Step 5: Manual smoke check**

Run:

```bash
npm run dev
```

Expected:

- ActivityBar shows AI 设置 icon.
- Top menu `AI 设置 → 打开 AI 控制中心` switches to AI settings.
- AI Settings shell renders without breaking other views.

- [ ] **Step 6: Checkpoint**

Run:

```bash
git status --short
```

Ask user before committing.

---

## Task 5: Implement AI Settings model/proxy/reasoning controls

**Files:**
- Modify: `frontend/src/views/AISettings.vue`
- Modify: `frontend/src/ide/AssistantPanel.vue`

- [ ] **Step 1: Replace AISettings shell script section**

Add a `<script setup>` block to `frontend/src/views/AISettings.vue`:

```vue
<script setup>
import { computed } from 'vue'
import { ElMessage } from 'element-plus'
import { useChatStore } from '@/stores/chat'
import { useAiSettingsStore, REASONING_MODE } from '@/stores/aiSettings'

const chat = useChatStore()
const aiSettings = useAiSettingsStore()

const providerLabel = computed(() => chat.PROVIDERS.find((p) => p.id === chat.provider)?.label || chat.provider)
const reasoningSupport = computed(() => aiSettings.modelReasoningSupport(chat.provider, chat.model))

function saveProvider(pid) {
  chat.setProvider(pid)
}

function saveModel(mid) {
  chat.model = mid
}

function saveApiKey(val) {
  chat.setApiKey(val || '')
}

function saveCustomBaseUrl(val) {
  chat.setCustomBaseUrl(val || '')
}

async function testConnection() {
  await chat.fetchModels()
  ElMessage.success('模型列表已刷新')
}
</script>
```

- [ ] **Step 2: Replace AISettings template with real controls**

Replace `frontend/src/views/AISettings.vue` template with:

```vue
<template>
  <div class="ai-settings-view">
    <header class="settings-hero">
      <div>
        <p class="eyebrow">AI Control Center</p>
        <h1>AI 设置</h1>
        <p class="summary">集中管理模型连接、网络代理、工具权限、记忆卡和思考模式。</p>
      </div>
      <el-tag type="info" effect="plain">{{ providerLabel }} · {{ chat.model || '未选择模型' }}</el-tag>
    </header>

    <section class="settings-grid">
      <el-card class="settings-card wide" shadow="never">
        <template #header>模型与连接</template>
        <el-form label-position="top" class="settings-form">
          <el-form-item label="供应商">
            <el-select :model-value="chat.provider" @change="saveProvider">
              <el-option v-for="p in chat.PROVIDERS" :key="p.id" :label="p.label" :value="p.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="模型">
            <el-select :model-value="chat.model" filterable allow-create @change="saveModel">
              <el-option v-for="m in chat.models" :key="m" :label="m" :value="m" />
            </el-select>
          </el-form-item>
          <el-form-item label="API Key">
            <el-input :model-value="chat.apiKey" type="password" show-password clearable @update:model-value="saveApiKey" />
          </el-form-item>
          <el-form-item v-if="chat.provider === 'custom'" label="API Base URL">
            <el-input :model-value="chat.customBaseUrl" clearable placeholder="https://api.example.com/v1" @update:model-value="saveCustomBaseUrl" />
          </el-form-item>
          <el-button type="primary" plain @click="testConnection">刷新模型列表</el-button>
        </el-form>
      </el-card>

      <el-card class="settings-card" shadow="never">
        <template #header>网络代理</template>
        <el-form label-position="top" class="settings-form">
          <el-form-item label="启用代理">
            <el-switch :model-value="aiSettings.proxy.enabled" @change="(v) => aiSettings.setProxy({ enabled: v })" />
          </el-form-item>
          <el-form-item label="代理类型">
            <el-select :model-value="aiSettings.proxy.type" @change="(v) => aiSettings.setProxy({ type: v })">
              <el-option label="HTTP" value="http" />
              <el-option label="HTTPS" value="https" />
              <el-option label="SOCKS" value="socks" />
            </el-select>
          </el-form-item>
          <el-form-item label="代理地址">
            <el-input :model-value="aiSettings.proxy.url" placeholder="http://127.0.0.1:7890" clearable @update:model-value="(v) => aiSettings.setProxy({ url: v })" />
          </el-form-item>
          <el-form-item label="生效范围">
            <el-select :model-value="aiSettings.proxy.scope" @change="(v) => aiSettings.setProxy({ scope: v })">
              <el-option label="全部供应商" value="all" />
              <el-option label="当前供应商" value="currentProvider" />
              <el-option label="仅自定义供应商" value="customOnly" />
            </el-select>
          </el-form-item>
          <p class="field-note">第一轮仅保存配置；后端代理接入将在后续任务完成。</p>
        </el-form>
      </el-card>

      <el-card class="settings-card" shadow="never">
        <template #header>思考模式</template>
        <el-radio-group :model-value="aiSettings.reasoningMode" @change="aiSettings.setReasoningMode">
          <el-radio-button :label="REASONING_MODE.AUTO">自动</el-radio-button>
          <el-radio-button :label="REASONING_MODE.FAST">快速</el-radio-button>
          <el-radio-button :label="REASONING_MODE.DEEP">深度</el-radio-button>
        </el-radio-group>
        <p class="field-note">当前模型能力：{{ reasoningSupport }}。深度模式会优先使用模型原生 reasoning；未知模型降级为提示词增强。</p>
      </el-card>
    </section>
  </div>
</template>
```

Keep and extend the existing styles. Add:

```css
.settings-card.wide { grid-column: span 2; }
.settings-form { max-width: 520px; }
.field-note {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--km-gray-500);
  line-height: 1.6;
}
@media (max-width: 980px) {
  .settings-card.wide { grid-column: span 1; }
}
```

- [ ] **Step 3: Replace AssistantPanel API Key dialog entry with settings entry**

In `frontend/src/ide/AssistantPanel.vue`, add `Setting` to imports:

```js
import { Delete, VideoPause, Promotion, EditPen, Check, MagicStick, Setting } from '@element-plus/icons-vue'
```

Add function near `onProviderChange`:

```js
function openAiSettings() {
  sidebar.setView('ai-settings')
}
```

Replace API key button block with:

```vue
<el-button
  size="small"
  class="apikey-btn"
  :class="{ set: !!chat.apiKey }"
  :title="chat.apiKey ? '打开 AI 设置（API Key 已设置）' : '打开 AI 设置（设置 API Key）'"
  :disabled="chat.streaming"
  @click="openAiSettings"
>
  <el-icon :size="14"><Setting /></el-icon>
</el-button>
```

Do not remove the dialog code yet; remove it in Task 8 cleanup after the settings page has all controls.

- [ ] **Step 4: Add reasoning mode mini button in AssistantPanel**

After tutor button in `AssistantPanel.vue`, add:

```vue
<el-tooltip content="切换思考模式：自动 / 快速 / 深度" placement="top">
  <el-button
    size="small"
    class="reasoning-btn"
    :class="{ on: aiSettings.reasoningMode === 'deep' }"
    :disabled="chat.streaming"
    @click="cycleReasoningMode"
  >
    {{ reasoningLabel }}
  </el-button>
</el-tooltip>
```

Update script imports:

```js
import { computed, ref, reactive, watch, nextTick } from 'vue'
import { useAiSettingsStore } from '@/stores/aiSettings'
```

After `const chat = useChatStore()`:

```js
const aiSettings = useAiSettingsStore()
const reasoningLabel = computed(() => {
  if (aiSettings.reasoningMode === 'deep') return '深思'
  if (aiSettings.reasoningMode === 'fast') return '快速'
  return '自动'
})
function cycleReasoningMode() {
  const next = aiSettings.reasoningMode === 'auto'
    ? 'deep'
    : aiSettings.reasoningMode === 'deep'
      ? 'fast'
      : 'auto'
  aiSettings.setReasoningMode(next)
}
```

Add CSS near `.tutor-btn`:

```css
.reasoning-btn {
  height: 30px;
  padding: 0 8px;
  font-size: 11px;
  border-radius: var(--km-radius-sm);
  opacity: 0.65;
  transition: all 0.2s var(--km-ease);
}
.reasoning-btn.on {
  opacity: 1;
  background: var(--km-primary-light);
  border-color: var(--km-primary);
  color: var(--km-primary);
  font-weight: 650;
}
```

- [ ] **Step 5: Build**

Run:

```bash
cd frontend && npm run build
```

Expected: build succeeds.

- [ ] **Step 6: Manual smoke check**

Run:

```bash
npm run dev
```

Expected:

- AI Settings page has model/proxy/reasoning controls.
- Changing provider/model/API Key still updates chat store.
- AssistantPanel settings button navigates to AI Settings.
- Reasoning mini button cycles 自动 → 深思 → 快速 → 自动.

- [ ] **Step 7: Checkpoint**

Run `git status --short` and ask user before committing.

---

## Task 6: Tool permission matrix UI

**Files:**
- Modify: `frontend/src/views/AISettings.vue`
- Modify: `frontend/src/stores/aiSettings.js` if labels are helpful
- Test: `frontend/src/__tests__/ai-settings-store.test.js`

- [ ] **Step 1: Add exported tool metadata**

Modify `frontend/src/stores/aiSettings.js` after `DEFAULT_TOOL_PERMISSIONS`:

```js
export const TOOL_PERMISSION_ITEMS = Object.freeze([
  { name: 'read_file', label: '读取文件', description: '允许 AI 读取当前工作区文件内容。' },
  { name: 'list_directory', label: '列目录', description: '允许 AI 查看项目目录结构。' },
  { name: 'write_file', label: '写文件', description: '允许 AI 请求创建或覆盖文件；保留安全预检和审批。' },
  { name: 'generate_project_graph', label: '生成项目图谱', description: '允许 AI 调用离线代码图谱解析。' },
  { name: 'code_review', label: '代码审查', description: '允许 AI 委派后端进行四维度代码审查。' },
  { name: 'code_test', label: '代码测试', description: '允许 AI 委派后端生成并执行 pytest 测试。' },
])
```

- [ ] **Step 2: Add a test for invalid permission handling**

Append to `ai-settings-store.test.js`:

```js
  it('ignores invalid tool permission changes', () => {
    const settings = useAiSettingsStore()
    settings.setToolPermission('code_test', 'deny')
    settings.setToolPermission('code_test', 'invalid')
    settings.setToolPermission('missing_tool', 'allow')

    expect(settings.toolPermissions.code_test).toBe('deny')
    expect(settings.permissionFor('missing_tool')).toBe('deny')
  })
```

Run:

```bash
cd frontend && npm test -- ai-settings-store.test.js
```

Expected: PASS.

- [ ] **Step 3: Add permission card to AISettings**

Update `AISettings.vue` script import:

```js
import { useAiSettingsStore, REASONING_MODE, TOOL_PERMISSION_ITEMS } from '@/stores/aiSettings'
```

Expose constant:

```js
const toolPermissionItems = TOOL_PERMISSION_ITEMS
```

Add this card inside `settings-grid` after proxy card:

```vue
<el-card class="settings-card wide" shadow="never">
  <template #header>工具权限</template>
  <div class="permission-list">
    <div v-for="tool in toolPermissionItems" :key="tool.name" class="permission-row">
      <div class="permission-copy">
        <strong>{{ tool.label }}</strong>
        <span>{{ tool.description }}</span>
        <code>{{ tool.name }}</code>
      </div>
      <el-segmented
        :model-value="aiSettings.permissionFor(tool.name)"
        :options="[
          { label: '允许', value: 'allow' },
          { label: '询问', value: 'ask' },
          { label: '禁用', value: 'deny' },
        ]"
        @change="(value) => aiSettings.setToolPermission(tool.name, value)"
      />
    </div>
  </div>
</el-card>
```

If Element Plus version lacks `el-segmented`, use this compatible fallback instead:

```vue
<el-radio-group
  :model-value="aiSettings.permissionFor(tool.name)"
  size="small"
  @change="(value) => aiSettings.setToolPermission(tool.name, value)"
>
  <el-radio-button label="allow">允许</el-radio-button>
  <el-radio-button label="ask">询问</el-radio-button>
  <el-radio-button label="deny">禁用</el-radio-button>
</el-radio-group>
```

Use the fallback if build fails on `el-segmented`.

Add styles:

```css
.permission-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.permission-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px;
  border: 1px solid var(--km-border-light);
  border-radius: var(--km-radius-sm);
  background: var(--km-bg-layer-2);
}
.permission-copy {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.permission-copy strong {
  color: var(--km-gray-800);
  font-size: 13px;
}
.permission-copy span {
  color: var(--km-gray-600);
  font-size: 12px;
  line-height: 1.5;
}
.permission-copy code {
  width: fit-content;
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--km-gray-200);
  color: var(--km-gray-600);
  font-size: 11px;
}
```

- [ ] **Step 4: Build and test**

Run:

```bash
cd frontend && npm test -- ai-settings-store.test.js && npm run build
```

Expected: tests and build pass.

- [ ] **Step 5: Manual smoke check**

Run:

```bash
npm run dev
```

Expected:

- Permission matrix displays all six tools.
- Changing a permission persists after refresh.
- Setting `code_test` to `deny` removes `code_test` from subsequent tool prompt text indirectly through Task 2 behavior.

- [ ] **Step 6: Checkpoint**

Run `git status --short` and ask user before committing.

---

## Task 7: Memory cards UI and prompt injection smoke

**Files:**
- Modify: `frontend/src/views/AISettings.vue`
- Test: `frontend/src/__tests__/ai-settings-store.test.js`

- [ ] **Step 1: Add memory form state to AISettings**

In `AISettings.vue` script, import `ref`:

```js
import { computed, ref } from 'vue'
```

Add:

```js
const memoryDraft = ref({ type: 'preference', title: '', content: '' })

function addMemoryCard() {
  const created = aiSettings.addMemory({
    ...memoryDraft.value,
    source: 'manual',
  })
  if (!created) {
    ElMessage.warning('请填写记忆标题和内容')
    return
  }
  memoryDraft.value = { type: 'preference', title: '', content: '' }
  ElMessage.success('记忆卡已添加')
}
```

- [ ] **Step 2: Add memory card UI**

Add this card inside `settings-grid` after permissions:

```vue
<el-card class="settings-card wide" shadow="never">
  <template #header>记忆设置</template>
  <div class="memory-editor">
    <el-select v-model="memoryDraft.type" size="small" class="memory-type">
      <el-option label="用户偏好" value="preference" />
      <el-option label="学习画像" value="learning" />
      <el-option label="项目上下文" value="project" />
    </el-select>
    <el-input v-model="memoryDraft.title" size="small" placeholder="记忆标题，例如：回答风格" />
    <el-input v-model="memoryDraft.content" type="textarea" :rows="2" resize="none" placeholder="记忆内容，例如：用户喜欢先讲思路再给代码。" />
    <el-button type="primary" plain @click="addMemoryCard">添加记忆卡</el-button>
  </div>

  <div class="memory-list" v-if="aiSettings.memories.length">
    <div v-for="memory in aiSettings.memories" :key="memory.id" class="memory-card" :class="{ disabled: !memory.enabled }">
      <div class="memory-head">
        <el-tag size="small" effect="plain">{{ memory.type }}</el-tag>
        <strong>{{ memory.title }}</strong>
        <el-switch :model-value="memory.enabled" @change="(v) => aiSettings.updateMemory(memory.id, { enabled: v })" />
      </div>
      <p>{{ memory.content }}</p>
      <div class="memory-actions">
        <span>{{ memory.source }} · {{ memory.updatedAt.slice(0, 10) }}</span>
        <el-button size="small" text type="danger" @click="aiSettings.removeMemory(memory.id)">删除</el-button>
      </div>
    </div>
  </div>
  <el-empty v-else description="还没有记忆卡" :image-size="80" />
</el-card>
```

Add styles:

```css
.memory-editor {
  display: grid;
  grid-template-columns: 140px minmax(180px, 1fr) auto;
  gap: 10px;
  align-items: start;
  margin-bottom: 14px;
}
.memory-editor :deep(.el-textarea) {
  grid-column: 1 / -1;
}
.memory-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.memory-card {
  padding: 12px;
  border: 1px solid var(--km-border-light);
  border-radius: var(--km-radius-sm);
  background: var(--km-bg-layer-2);
}
.memory-card.disabled {
  opacity: 0.55;
}
.memory-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.memory-head strong {
  flex: 1;
  min-width: 0;
  color: var(--km-gray-800);
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.memory-card p {
  margin: 8px 0;
  color: var(--km-gray-600);
  font-size: 12px;
  line-height: 1.6;
}
.memory-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: var(--km-gray-500);
  font-size: 11px;
}
@media (max-width: 980px) {
  .memory-editor { grid-template-columns: 1fr; }
  .memory-list { grid-template-columns: 1fr; }
}
```

- [ ] **Step 3: Add truncation test**

Append to `ai-settings-store.test.js`:

```js
  it('formats at most ten enabled memories and truncates long content', () => {
    const settings = useAiSettingsStore()
    for (let i = 0; i < 12; i++) {
      settings.addMemory({ title: `记忆${i}`, content: 'x'.repeat(260), type: 'project' })
    }

    const block = settings.formatEnabledMemories(10, 20)

    expect(block.match(/\[project\]/g)).toHaveLength(10)
    expect(block).toContain('xxxxxxxxxxxxxxxxxxxx…')
    expect(block).not.toContain('记忆10')
  })
```

- [ ] **Step 4: Run test and build**

Run:

```bash
cd frontend && npm test -- ai-settings-store.test.js && npm run build
```

Expected: PASS and build succeeds.

- [ ] **Step 5: Manual smoke check**

Run:

```bash
npm run dev
```

Expected:

- Can add a memory card.
- Toggle disables it visually and removes it from `enabledMemories`.
- Delete removes it.
- After page reload, memory cards persist.

- [ ] **Step 6: Checkpoint**

Run `git status --short` and ask user before committing.

---

## Task 8: Cleanup AssistantPanel API dialog and improve shell visual polish

**Files:**
- Modify: `frontend/src/ide/AssistantPanel.vue`
- Modify: `frontend/src/views/Workspace.vue`
- Modify: `frontend/src/ide/ActivityBar.vue`
- Modify: `frontend/src/ide/FileExplorer.vue`
- Modify: `frontend/src/ide/StatusBar.vue`
- Modify: `frontend/src/styles/theme.css`

- [ ] **Step 1: Remove unused API dialog from AssistantPanel**

Remove the `<el-dialog>` block titled `API 设置` from `AssistantPanel.vue` lines around the current API key dialog.

Remove these script refs/functions if no longer referenced:

```js
const apiKeyDialogVisible = ref(false)
const apiKeyInput = ref('')
const baseUrlInput = ref('')
function openApiKeyDialog() { ... }
function saveApiKey() { ... }
```

Keep `openAiSettings()` from Task 5.

- [ ] **Step 2: Add titlebar/menu tokens**

In `frontend/src/styles/theme.css`, add to light theme after title/status tokens:

```css
  --km-titlebar-bg: rgba(247, 246, 245, 0.92);
  --km-titlebar-menu-hover: rgba(108, 124, 224, 0.10);
```

Add to `html.dark`:

```css
  --km-titlebar-bg: rgba(22, 21, 18, 0.92);
  --km-titlebar-menu-hover: rgba(139, 156, 240, 0.12);
```

- [ ] **Step 3: Polish Workspace titlebar**

Modify `Workspace.vue` `.ide-titlebar`:

```css
.ide-titlebar {
  height: 38px;
  background: var(--km-titlebar-bg, var(--kbg-elevated));
  border-bottom: 1px solid var(--km-border-light);
  display: grid;
  grid-template-columns: minmax(420px, 1fr) auto minmax(260px, 1fr);
  align-items: center;
  padding: 0 10px;
  flex-shrink: 0;
  -webkit-app-region: drag;
  backdrop-filter: blur(16px);
}
.title-left { min-width: 0; }
.title-center {
  display: flex; align-items: center; gap: 6px;
  min-width: 0;
  max-width: 420px;
  padding: 4px 10px;
  border-radius: var(--km-radius-sm);
  background: var(--km-bg-layer-1);
  border: 1px solid var(--km-border-light);
  font-size: 12px; color: var(--ktext-secondary);
  -webkit-app-region: no-drag;
}
.title-center span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.title-right {
  justify-self: end;
  -webkit-app-region: no-drag;
}
.title-hint { font-size: 11px; color: var(--ktext-muted); }
```

- [ ] **Step 4: Polish ActivityBar active/hover state**

Modify `ActivityBar.vue` styles:

```css
.activity-bar {
  width: 48px;
  background: var(--km-activity-bg);
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 8px 0;
  flex-shrink: 0;
  border-right: 1px solid rgba(255,255,255,0.05);
  box-shadow: inset -1px 0 rgba(0,0,0,0.12);
}
.activity-item:hover {
  opacity: 0.9;
  background: rgba(255,255,255,0.07);
  transform: translateY(-1px);
}
.activity-item:active { transform: scale(0.96); }
.activity-item.active {
  opacity: 1;
  background: rgba(139,156,240,0.14);
  color: #fff;
}
.activity-item.active::before {
  content: '';
  position: absolute;
  left: -8px; top: 7px; bottom: 7px;
  width: 2px;
  border-radius: 2px;
  background: var(--km-activity-active);
  box-shadow: 0 0 10px rgba(139,156,240,0.65);
}
```

- [ ] **Step 5: Polish FileExplorer active row**

Modify `FileExplorer.vue` styles:

```css
.file-explorer {
  width: 246px;
  background: var(--km-bg-layer-0);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  height: 100%;
  border-right: 1px solid var(--km-border-light);
  font-size: 13px;
}
.explorer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  height: 42px;
  flex-shrink: 0;
  border-bottom: 1px solid var(--km-border-light);
}
.tree-node {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 28px;
  margin: 1px 6px;
  padding-right: 8px;
  border-radius: 7px;
  cursor: pointer;
  color: var(--km-gray-700);
  user-select: none;
  transition: background 0.12s var(--km-ease), color 0.12s var(--km-ease);
}
.tree-node:hover { background: var(--km-gray-200); }
.tree-node.active {
  background: var(--km-primary-light);
  color: var(--km-primary-active);
  font-weight: 550;
}
```

- [ ] **Step 6: Polish StatusBar**

Modify `StatusBar.vue` styles:

```css
.status-bar {
  height: 24px;
  background: var(--km-statusbar-bg);
  color: var(--km-gray-600);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px;
  font-size: 12px;
  flex-shrink: 0;
  border-top: 1px solid rgba(255,255,255,0.05);
}
.status-item {
  display: flex;
  align-items: center;
  gap: 4px;
  max-width: 520px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.status-item.clickable:hover {
  color: var(--km-primary);
}
```

- [ ] **Step 7: Build**

Run:

```bash
cd frontend && npm run build
```

Expected: build succeeds.

- [ ] **Step 8: Manual UI smoke**

Run:

```bash
npm run dev
```

Expected:

- Titlebar looks integrated with custom menu.
- ActivityBar active item is clearer.
- FileExplorer active and hover rows are clearer.
- StatusBar remains readable in light and dark modes.
- AssistantPanel no longer has separate API dialog; settings button opens AI Settings.

- [ ] **Step 9: Checkpoint**

Run `git status --short` and ask user before committing.

---

## Task 9: Generic ask-permission placeholder for non-write tools

**Files:**
- Modify: `frontend/src/stores/chat.js`
- Modify: `frontend/src/ide/AssistantPanel.vue`
- Test: `frontend/src/__tests__/chat-ai-settings.test.js`

- [ ] **Step 1: Add generic pending tool approval state**

In `chat.js` after `pendingApproval` state, add:

```js
  const pendingToolApproval = ref(null)
  let _toolApprovalId = 0
```

Add helper:

```js
  function _requestToolApproval(call) {
    return new Promise((resolve) => {
      pendingToolApproval.value = {
        id: `tool_appr_${++_toolApprovalId}`,
        call,
        resolve,
      }
    })
  }

  function resolveToolApproval(decision) {
    const p = pendingToolApproval.value
    if (!p) return
    pendingToolApproval.value = null
    p.resolve(decision || { approved: false })
  }
```

Return them from store:

```js
pendingToolApproval, resolveToolApproval,
```

- [ ] **Step 2: Apply ask mode before tool execution**

At the start of `_executeTool(call)` after denied check, add:

```js
      if (call.tool !== 'write_file' && aiSettings.shouldAskForTool(call.tool)) {
        const decision = await _requestToolApproval(call)
        if (!decision.approved) return { error: `用户拒绝执行工具 ${call.tool}` }
      }
```

`write_file` keeps its stronger existing approval card.

- [ ] **Step 3: Add approval card UI**

In `AssistantPanel.vue`, before the existing write_file approval card, add:

```vue
<div v-if="chat.pendingToolApproval" class="approval-card tool-approval-card">
  <div class="approval-header">
    <el-icon :size="15"><EditPen /></el-icon>
    <span class="approval-title">工具执行审批</span>
    <el-tag size="small" type="info">{{ chat.pendingToolApproval.call.tool }}</el-tag>
  </div>
  <div class="safety-block">
    <div class="safety-line warn">AI 请求执行该工具。你可以允许或拒绝。</div>
    <pre class="tool-approval-json">{{ JSON.stringify(chat.pendingToolApproval.call, null, 2) }}</pre>
  </div>
  <div class="approval-actions">
    <el-button size="small" @click="chat.resolveToolApproval({ approved: false })">拒绝</el-button>
    <el-button size="small" type="primary" @click="chat.resolveToolApproval({ approved: true })">
      <el-icon :size="14"><Check /></el-icon>&nbsp;允许执行
    </el-button>
  </div>
</div>
```

Add CSS:

```css
.tool-approval-json {
  margin: 8px 0 0;
  max-height: 120px;
  overflow: auto;
  font-family: var(--km-font-mono);
  font-size: 11px;
  color: var(--km-gray-600);
  background: var(--km-bg-layer-1);
  border-radius: 6px;
  padding: 8px;
}
```

- [ ] **Step 4: Ensure clearMessages rejects generic approval**

In `clearMessages()` after pendingApproval cleanup, add:

```js
    if (pendingToolApproval.value) {
      const p = pendingToolApproval.value
      pendingToolApproval.value = null
      p.resolve({ approved: false })
    }
```

- [ ] **Step 5: Build**

Run:

```bash
cd frontend && npm run build
```

Expected: build succeeds.

- [ ] **Step 6: Manual permission smoke**

Run:

```bash
npm run dev
```

Manual steps:

1. Open AI Settings.
2. Set `code_test` to `询问`.
3. Ask AI to run a code test using a tool call.
4. Expected: generic tool approval card appears before execution.
5. Reject it.
6. Expected: tool result says user refused.

- [ ] **Step 7: Checkpoint**

Run `git status --short` and ask user before committing.

---

## Task 10: Final verification and docs update

**Files:**
- Modify: `docs/devlogs/2026-06-21-ai-control-center-shell.md` or create it if missing
- Modify: `docs/BUG决策日志.md` only if bugs are discovered during implementation
- Optional modify: `CLAUDE.md` if the project’s current phase summary needs updating

- [ ] **Step 1: Run frontend unit tests**

Run:

```bash
cd frontend && npm test
```

Expected: all frontend tests pass.

- [ ] **Step 2: Run root test suite**

Run:

```bash
npm test
```

Expected: Vitest tests pass from root.

- [ ] **Step 3: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: Vite build succeeds.

- [ ] **Step 4: Run Electron build**

Run:

```bash
npm run build
```

Expected: electron-vite build succeeds.

- [ ] **Step 5: Manual smoke in dev app**

Run:

```bash
npm run dev
```

Manual checklist:

- Default native Window/Help menu is gone.
- Custom titlebar menu works.
- Project menu opens/refreshes project.
- Learning menu switches to graph/assessment/learning/agents/dashboard.
- AI Settings opens from menu and activity bar.
- Model/API settings still affect AssistantPanel.
- Proxy settings persist after reload.
- Permission matrix persists after reload.
- Memory cards can be added/disabled/deleted and persist after reload.
- Reasoning button cycles modes and does not break normal chat.
- Denied tools are not advertised in prompt and are blocked if stale tool calls appear.
- `write_file` still uses the stronger safety approval card.

- [ ] **Step 6: Write devlog**

Create `docs/devlogs/2026-06-21-ai-control-center-shell.md`:

```markdown
# 2026-06-21 AI 控制中心外壳升级

## 完成内容

- 隐藏 Electron 默认菜单，新增 KMatch 自定义标题栏菜单。
- 新增 AI 设置视图，集中管理模型连接、代理配置、工具权限、记忆卡和思考模式。
- 新增 AI 设置 Pinia store，使用 localStorage 持久化。
- AI 助手读取 AI 设置：工具权限、启用记忆和思考模式会影响后续对话。
- AssistantPanel 改为轻量入口，保留导学模式并增加思考模式按钮。

## 验证

- `cd frontend && npm test`
- `npm test`
- `cd frontend && npm run build`
- `npm run build`
- `npm run dev` 手动 smoke

## 后续

- 后端代理配置真实生效。
- 模型能力动态探测。
- Claude 原生 thinking/effort 参数适配。
- 记忆持久化升级为本地文件或数据库。
```

- [ ] **Step 7: Review git diff**

Run:

```bash
git status --short
git diff --stat
```

Expected: planned files only.

- [ ] **Step 8: Ask user before commit**

Do not commit without explicit user instruction. If user authorizes, commit with:

```bash
git add electron/main/index.js electron/preload/index.js frontend/src docs/superpowers docs/devlogs
git commit -m "feat(ui): AI 控制中心与自定义标题栏菜单"
```

---

## Self-Review

### Spec coverage

- Custom titlebar menu and default menu removal: Task 3.
- IDE shell visual polish: Task 8.
- AI Settings page: Tasks 4-7.
- Model/API settings: Task 5.
- Proxy settings UI and persistence: Task 5.
- Tool permissions and enforcement: Tasks 2, 6, 9.
- Memory cards and prompt injection: Tasks 1, 2, 7.
- Deep thinking / reasoning mode: Tasks 1, 2, 5.
- Backend proxy and Claude native thinking are explicitly deferred: Task 10 devlog follow-up.

### Placeholder scan

No `TBD`, `TODO`, “similar to”, or unfilled implementation placeholders are present. Deferred work is explicitly out of first-round scope and listed as follow-up.

### Type consistency

- Store name is consistently `useAiSettingsStore`.
- Reasoning modes are consistently `auto | fast | deep`.
- Tool permission modes are consistently `allow | ask | deny`.
- Memory card fields match the spec: `id`, `type`, `title`, `content`, `source`, `enabled`, `createdAt`, `updatedAt`.
