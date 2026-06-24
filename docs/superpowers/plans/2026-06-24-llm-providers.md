# Spec A — 聊天框 Apix 化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 AI 助手聊天框具备多厂商（8 项）+ 动态模型 + 模型能力徽章 + 三态思考模式 + 视觉探测 + 图片上传 + Anthropic 原生协议的对话体验，与 Apix 对齐。

**Architecture:** 前端 `aiSettings` 是厂商配置单一源 → 新增 `customProviders`（列表 schema 但 UI 仍 1 组）/ `modelVision`（运行时探测缓存）两个 store + `services/llm/modelCapabilities.js`（静态能力表）。`chat.js` 把 body 从 `reasoning: bool|None` 改为 `reasoning_mode + protocol`，user 消息 content 支持 OpenAI 多模态数组。后端 `chat.py` 按 `protocol` 分支 OpenAI / Anthropic 双 stream，发出形状一致的 SSE 帧。`AssistantPanel.vue` 工具栏加 reasoning radio + 📎 上传按钮，模型 hint 换成带徽章的 select。所有改动**对 chat.js 工具循环 / 审批门 / 重生成分支无入侵**。

**Tech Stack:** Vue 3 + Pinia + Element Plus 2.8, AsyncOpenAI + anthropic>=0.40.0, Vitest 2.1, pytest, FastAPI StreamingResponse SSE。

**Spec:** [docs/superpowers/specs/2026-06-24-llm-providers-design.md](../specs/2026-06-24-llm-providers-design.md)

---

## File Structure

**新增（4 模块 + 8 图标 + 9 测试）:**

- `frontend/src/stores/customProviders.js` — 自定义厂商列表 store（schema 已多组，UI 本期 1 组）
- `frontend/src/stores/modelVision.js` — 视觉能力缓存 + 探测调度
- `frontend/src/services/llm/modelCapabilities.js` — 模型能力静态表 + `capabilityOf(provider, model)`
- `frontend/src/assets/icons/llm_providers/*.svg` — deepseek/openai/claude/moonshot/qwen/google/ollama/custom（8 个，从 Apix 复制）
- `frontend/src/__tests__/customProviders-store.test.js`
- `frontend/src/__tests__/modelCapabilities.test.js`
- `frontend/src/__tests__/modelVision-store.test.js`
- `frontend/src/__tests__/chat-attachments.test.js`
- `backend/tests/test_chat_models_api.py`
- `backend/tests/test_chat_probe_vision.py`
- `backend/tests/test_chat_build_request_extras.py`
- `backend/tests/test_chat_anthropic_stream.py`
- `backend/tests/test_chat_openai_to_anthropic_msg.py`

**修改:**

- `frontend/src/stores/aiSettings.js` — PROVIDERS 扩 8 项；`provider` 值域支持 `custom:<uuid>`；customBaseUrl → customProviders 列表；`providerMeta()` / `getBaseUrl()` 透 custom；`modelReasoningSupport` 改委托 capabilityOf
- `frontend/src/stores/chat.js` — body 字段 `reasoning_mode + protocol`，删 `_reasoningForRequest`；`pendingAttachments` + `addAttachment` / `removeAttachment` / `clearAttachments`；`sendMessage` 多模态 content；`contentTextOf` 支持数组；构建 apiMessages 时 user 消息原样传
- `frontend/src/ide/AssistantPanel.vue` — 工具栏加 reasoning radio（三态）+ 📎 上传 + 拖拽 + 预览条；厂商下拉用 icon；模型 hint 换 select + 徽章；🔑 弹窗写入 customProviders[id=default]；user 消息渲染加 `_attachments` 块
- `frontend/src/__tests__/ai-settings-store.test.js` — 旧断言 `Claude → 'native-when-supported-by-backend'` 改为 `'native'`；新增 customBaseUrl 迁移、`provider='custom:default'` 形态、reasoningMode 自动降级
- `frontend/src/__tests__/chat-ai-settings.test.js` — 新增 `reasoning_mode` + `protocol` 字段断言
- `backend/app/api/chat.py` — ChatRequest +`protocol` +`reasoning_mode`（删 `reasoning`）；`_resolve_client` 拆 OpenAI / Anthropic 双；`_stream_chat` → `_stream_openai` + `_stream_anthropic`；`_build_extra_body` → `_build_request_extras`；+`/probe-vision`、+DELETE `/probe-vision/cache`、`_load_vision_cache` / `_save_vision_cache`；`/models` 加 `protocol` 字段 + `ANTHROPIC_MODELS` 硬编码
- `backend/requirements.txt` — `+anthropic>=0.40.0`

---

## 现状关键事实（实施前必读）

- `aiSettings.PROVIDERS` 目前 4 项：deepseek/openai/ollama/custom，无 `protocol`/`iconKey`。`provider` 是单字符串（id）；`apiKey` / `customBaseUrl` / `model` 各一 ref，全部走单 blob `kmatch-ai-settings` 持久化。
- `aiSettings.modelReasoningSupport(provider, model)` 返回 `'native'` / `'native-when-supported-by-backend'` / `'prompt-only'` / `'unknown'` 四态。被 `chat.js:614` 和 [ai-settings-store.test.js:99](../../../frontend/src/__tests__/ai-settings-store.test.js#L99) 调用。**本期收敛为 `'native'` / `'prompt-only'` 两态**（anthropic 协议已直连）。
- `aiSettings.fetchModels()` 当前 body `{base_url, api_key}`；后端 [chat.py:191 list_models](../../../backend/app/api/chat.py#L191) 直接走 AsyncOpenAI。新增 `protocol` 字段：anthropic 时短路返回 `ANTHROPIC_MODELS` 列表（API 无 /models 端点）。
- `chat.js:374-375` 当前 body `reasoning: bool|undefined`，靠 `_reasoningForRequest()` 推导。本期改为 `reasoning_mode: 'auto'|'fast'|'deep'` + `protocol: 'openai'|'anthropic'`，删 `_reasoningForRequest`。
- `chat.js:716-718` 构建 apiMessages 时 `historyMsgs = visibleMessages.value.map(m => ({role, content: m.role==='assistant' ? stripToolCalls(contentTextOf(m)) : contentTextOf(m)}))`。**本期 user 分支改为：content 是数组（多模态）原样传，是 string 走 contentTextOf**。
- `chat.js` 工具循环、`pendingApproval`、`regenMessage` 都依赖 `contentTextOf` / `visibleMessages` 等 helper —— **本期 helper 扩展为"数组 content 时拼接 type==='text' 段"**，保证向后兼容。
- `AssistantPanel.vue:194-199` 当前 user 消息是 6 行纯文本气泡（`<pre class="user-text">`）。
- `AssistantPanel.vue:286+` 工具栏顺序：厂商 select → 🔑 → 导学 → 模型 hint → 发送。**本期 reasoning radio 放导学和模型 select 之间，📎 放发送按钮左边**。
- `_get_async_client(base_url, api_key)` 用 `@lru_cache(maxsize=16)` 缓存。新增 `_get_anthropic_client(api_key)` 同样 lru_cache。
- `_stream_chat` 当前发 SSE 帧形状：`{delta: str}` / `{reasoning: str}` / `{error: str}` / `[DONE]`。两个新 stream 函数发**完全相同的帧**，前端无感。
- 后端单测用 `pytest`，集中在 `backend/tests/`；前端单测用 `vitest`，集中在 `frontend/src/__tests__/`。前端有 `pinia` setActivePinia + localStorage clear 的隔离套路；后端用 `httpx.AsyncClient` + `monkeypatch` mock 外部调用。
- 项目 commit 风格：`feat(scope): 中文简述` / `fix(scope): ...`，每 PR 末尾必带 Co-Authored-By。

---

## 实施顺序（5 个 PR，逐步落地）

| PR | 范围 | 任务编号 |
| --- | --- | --- |
| PR-1 厂商注册表 + customProviders | §1 / §2 / fetchModels protocol 字段 | Task 1-4 |
| PR-2 模型能力 + reasoning UI | modelCapabilities / reasoning radio / reasoningMode 自动降级 / ChatRequest reasoning_mode | Task 5-9 |
| PR-3 Anthropic 协议 | anthropic 包 / 双 stream / msg 转换 / requirements | Task 10-13 |
| PR-4 Vision 探测 | probe-vision endpoint / modelVision store / 触发时机 | Task 14-17 |
| PR-5 图片上传 | pendingAttachments / sendMessage 多模态 / UI 📎 + 拖拽 + 预览 | Task 18-22 |

每个 PR 独立可 merge；任务序号是顺序依赖。

---


## PR-1 厂商注册表 + customProviders schema

### Task 1: customProviders store（独立持久化 + CRUD）

**Files:**
- Create: `frontend/src/stores/customProviders.js`
- Test: `frontend/src/__tests__/customProviders-store.test.js`

新 store 独立 localStorage key（`kmatch-ai-custom-providers`），不混进 aiSettings blob，避免单点超量。

- [ ] **Step 1: 写失败测试**

`frontend/src/__tests__/customProviders-store.test.js`:

```js
import { describe, it, expect, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useCustomProvidersStore } from '@/stores/customProviders'

describe('customProviders store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('add returns new item with id/timestamps and persists', () => {
    const s = useCustomProvidersStore()
    const cp = s.add({ name: '本地', baseUrl: 'http://localhost:8080/v1', apiKey: 'k', models: ['x'] })
    expect(cp.id).toBeTruthy()
    expect(cp.createdAt).toBeTruthy()
    expect(s.list).toHaveLength(1)

    setActivePinia(createPinia())
    const s2 = useCustomProvidersStore()
    expect(s2.list[0].baseUrl).toBe('http://localhost:8080/v1')
  })

  it('update merges patch and bumps updatedAt', async () => {
    const s = useCustomProvidersStore()
    const cp = s.add({ name: 'a', baseUrl: 'u', apiKey: 'k' })
    const t0 = cp.updatedAt
    await new Promise(r => setTimeout(r, 5))
    const next = s.update(cp.id, { apiKey: 'k2' })
    expect(next.apiKey).toBe('k2')
    expect(next.updatedAt).not.toBe(t0)
    expect(next.createdAt).toBe(cp.createdAt)
  })

  it('remove drops the item', () => {
    const s = useCustomProvidersStore()
    const a = s.add({ name: 'a', baseUrl: 'u' })
    s.add({ name: 'b', baseUrl: 'u2' })
    s.remove(a.id)
    expect(s.list).toHaveLength(1)
    expect(s.get(a.id)).toBeUndefined()
  })

  it('add with id="default" is stable across calls (used by 1-group UI)', () => {
    const s = useCustomProvidersStore()
    s.add({ id: 'default', name: '自定义', baseUrl: 'u' })
    s.add({ id: 'default', name: '自定义', baseUrl: 'u2' })  // upsert by id
    expect(s.list).toHaveLength(1)
    expect(s.get('default').baseUrl).toBe('u2')
  })
})
```

- [ ] **Step 2: 运行测试验证全部失败**

Run: `cd frontend && npx vitest run src/__tests__/customProviders-store.test.js`
Expected: FAIL（store 不存在）

- [ ] **Step 3: 实现 store**

`frontend/src/stores/customProviders.js`:

```js
import { ref } from 'vue'
import { defineStore } from 'pinia'

const STORAGE_KEY = 'kmatch-ai-custom-providers'

function nowIso() { return new Date().toISOString() }
function uuid() { return `cp_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}` }

function loadList() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const arr = JSON.parse(raw)
    return Array.isArray(arr) ? arr : []
  } catch { return [] }
}

function saveList(list) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(list)) } catch { /* quota / private mode */ }
}

function normalize(input, prev) {
  const ts = nowIso()
  return {
    id: input.id || prev?.id || uuid(),
    name: input.name ?? prev?.name ?? '自定义',
    baseUrl: input.baseUrl ?? prev?.baseUrl ?? '',
    apiKey: input.apiKey ?? prev?.apiKey ?? '',
    models: Array.isArray(input.models) ? input.models : (prev?.models || []),
    protocol: input.protocol ?? prev?.protocol ?? 'openai',
    description: input.description ?? prev?.description ?? '',
    createdAt: prev?.createdAt || ts,
    updatedAt: ts,
  }
}

export const useCustomProvidersStore = defineStore('customProviders', () => {
  const list = ref(loadList())

  function persist() { saveList(list.value) }

  function add(input) {
    const id = input?.id
    if (id) {
      const existing = list.value.find((c) => c.id === id)
      if (existing) return update(id, input)  // upsert by id
    }
    const item = normalize(input || {})
    list.value = [...list.value, item]
    persist()
    return item
  }

  function update(id, patch) {
    let next = null
    list.value = list.value.map((c) => {
      if (c.id !== id) return c
      next = normalize({ ...patch, id }, c)
      return next
    })
    persist()
    return next
  }

  function remove(id) {
    list.value = list.value.filter((c) => c.id !== id)
    persist()
  }

  function get(id) { return list.value.find((c) => c.id === id) }

  async function autoFetchModels(id) {
    const cp = get(id)
    if (!cp || !cp.baseUrl) return { ok: false, error: 'baseUrl 未配置' }
    try {
      const res = await window.api.http.request('POST', '/api/chat/models', {
        base_url: cp.baseUrl, api_key: cp.apiKey || '', protocol: cp.protocol || 'openai',
      })
      const data = res.body
      if (!res.ok || data?.error) return { ok: false, error: data?.error || `HTTP ${res.status}` }
      const models = Array.isArray(data.models) ? data.models : []
      update(id, { models })
      return { ok: true, models }
    } catch (e) {
      return { ok: false, error: e.message || '请求失败' }
    }
  }

  return { list, add, update, remove, get, autoFetchModels }
})
```

- [ ] **Step 4: 跑测验证通过**

Run: `cd frontend && npx vitest run src/__tests__/customProviders-store.test.js`
Expected: PASS（4 cases）

- [ ] **Step 5: Commit**

```bash
git add frontend/src/stores/customProviders.js frontend/src/__tests__/customProviders-store.test.js
git commit -m "feat(stores): 新增 customProviders store — 多组列表 schema + CRUD + autoFetchModels"
```

---

### Task 2: PROVIDERS 扩 8 项 + protocol/iconKey/fallbackModels

**Files:**
- Modify: `frontend/src/stores/aiSettings.js:21-44`（PROVIDERS + fallbackModels 函数）
- Test: `frontend/src/__tests__/ai-settings-store.test.js`（已有，扩 cases）

- [ ] **Step 1: 加失败测试**

在 `frontend/src/__tests__/ai-settings-store.test.js` 顶部 import 行后追加新 describe（保留既有）：

```js
import { PROVIDERS } from '@/stores/aiSettings'

describe('PROVIDERS registry (Spec A)', () => {
  it('exposes 8 predefined + custom with required metadata', () => {
    const ids = PROVIDERS.map((p) => p.id)
    expect(ids).toEqual(['deepseek','openai','anthropic','moonshot','qwen','gemini','ollama','custom'])
    for (const p of PROVIDERS) {
      expect(typeof p.label).toBe('string')
      expect(['openai','anthropic']).toContain(p.protocol)
      expect(typeof p.iconKey).toBe('string')
      expect(Array.isArray(p.fallbackModels)).toBe(true)
    }
  })

  it('anthropic uses anthropic protocol; others openai', () => {
    expect(PROVIDERS.find((p) => p.id === 'anthropic').protocol).toBe('anthropic')
    expect(PROVIDERS.find((p) => p.id === 'gemini').protocol).toBe('openai')   // gemini 走 openai 兼容
  })
})
```

- [ ] **Step 2: 跑测验证失败**

Run: `cd frontend && npx vitest run src/__tests__/ai-settings-store.test.js -t "PROVIDERS registry"`
Expected: FAIL（缺 anthropic/moonshot/...）

- [ ] **Step 3: 改 PROVIDERS**

`frontend/src/stores/aiSettings.js:21-26` 替换为：

```js
export const PROVIDERS = Object.freeze([
  { id: 'deepseek',  label: 'DeepSeek',         baseUrl: 'https://api.deepseek.com/v1',
    protocol: 'openai',    iconKey: 'deepseek',
    fallbackModels: ['deepseek-v4-pro', 'deepseek-v3', 'deepseek-reasoner'] },
  { id: 'openai',    label: 'OpenAI',           baseUrl: 'https://api.openai.com/v1',
    protocol: 'openai',    iconKey: 'openai',
    fallbackModels: ['gpt-4o', 'gpt-4o-mini', 'gpt-4.1', 'o1', 'o3-mini'] },
  { id: 'anthropic', label: 'Anthropic',        baseUrl: 'https://api.anthropic.com',
    protocol: 'anthropic', iconKey: 'claude',
    fallbackModels: ['claude-fable-5', 'claude-opus-4-8', 'claude-sonnet-4-6', 'claude-haiku-4-5'] },
  { id: 'moonshot',  label: 'Moonshot',         baseUrl: 'https://api.moonshot.cn/v1',
    protocol: 'openai',    iconKey: 'moonshot',
    fallbackModels: ['moonshot-v1-128k', 'moonshot-v1-32k', 'kimi-k2-0905-preview'] },
  { id: 'qwen',      label: '通义千问',          baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    protocol: 'openai',    iconKey: 'qwen',
    fallbackModels: ['qwen-max', 'qwen-plus', 'qwen-turbo', 'qwen-vl-max'] },
  { id: 'gemini',    label: 'Google Gemini',    baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai',
    protocol: 'openai',    iconKey: 'google',
    fallbackModels: ['gemini-2.5-pro', 'gemini-2.5-flash'] },
  { id: 'ollama',    label: 'Ollama (本地)',    baseUrl: 'http://localhost:11434/v1',
    protocol: 'openai',    iconKey: 'ollama',
    fallbackModels: ['llama3', 'qwen2.5', 'codellama'] },
  { id: 'custom',    label: '自定义',            baseUrl: '',
    protocol: 'openai',    iconKey: 'custom',
    fallbackModels: [] },
])
```

`fallbackModels(pid)` 函数也改为从 PROVIDERS 表读（DRY）：

```js
function fallbackModels(pid) {
  // custom:<uuid> 走 customProviders.models, 这里只处理 predefined id
  const meta = PROVIDERS.find((p) => p.id === pid)
  return meta ? [...meta.fallbackModels] : []
}
```

- [ ] **Step 4: 跑测验证通过**

Run: `cd frontend && npx vitest run src/__tests__/ai-settings-store.test.js`
Expected: PASS（新 cases + 既有不破）

- [ ] **Step 5: Commit**

```bash
git add frontend/src/stores/aiSettings.js frontend/src/__tests__/ai-settings-store.test.js
git commit -m "feat(aiSettings): PROVIDERS 扩 8 项 + protocol/iconKey/fallbackModels 元数据"
```

---

### Task 3: provider 值域支持 custom:<uuid> + 迁移旧 customBaseUrl

**Files:**
- Modify: `frontend/src/stores/aiSettings.js`（loadProviderConfig / providerMeta / getBaseUrl / setApiKey / setCustomBaseUrl）
- Test: `frontend/src/__tests__/ai-settings-store.test.js`

引入 `isCustomProvider(p)` / `customProviderUuid(p)` 两个 helper（spec §7 风险点：禁止散落 split）。

- [ ] **Step 1: 加失败测试**

在 `ai-settings-store.test.js` 末尾追加：

```js
import { useCustomProvidersStore } from '@/stores/customProviders'

describe('provider value-set: custom:<uuid> (Spec A)', () => {
  beforeEach(() => { setActivePinia(createPinia()); localStorage.clear() })

  it('migrates legacy customBaseUrl + provider="custom" to customProviders[id=default]', () => {
    localStorage.setItem('kmatch-ai-settings', JSON.stringify({
      providerConfig: { provider: 'custom', apiKey: 'sk-X', customBaseUrl: 'http://x/v1', model: 'm' },
    }))
    const s = useAiSettingsStore()
    const cps = useCustomProvidersStore()
    expect(s.provider).toBe('custom:default')
    expect(cps.list).toHaveLength(1)
    expect(cps.get('default').baseUrl).toBe('http://x/v1')
    expect(cps.get('default').apiKey).toBe('sk-X')
  })

  it('providerMeta() reads from customProviders when provider startsWith custom:', () => {
    const cps = useCustomProvidersStore()
    cps.add({ id: 'default', name: 'X', baseUrl: 'http://y/v1', apiKey: 'k', protocol: 'openai' })
    const s = useAiSettingsStore()
    s.provider = 'custom:default'   // 直接改 ref, 不走 setProvider 避免 fetchModels
    const meta = s.providerMeta()
    expect(meta.baseUrl).toBe('http://y/v1')
    expect(meta.protocol).toBe('openai')
    expect(meta.label).toBe('X')
  })

  it('getBaseUrl returns custom entry baseUrl', () => {
    const cps = useCustomProvidersStore()
    cps.add({ id: 'default', name: 'X', baseUrl: 'http://z/v1' })
    const s = useAiSettingsStore()
    s.provider = 'custom:default'
    expect(s.getBaseUrl()).toBe('http://z/v1')
  })

  it('falls back to PROVIDERS[0] when custom:<uuid> entry missing', () => {
    const s = useAiSettingsStore()
    s.provider = 'custom:ghost'
    expect(s.providerMeta().id).toBe('deepseek')
  })
})
```

- [ ] **Step 2: 跑测验证失败**

Run: `cd frontend && npx vitest run src/__tests__/ai-settings-store.test.js -t "custom:<uuid>"`
Expected: FAIL

- [ ] **Step 3: 加 helper + 改 loadProviderConfig**

`frontend/src/stores/aiSettings.js` 顶部 import 区下加：

```js
import { useCustomProvidersStore } from './customProviders'

export function isCustomProvider(p) {
  return typeof p === 'string' && p.startsWith('custom:')
}

export function customProviderUuid(p) {
  return isCustomProvider(p) ? p.slice('custom:'.length) : null
}
```

`loadProviderConfig(saved)` 完整替换为：

```js
function loadProviderConfig(saved) {
  const s = saved && typeof saved === 'object' ? saved : {}
  if (s.provider !== undefined || s.apiKey !== undefined || s.customBaseUrl !== undefined) {
    const out = {
      provider: typeof s.provider === 'string' && s.provider ? s.provider : DEFAULT_PROVIDER,
      apiKey: typeof s.apiKey === 'string' ? s.apiKey : '',
      model: typeof s.model === 'string' ? s.model : DEFAULT_MODEL,
    }
    // 一次性迁移: 旧 customBaseUrl → customProviders[id=default]
    if (typeof s.customBaseUrl === 'string' && s.customBaseUrl) {
      const cps = useCustomProvidersStore()
      cps.add({
        id: 'default',
        name: '自定义',
        baseUrl: s.customBaseUrl,
        apiKey: out.provider === 'custom' ? out.apiKey : '',
        protocol: 'openai',
      })
      if (out.provider === 'custom') {
        out.provider = 'custom:default'
        out.apiKey = ''   // 已挪到 customProviders[default].apiKey
      }
    }
    return out
  }
  return {
    provider: loadLegacyStr(LEGACY_KEY_PROVIDER) || DEFAULT_PROVIDER,
    apiKey: loadLegacyStr(LEGACY_KEY_APIKEY),
    model: DEFAULT_MODEL,
  }
}
```

去掉 `customBaseUrl` ref + setter（迁移后已不需要）：

```js
// 删除: const customBaseUrl = ref(providerCfg.customBaseUrl)
// 删除: function setCustomBaseUrl(url) { ... }
```

`providerMeta()` / `getBaseUrl()` 替换为：

```js
function providerMeta() {
  if (isCustomProvider(provider.value)) {
    const uuid = customProviderUuid(provider.value)
    const cp = useCustomProvidersStore().get(uuid)
    return cp
      ? { id: provider.value, label: cp.name, baseUrl: cp.baseUrl,
          protocol: cp.protocol || 'openai', iconKey: 'custom',
          fallbackModels: cp.models || [] }
      : PROVIDERS[0]
  }
  return PROVIDERS.find((p) => p.id === provider.value) || PROVIDERS[0]
}

function getBaseUrl() { return providerMeta().baseUrl || '' }
```

`persist()` 同步改：

```js
function persist() {
  saveState({
    providerConfig: {
      provider: provider.value,
      apiKey: apiKey.value,
      model: model.value,
    },
    proxy: proxy.value,
    toolPermissions: toolPermissions.value,
    memories: memories.value,
    reasoningMode: reasoningMode.value,
  })
}
```

`apiKey` 当 `provider.value` 是 `custom:<uuid>` 时，setApiKey 写到对应 customProvider：

```js
async function setApiKey(key) {
  apiKey.value = key
  if (isCustomProvider(provider.value)) {
    const uuid = customProviderUuid(provider.value)
    useCustomProvidersStore().update(uuid, { apiKey: key })
  }
  persist()
  await fetchModels()
  persist()
}
```

切换到 `custom:<uuid>` 时 apiKey 从对应 entry 加载：

```js
async function setProvider(pid) {
  provider.value = pid
  if (isCustomProvider(pid)) {
    const cp = useCustomProvidersStore().get(customProviderUuid(pid))
    apiKey.value = cp?.apiKey || ''
  }
  persist()
  await fetchModels()
  persist()
}
```

最后 return 里删除 `customBaseUrl` / `setCustomBaseUrl`，加 `isCustomProvider` / `customProviderUuid`（仅 store 外辅助；如不希望污染可保留只在文件内导出）。

- [ ] **Step 4: 跑测验证通过**

Run: `cd frontend && npx vitest run src/__tests__/ai-settings-store.test.js`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/stores/aiSettings.js frontend/src/__tests__/ai-settings-store.test.js
git commit -m "feat(aiSettings): provider 值域支持 custom:<uuid> + 迁移旧 customBaseUrl"
```

---

### Task 4: 后端 /models 支持 protocol 字段（Anthropic 短路）

**Files:**
- Modify: `backend/app/api/chat.py`（ModelsRequest + list_models + ANTHROPIC_MODELS 常量）
- Modify: `frontend/src/stores/aiSettings.js:201`（fetchModels body 加 protocol）
- Test: `backend/tests/test_chat_models_api.py`（新增）

- [ ] **Step 1: 写后端失败测试**

`backend/tests/test_chat_models_api.py`:

```python
"""场景: /api/chat/models — protocol=openai 走 AsyncOpenAI; protocol=anthropic 返回硬编码列表。"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, MagicMock

from app.main import app

client = TestClient(app)


def test_models_anthropic_short_circuits_returns_hardcoded():
    resp = client.post("/api/chat/models", json={
        "base_url": "https://api.anthropic.com", "api_key": "sk-X", "protocol": "anthropic",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert "claude-fable-5" in body["models"]
    assert "claude-opus-4-8" in body["models"]


def test_models_openai_calls_async_client():
    mock_resp = MagicMock()
    mock_resp.data = [MagicMock(id='deepseek-v4-pro'), MagicMock(id='deepseek-v3')]
    fake_client = MagicMock()
    fake_client.models.list = AsyncMock(return_value=mock_resp)
    with patch("app.api.chat._get_async_client", return_value=fake_client):
        resp = client.post("/api/chat/models", json={
            "base_url": "https://api.deepseek.com/v1", "api_key": "sk-X", "protocol": "openai",
        })
    assert resp.status_code == 200
    assert resp.json() == {"models": ["deepseek-v4-pro", "deepseek-v3"]}


def test_models_defaults_protocol_to_openai_when_omitted():
    fake_client = MagicMock()
    fake_client.models.list = AsyncMock(return_value=MagicMock(data=[]))
    with patch("app.api.chat._get_async_client", return_value=fake_client):
        resp = client.post("/api/chat/models", json={"base_url": "x", "api_key": "y"})
    assert resp.status_code == 200
    assert "models" in resp.json()
```

- [ ] **Step 2: 跑测验证失败**

Run: `cd backend && pytest tests/test_chat_models_api.py -v`
Expected: FAIL（ModelsRequest 不识别 protocol，且无 Anthropic 短路逻辑）

- [ ] **Step 3: 改 chat.py**

`backend/app/api/chat.py:48-50` 替换 ModelsRequest：

```python
class ModelsRequest(BaseModel):
    base_url: str = Field(..., description="API Base URL (如 https://api.deepseek.com/v1)")
    api_key: str = Field(..., description="API Key")
    protocol: str = Field('openai', description="协议: openai | anthropic")
```

文件顶部加常量（紧跟 `router = APIRouter()` 后）：

```python
# Anthropic 无 /models 端点, 硬编码列表 (按需更新)
ANTHROPIC_MODELS = [
    'claude-fable-5', 'claude-opus-4-8', 'claude-sonnet-4-6',
    'claude-haiku-4-5', 'claude-opus-4-7', 'claude-sonnet-4',
]
```

`@router.post("/models")` 替换：

```python
@router.post("/models")
async def list_models(req: ModelsRequest):
    """拉取厂商模型列表 (OpenAI 兼容 /models 端点 / Anthropic 硬编码)。"""
    if req.protocol == 'anthropic':
        return {"models": list(ANTHROPIC_MODELS)}
    try:
        client = _get_async_client(req.base_url, req.api_key)
        resp = await client.models.list()
        ids = [m.id for m in resp.data] if hasattr(resp, 'data') else []
        return {"models": ids}
    except Exception as exc:
        return {"error": str(exc)}
```

- [ ] **Step 4: 跑后端测验证通过**

Run: `cd backend && pytest tests/test_chat_models_api.py -v`
Expected: PASS（3 cases）

- [ ] **Step 5: 前端 fetchModels body 加 protocol**

`frontend/src/stores/aiSettings.js:201` 替换：

```js
const meta = providerMeta()
const res = await window.api.http.request('POST', '/api/chat/models', {
  base_url: base, api_key: key, protocol: meta.protocol || 'openai',
})
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/chat.py backend/tests/test_chat_models_api.py frontend/src/stores/aiSettings.js
git commit -m "feat(chat): /models 加 protocol 字段 — Anthropic 短路返回硬编码列表"
```

---

## PR-2 模型能力 metadata + reasoning UI

### Task 5: modelCapabilities 静态表 + capabilityOf

**Files:**
- Create: `frontend/src/services/llm/modelCapabilities.js`
- Test: `frontend/src/__tests__/modelCapabilities.test.js`

- [ ] **Step 1: 写失败测试**

`frontend/src/__tests__/modelCapabilities.test.js`:

```js
import { describe, it, expect } from 'vitest'
import { capabilityOf, formatContext } from '@/services/llm/modelCapabilities'

describe('capabilityOf', () => {
  it.each([
    ['openai',    'o1',                  'native',      128_000],
    ['openai',    'o3-mini',             'native',      128_000],
    ['openai',    'gpt-4.1',             'prompt-only', 1_000_000],
    ['openai',    'gpt-4o',              'prompt-only', 128_000],
    ['deepseek',  'deepseek-v4-pro',     'native',      128_000],
    ['deepseek',  'deepseek-reasoner',   'native',      64_000],
    ['deepseek',  'deepseek-v3',         'prompt-only', null],
    ['anthropic', 'claude-fable-5',      'native',      200_000],
    ['anthropic', 'claude-opus-4-8',     'native',      200_000],
    ['qwen',      'qwen-max',            'prompt-only', 128_000],
    ['gemini',    'gemini-2.5-pro',      'native',      1_000_000],
  ])('%s/%s -> reasoning=%s context=%s', (provider, model, reasoning, context) => {
    const cap = capabilityOf(provider, model)
    expect(cap.reasoning).toBe(reasoning)
    expect(cap.context).toBe(context)
  })

  it('falls back to prompt-only/null for unknown provider+model', () => {
    expect(capabilityOf('unknown', 'foo-bar')).toEqual({ reasoning: 'prompt-only', context: null })
  })

  it('custom:<uuid> falls back to prompt-only', () => {
    expect(capabilityOf('custom:default', 'whatever-7b').reasoning).toBe('prompt-only')
  })

  it('formatContext renders 1M / 128K / null', () => {
    expect(formatContext(1_000_000)).toBe('1M')
    expect(formatContext(128_000)).toBe('128K')
    expect(formatContext(null)).toBe('')
  })
})
```

- [ ] **Step 2: 跑测验证失败**

Run: `cd frontend && npx vitest run src/__tests__/modelCapabilities.test.js`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现**

`frontend/src/services/llm/modelCapabilities.js`:

```js
/**
 * 模型能力静态表 — 按 provider × modelPattern 匹配。
 * 字段:
 *   reasoning: 'native' = 支持原生 thinking/reasoning_effort 参数
 *              'prompt-only' = 仅靠提示词代偿
 *   context: 上下文窗口 token 数; null = 未知
 *
 * vision 不在此表 — 走运行时探测 (modelVision store)。
 */
const CAPABILITY_TABLE = [
  // OpenAI
  { provider: 'openai', modelPattern: /^o(1|3)/,       reasoning: 'native',      context: 128_000 },
  { provider: 'openai', modelPattern: /^gpt-4\.1/,     reasoning: 'prompt-only', context: 1_000_000 },
  { provider: 'openai', modelPattern: /^gpt-4o/,       reasoning: 'prompt-only', context: 128_000 },

  // DeepSeek
  { provider: 'deepseek', modelPattern: /^deepseek-v4/,       reasoning: 'native', context: 128_000 },
  { provider: 'deepseek', modelPattern: /^deepseek-reasoner/, reasoning: 'native', context:  64_000 },

  // Anthropic
  { provider: 'anthropic', modelPattern: /^claude-(opus|sonnet|haiku|fable|mythos)-(4|5)/,
    reasoning: 'native', context: 200_000 },

  // Qwen
  { provider: 'qwen', modelPattern: /^qwen-/, reasoning: 'prompt-only', context: 128_000 },

  // Gemini
  { provider: 'gemini', modelPattern: /^gemini-2\.5/, reasoning: 'native', context: 1_000_000 },
]

const DEFAULT_CAP = Object.freeze({ reasoning: 'prompt-only', context: null })

export function capabilityOf(provider, model) {
  const p = (provider || '').toLowerCase()
  // custom:<uuid> 走兜底
  const pid = p.startsWith('custom') ? 'custom' : p
  const m = model || ''
  for (const row of CAPABILITY_TABLE) {
    if (row.provider !== pid) continue
    if (row.modelPattern.test(m)) {
      return { reasoning: row.reasoning, context: row.context }
    }
  }
  return { ...DEFAULT_CAP }
}

export function formatContext(n) {
  if (!n) return ''
  if (n >= 1_000_000) return `${Math.round(n / 1_000_000)}M`
  if (n >= 1_000) return `${Math.round(n / 1_000)}K`
  return String(n)
}
```

- [ ] **Step 4: 跑测验证通过**

Run: `cd frontend && npx vitest run src/__tests__/modelCapabilities.test.js`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/services/llm/modelCapabilities.js frontend/src/__tests__/modelCapabilities.test.js
git commit -m "feat(llm): modelCapabilities 静态表 — provider×modelPattern 推 reasoning/context"
```

---

### Task 6: aiSettings.modelReasoningSupport 委托 capabilityOf + 收敛为两态

**Files:**
- Modify: `frontend/src/stores/aiSettings.js:278-299`（modelReasoningSupport / reasoningInstruction）
- Modify: `frontend/src/__tests__/ai-settings-store.test.js:99`（Claude 旧断言改为 `'native'`）

⚠️ 这是破坏性变更：旧四态 → 两态 `native | prompt-only`。同期 PR-3 把 Anthropic 协议接通后此态就够用。

- [ ] **Step 1: 改测试（先把旧断言改成新预期，跑应红）**

`ai-settings-store.test.js:99` 一行原值 `'native-when-supported-by-backend'` 改为 `'native'`：

```js
expect(settings.modelReasoningSupport('custom', 'claude-opus-4-8')).toBe('native')
```

再追加一段新 describe（保留既有不删）：

```js
describe('modelReasoningSupport 委托 capabilityOf（Spec A 收敛为两态）', () => {
  beforeEach(() => { setActivePinia(createPinia()); localStorage.clear() })

  it('返回 native | prompt-only 两态', () => {
    const s = useAiSettingsStore()
    expect(s.modelReasoningSupport('anthropic', 'claude-fable-5')).toBe('native')
    expect(s.modelReasoningSupport('anthropic', 'claude-opus-4-8')).toBe('native')
    expect(s.modelReasoningSupport('openai', 'gpt-4o')).toBe('prompt-only')
    expect(s.modelReasoningSupport('openai', 'o1')).toBe('native')
    expect(s.modelReasoningSupport('foo', 'bar')).toBe('prompt-only')   // 旧 'unknown' 收敛
  })
})
```

- [ ] **Step 2: 跑测验证失败**

Run: `cd frontend && npx vitest run src/__tests__/ai-settings-store.test.js`
Expected: FAIL（仍是旧四态逻辑）

- [ ] **Step 3: 改实现**

`frontend/src/stores/aiSettings.js` 顶部 import：

```js
import { capabilityOf } from '@/services/llm/modelCapabilities'
```

`modelReasoningSupport` / `reasoningInstruction` 完整替换为：

```js
function modelReasoningSupport(provider, model) {
  // capabilityOf 接受 'custom:<uuid>' 形态; 直接透传
  return capabilityOf(provider, model).reasoning   // 'native' | 'prompt-only'
}

function reasoningInstruction(provider, model) {
  if (reasoningMode.value === REASONING_MODE.FAST) {
    return '思考模式: 快速。请直接给出简洁实用的回答，不展开冗长推理。'
  }
  if (reasoningMode.value === REASONING_MODE.DEEP) {
    const support = modelReasoningSupport(provider, model)
    if (support === 'native') return '思考模式: 深度。当前模型支持 reasoning，请进行更充分的分析，并在最终回答中保持结论清晰。'
    return '思考模式: 深度。当前模型未确认支持原生 thinking 参数，请更仔细地分析问题，先内部推理，再给出简洁结论。'
  }
  return ''
}
```

- [ ] **Step 4: 跑测验证通过**

Run: `cd frontend && npx vitest run src/__tests__/ai-settings-store.test.js`
Expected: PASS（含原有 cases）

- [ ] **Step 5: Commit**

```bash
git add frontend/src/stores/aiSettings.js frontend/src/__tests__/ai-settings-store.test.js
git commit -m "refactor(aiSettings): modelReasoningSupport 委托 capabilityOf — 四态收敛为 native|prompt-only"
```

---

### Task 7: 后端 ChatRequest reasoning_mode + protocol + _build_request_extras

**Files:**
- Modify: `backend/app/api/chat.py`（ChatRequest / _build_extra_body → _build_request_extras / chat_completions 入口）
- Test: `backend/tests/test_chat_build_request_extras.py`（新增）

⚠️ 本任务先**只改后端**；前端 chat.js body 改在 Task 8 一起跟。本任务后字段已对接，但前端仍发旧 `reasoning` → Pydantic ignore，行为退化为 `reasoning_mode='auto'`（可接受）。

- [ ] **Step 1: 写失败测试**

`backend/tests/test_chat_build_request_extras.py`:

```python
"""场景: _build_request_extras — protocol × model × reasoning_mode 九宫格。"""
import pytest
from app.api.chat import _build_request_extras


@pytest.mark.parametrize("protocol,model,mode,expect", [
    # DeepSeek-V4 走 extra_body.thinking
    ('openai', 'deepseek-v4-pro', 'auto', {'extra_body': {'thinking': {'type': 'enabled'}}}),
    ('openai', 'deepseek-v4-pro', 'deep', {'extra_body': {'thinking': {'type': 'enabled'}}}),
    ('openai', 'deepseek-v4-pro', 'fast', {'extra_body': {'thinking': {'type': 'disabled'}}}),

    # Anthropic claude-fable-5
    ('anthropic', 'claude-fable-5', 'auto', {}),
    ('anthropic', 'claude-fable-5', 'deep', {'thinking': {'type': 'enabled', 'budget_tokens': 8000}}),
    ('anthropic', 'claude-fable-5', 'fast', {'thinking': {'type': 'disabled'}}),

    # OpenAI o1/o3
    ('openai', 'o1', 'auto', {'reasoning_effort': 'medium'}),
    ('openai', 'o3-mini', 'deep', {'reasoning_effort': 'high'}),
    ('openai', 'o1', 'fast', {'reasoning_effort': 'low'}),

    # 其他模型: 不传 extras
    ('openai', 'gpt-4o', 'deep', {}),
    ('openai', 'gpt-4o', 'fast', {}),
])
def test_build_request_extras(protocol, model, mode, expect):
    assert _build_request_extras(protocol, model, mode) == expect
```

- [ ] **Step 2: 跑测验证失败**

Run: `cd backend && pytest tests/test_chat_build_request_extras.py -v`
Expected: FAIL（函数不存在）

- [ ] **Step 3: 改 chat.py**

`backend/app/api/chat.py` 顶部 import 加 `import re` 和 `from typing import Literal`。

ChatRequest 完整替换为：

```python
class ChatRequest(BaseModel):
    messages: list[dict] = Field(..., min_length=1, description="对话消息数组")
    stream: bool = Field(True, description="是否 SSE 流式返回")
    max_tokens: int = Field(4096, ge=1, le=32768)
    model: str | None = Field(None)
    api_key: str | None = Field(None)
    base_url: str | None = Field(None)
    protocol: Literal['openai', 'anthropic'] = Field('openai', description="协议分支")
    reasoning_mode: Literal['auto', 'fast', 'deep'] = Field(
        'auto',
        description="思考模式: auto=模型默认 / fast=关思考秒回 / deep=充分思考",
    )
```

把 `_is_deepseek_thinking_model` 改名 `_is_thinking_extra_body_model`（语义更准），并新增 `_is_anthropic_reasoning_model`：

```python
def _is_thinking_extra_body_model(model: str) -> bool:
    """走 extra_body.thinking 的模型 — DeepSeek-V4 / 后续 thinking 系列。"""
    m = (model or "").lower()
    return m.startswith("deepseek-v4") or m == "deepseek-reasoner-pro"


def _is_anthropic_reasoning_model(model: str) -> bool:
    """Anthropic Claude 4+ 支持 thinking param。"""
    m = (model or "").lower()
    return bool(re.match(r'^claude-(opus|sonnet|haiku|fable|mythos)-(4|5)', m))
```

`_build_extra_body` 整体替换为新签名 `_build_request_extras`：

```python
def _build_request_extras(protocol: str, model: str, reasoning_mode: str) -> dict:
    """
    构造厂商特定的额外 kwargs (不含 messages/model/stream/max_tokens).
    reasoning_mode: 'auto' | 'fast' | 'deep'
    返回 kwargs 字典 — 调用方直接 kwargs.update(extras)。
    """
    # DeepSeek-V4 系列 + xiaomi MiMo 等: extra_body.thinking
    if protocol == 'openai' and _is_thinking_extra_body_model(model):
        thinking = 'disabled' if reasoning_mode == 'fast' else 'enabled'
        return {'extra_body': {'thinking': {'type': thinking}}}

    # Anthropic Claude 4+: thinking param
    if protocol == 'anthropic' and _is_anthropic_reasoning_model(model):
        if reasoning_mode == 'deep':
            return {'thinking': {'type': 'enabled', 'budget_tokens': 8000}}
        if reasoning_mode == 'fast':
            return {'thinking': {'type': 'disabled'}}
        return {}

    # OpenAI o1/o3: reasoning_effort
    if protocol == 'openai' and re.match(r'^o[13]', (model or '').lower()):
        if reasoning_mode == 'deep': return {'reasoning_effort': 'high'}
        if reasoning_mode == 'fast': return {'reasoning_effort': 'low'}
        return {'reasoning_effort': 'medium'}

    return {}
```

`chat_completions` 入口 `extra_body = _build_extra_body(model, req.reasoning)` 改为：

```python
extras = _build_request_extras(req.protocol, model, req.reasoning_mode)
```

并把 `_stream_chat` 调用签名、非流式 fallback 中 `kwargs["extra_body"] = extra_body` 的逻辑统一改为：

```python
kwargs.update(extras)   # extras 自带 extra_body / thinking / reasoning_effort 键
```

最后把 `_stream_chat(..., extra_body=extras)` 调用一起改为 `_stream_chat(..., extras=extras)`，函数内部也改名 + 改 update：

```python
async def _stream_chat(client, messages, max_tokens, model, extras=None):
    try:
        kwargs = dict(model=model, messages=messages, stream=True,
                      max_tokens=max_tokens, temperature=0.7)
        if extras: kwargs.update(extras)
        stream = await client.chat.completions.create(**kwargs)
        ...
```

- [ ] **Step 4: 跑测验证通过**

Run: `cd backend && pytest tests/test_chat_build_request_extras.py tests/test_chat_models_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/chat.py backend/tests/test_chat_build_request_extras.py
git commit -m "feat(chat): ChatRequest reasoning_mode + protocol + _build_request_extras 三态扩展"
```

---

### Task 8: 前端 body 改为 reasoning_mode + protocol + 删 _reasoningForRequest

**Files:**
- Modify: `frontend/src/stores/chat.js:281-288, 363-382`
- Modify: `frontend/src/__tests__/chat-ai-settings.test.js`（新增字段断言）

- [ ] **Step 1: 加失败测试**

在 `chat-ai-settings.test.js` 文件末尾追加（注意：现有该文件只测 helper，没有 store 实例化，故新增独立 describe + 自带 pinia setup）：

```js
import { setActivePinia, createPinia } from 'pinia'
import { beforeEach, vi } from 'vitest'

describe('chat body: reasoning_mode + protocol (Spec A)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.resetModules()
  })

  it('streamChat 调用 body 含 reasoning_mode + protocol, 不再含 reasoning 字段', async () => {
    const captured = { body: null }
    vi.doMock('@/ide/chat/stream', () => ({
      streamChat: async ({ body }) => { captured.body = body },
    }))
    const { useChatStore } = await import('@/stores/chat')
    const { useAiSettingsStore } = await import('@/stores/aiSettings')
    const ai = useAiSettingsStore()
    ai.provider = 'anthropic'
    ai.apiKey = 'sk-X'
    ai.model = 'claude-fable-5'
    ai.setReasoningMode('deep')
    const chat = useChatStore()
    await chat.sendMessage('hi')
    expect(captured.body.reasoning_mode).toBe('deep')
    expect(captured.body.protocol).toBe('anthropic')
    expect(captured.body).not.toHaveProperty('reasoning')
  })
})
```

- [ ] **Step 2: 跑测验证失败**

Run: `cd frontend && npx vitest run src/__tests__/chat-ai-settings.test.js -t "reasoning_mode + protocol"`
Expected: FAIL（body 仍含旧 reasoning 或不含 protocol）

- [ ] **Step 3: 改 chat.js**

删除 `_reasoningForRequest` 函数（`chat.js:281-288`）。

`_streamResponse`（`chat.js:363-382`）body 构造段替换为：

```js
async function _streamResponse(apiMessages, assistantMsg) {
  const ai = useAiSettingsStore()
  const body = {
    messages: apiMessages,
    stream: true,
    max_tokens: 8192,
    model: ai.model,
    api_key: ai.apiKey || undefined,
    base_url: ai.getBaseUrl() || undefined,
    protocol: ai.providerMeta().protocol || 'openai',
    reasoning_mode: ai.reasoningMode,
  }
  await streamChat({
    body,
    signal: abortController.value.signal,
    onBlock: (block) => _applySseBlock(block, assistantMsg),
  })
}
```

- [ ] **Step 4: 跑测验证通过**

Run: `cd frontend && npx vitest run src/__tests__/chat-ai-settings.test.js`
Expected: PASS（含既有）

- [ ] **Step 5: Commit**

```bash
git add frontend/src/stores/chat.js frontend/src/__tests__/chat-ai-settings.test.js
git commit -m "feat(chat): body 字段 reasoning_mode + protocol, 删 _reasoningForRequest"
```

---

### Task 9: reasoning radio 三态 UI + 不支持时灰提示 + 自动降级

**Files:**
- Modify: `frontend/src/ide/AssistantPanel.vue`（工具栏 reasoning-group + computed deepDisabled）
- Modify: `frontend/src/stores/aiSettings.js`（watch 自动降级到 auto）
- Test: `frontend/src/__tests__/ai-settings-store.test.js`（追加自动降级 case）

- [ ] **Step 1: 加失败测试**

在 `ai-settings-store.test.js` 末尾追加：

```js
describe('reasoningMode auto-downgrade (Spec A)', () => {
  beforeEach(() => { setActivePinia(createPinia()); localStorage.clear() })

  it('deep 模式下切到 prompt-only 模型 -> 自动降级为 auto', async () => {
    const s = useAiSettingsStore()
    s.provider = 'anthropic'
    s.model = 'claude-fable-5'
    s.setReasoningMode('deep')
    expect(s.reasoningMode).toBe('deep')

    s.provider = 'openai'
    s.model = 'gpt-4o'        // prompt-only 模型
    await new Promise(r => setTimeout(r, 0))   // watch flush
    expect(s.reasoningMode).toBe('auto')
  })

  it('fast 不被降级', async () => {
    const s = useAiSettingsStore()
    s.setReasoningMode('fast')
    s.provider = 'openai'
    s.model = 'gpt-4o'
    await new Promise(r => setTimeout(r, 0))
    expect(s.reasoningMode).toBe('fast')
  })
})
```

- [ ] **Step 2: 跑测验证失败**

Run: `cd frontend && npx vitest run src/__tests__/ai-settings-store.test.js -t "auto-downgrade"`
Expected: FAIL

- [ ] **Step 3: 在 aiSettings 加 watch**

`frontend/src/stores/aiSettings.js` 顶部加 `import { watch } from 'vue'`。

在 store setup 末尾（`fetchModels()` 调用之前）加：

```js
// reasoningMode='deep' + 当前模型 prompt-only -> 自动降级到 auto
watch(
  [() => provider.value, () => model.value, reasoningMode],
  () => {
    if (reasoningMode.value !== 'deep') return
    if (capabilityOf(provider.value, model.value).reasoning !== 'native') {
      reasoningMode.value = 'auto'
      persist()
    }
  },
  { flush: 'sync' },
)
```

- [ ] **Step 4: 跑测验证通过**

Run: `cd frontend && npx vitest run src/__tests__/ai-settings-store.test.js`
Expected: PASS

- [ ] **Step 5: 加 UI radio（AssistantPanel.vue）**

[AssistantPanel.vue:286-328](../../../frontend/src/ide/AssistantPanel.vue#L286) 工具栏在导学按钮（结束 `</el-tooltip>`）后、模型 hint 前插入：

```vue
<el-radio-group
  :model-value="aiSettings.reasoningMode"
  size="small"
  class="reasoning-group"
  :disabled="chat.streaming"
  @change="aiSettings.setReasoningMode"
>
  <el-radio-button label="auto" title="自动 — 由模型默认决定">🤖</el-radio-button>
  <el-radio-button label="fast" title="快速 — 不思考直接回答">⚡</el-radio-button>
  <el-radio-button
    label="deep"
    :disabled="deepDisabled"
    :title="deepDisabled ? deepDisabledTooltip : '深度 — 充分思考'"
  >🧠</el-radio-button>
</el-radio-group>
```

`<script setup>` 顶部加：

```js
import { computed } from 'vue'
import { capabilityOf } from '@/services/llm/modelCapabilities'

const deepDisabled = computed(() =>
  capabilityOf(aiSettings.provider, aiSettings.model).reasoning !== 'native')

const deepDisabledTooltip = computed(() =>
  `当前模型 (${aiSettings.model}) 不支持原生推理；如需思考请用「快速/自动」+ 提示词`)
```

CSS（`<style scoped>` 末尾追加）：

```css
.reasoning-group { margin-right: 6px; }
.reasoning-group .el-radio-button__inner { padding: 4px 8px; font-size: 13px; }
.reasoning-group .is-disabled .el-radio-button__inner {
  opacity: 0.45;
  cursor: not-allowed;
}
```

- [ ] **Step 6: 手测 reasoning UI**

```bash
npm run dev
```

- 切 deepseek-v3（prompt-only）→ 🧠 灰
- 切 deepseek-v4-pro → 🧠 可点；点击后切 gpt-4o → 自动降回 auto
- 切到 deep + 发消息：DevTools Network 看 body 含 `reasoning_mode: "deep"`

- [ ] **Step 7: Commit**

```bash
git add frontend/src/stores/aiSettings.js frontend/src/ide/AssistantPanel.vue frontend/src/__tests__/ai-settings-store.test.js
git commit -m "feat(assistant): reasoning radio 三态 + 不支持模型 deep 灰 + 自动降级到 auto"
```

---

## PR-3 Anthropic 原生协议

### Task 10: 安装 anthropic 包 + 后端 client 缓存

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/app/api/chat.py`（_get_anthropic_client + _resolve_client 拆双）

- [ ] **Step 1: requirements.txt 加 anthropic**

`backend/requirements.txt` 在 `openai` 行下方插入：

```
anthropic>=0.40.0
```

- [ ] **Step 2: 安装**

```bash
cd backend && pip install -r requirements.txt
```

Expected: anthropic + 依赖装好；`python -c "from anthropic import AsyncAnthropic; print(AsyncAnthropic)"` 不报错。

- [ ] **Step 3: 加 _get_anthropic_client + 拆 _resolve_client**

`backend/app/api/chat.py` 顶部 import 区加：

```python
from anthropic import AsyncAnthropic
```

`_get_async_client` 下方加：

```python
@lru_cache(maxsize=16)
def _get_anthropic_client(api_key: str) -> AsyncAnthropic:
    """缓存 AsyncAnthropic client (key 唯一索引)"""
    return AsyncAnthropic(api_key=api_key)
```

`_resolve_client(req)` 拆为两个：

```python
def _resolve_openai_client(req: ChatRequest) -> AsyncOpenAI | None:
    if req.api_key:
        base = req.base_url or settings.LLM_BASE_URL
        return _get_async_client(base, req.api_key)
    if settings.LLM_API_KEY and settings.LLM_API_KEY != "sk-placeholder":
        return _get_async_client(settings.LLM_BASE_URL, settings.LLM_API_KEY)
    return None


def _resolve_anthropic_client(req: ChatRequest) -> AsyncAnthropic | None:
    if req.api_key:
        return _get_anthropic_client(req.api_key)
    return None   # 服务端默认 key 是 OpenAI 兼容, 不复用


def _resolve_client(req: ChatRequest):
    """根据 protocol 分派 client; 返回 (client, protocol)。None 表示未配置。"""
    if req.protocol == 'anthropic':
        return _resolve_anthropic_client(req), 'anthropic'
    return _resolve_openai_client(req), 'openai'
```

- [ ] **Step 4: Commit**

```bash
git add backend/requirements.txt backend/app/api/chat.py
git commit -m "feat(chat): 引入 anthropic SDK + _get_anthropic_client 缓存 + _resolve_client 双协议派发"
```

---

### Task 11: _openai_msg_to_anthropic + _split_system 转换函数

**Files:**
- Modify: `backend/app/api/chat.py`（新增两个 helper）
- Test: `backend/tests/test_chat_openai_to_anthropic_msg.py`（新增）

- [ ] **Step 1: 写失败测试**

`backend/tests/test_chat_openai_to_anthropic_msg.py`:

```python
"""场景: OpenAI 消息形式 → Anthropic messages.create 参数。

输入是前端发的 OpenAI 风格 messages, 含可能的多模态 content 数组、system 消息;
输出是 Anthropic SDK 要的 (system_text, [{role, content: parts}])。
"""
from app.api.chat import _split_system, _openai_msg_to_anthropic


def test_split_system_concatenates_multiple_system_messages():
    msgs = [
        {"role": "system", "content": "S1"},
        {"role": "user", "content": "U1"},
        {"role": "system", "content": "S2"},
        {"role": "assistant", "content": "A1"},
    ]
    system, ua = _split_system(msgs)
    assert system == "S1\n\nS2"
    assert [m["role"] for m in ua] == ["user", "assistant"]


def test_openai_msg_text_only_passthrough():
    out = _openai_msg_to_anthropic({"role": "user", "content": "hello"})
    assert out == {"role": "user", "content": "hello"}


def test_openai_msg_multimodal_data_url_image():
    msg = {"role": "user", "content": [
        {"type": "text", "text": "what is this?"},
        {"type": "image_url",
         "image_url": {"url": "data:image/png;base64,AAAA"}},
    ]}
    out = _openai_msg_to_anthropic(msg)
    assert out["role"] == "user"
    assert out["content"][0] == {"type": "text", "text": "what is this?"}
    assert out["content"][1] == {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": "AAAA"},
    }


def test_openai_msg_multimodal_url_image():
    msg = {"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": "https://example.com/x.png"}},
    ]}
    out = _openai_msg_to_anthropic(msg)
    assert out["content"][0] == {
        "type": "image",
        "source": {"type": "url", "url": "https://example.com/x.png"},
    }
```

- [ ] **Step 2: 跑测验证失败**

Run: `cd backend && pytest tests/test_chat_openai_to_anthropic_msg.py -v`
Expected: FAIL（函数不存在）

- [ ] **Step 3: 实现两个函数**

`backend/app/api/chat.py` 在 `_get_anthropic_client` 下方加：

```python
def _split_system(messages: list[dict]) -> tuple[str, list[dict]]:
    """把 system 消息抽出来拼成字符串 (Anthropic 的 system 是顶层 param);
    其余按原顺序返回。多个 system 消息以两个换行连接。"""
    sys_parts = [
        m["content"] for m in messages
        if m.get("role") == "system" and isinstance(m.get("content"), str)
    ]
    ua = [m for m in messages if m.get("role") != "system"]
    return ("\n\n".join(sys_parts), ua)


def _openai_msg_to_anthropic(msg: dict) -> dict:
    """OpenAI 风格 message → Anthropic 风格。

    - content 是 string: 原样回
    - content 是 OpenAI 多模态数组:
        - text 段: {type: 'text', text: ...}
        - image_url 段:
            url 以 data: 开头 → {type: image, source: {type: base64, media_type, data}}
            否则 → {type: image, source: {type: url, url}}
    """
    content = msg.get("content")
    if isinstance(content, str):
        return {"role": msg["role"], "content": content}
    parts = []
    for p in content or []:
        ptype = p.get("type")
        if ptype == "text":
            parts.append({"type": "text", "text": p.get("text", "")})
        elif ptype == "image_url":
            url = (p.get("image_url") or {}).get("url", "")
            if url.startswith("data:"):
                header, b64 = url.split(",", 1)
                media_type = header.split(";")[0].split(":")[1]
                parts.append({"type": "image",
                              "source": {"type": "base64",
                                         "media_type": media_type, "data": b64}})
            else:
                parts.append({"type": "image",
                              "source": {"type": "url", "url": url}})
    return {"role": msg["role"], "content": parts}
```

- [ ] **Step 4: 跑测验证通过**

Run: `cd backend && pytest tests/test_chat_openai_to_anthropic_msg.py -v`
Expected: PASS（4 cases）

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/chat.py backend/tests/test_chat_openai_to_anthropic_msg.py
git commit -m "feat(chat): _split_system + _openai_msg_to_anthropic 消息形态转换"
```

---

### Task 12: _stream_openai / _stream_anthropic 双 stream + 帧形状一致

**Files:**
- Modify: `backend/app/api/chat.py`（_stream_chat 改名 _stream_openai + 新增 _stream_anthropic + chat_completions 分派）
- Test: `backend/tests/test_chat_anthropic_stream.py`（新增）

⚠️ 两个 stream 函数发**完全相同的 SSE 帧**：`{delta}` / `{reasoning}` / `{error}` / `[DONE]`。前端 chat.js 不感知协议差异。

- [ ] **Step 1: 写失败测试（mock Anthropic stream）**

`backend/tests/test_chat_anthropic_stream.py`:

```python
"""场景: _stream_anthropic 把 Anthropic SDK 事件翻译成统一 SSE 帧。"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.api.chat import _stream_anthropic


class FakeDelta:
    def __init__(self, dtype, **kw):
        self.type = dtype
        for k, v in kw.items():
            setattr(self, k, v)


class FakeEvent:
    def __init__(self, etype, delta=None):
        self.type = etype
        self.delta = delta


class FakeStreamCtx:
    """模拟 client.messages.stream(...) 返回的 async context manager。"""
    def __init__(self, events):
        self._events = events

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def __aiter__(self):
        events = self._events
        async def gen():
            for e in events:
                yield e
        return gen()


@pytest.mark.asyncio
async def test_anthropic_stream_emits_reasoning_then_delta_then_done():
    events = [
        FakeEvent('content_block_delta', delta=FakeDelta('thinking_delta', thinking='思考中…')),
        FakeEvent('content_block_delta', delta=FakeDelta('text_delta', text='答案是 42')),
    ]
    fake_client = MagicMock()
    fake_client.messages.stream = MagicMock(return_value=FakeStreamCtx(events))

    frames = []
    messages = [{"role": "user", "content": "Q"}]
    async for chunk in _stream_anthropic(fake_client, messages, 'claude-fable-5', 1024, {}):
        frames.append(chunk)

    payloads = [json.loads(c.split('data: ', 1)[1].strip())
                for c in frames if 'data:' in c and '[DONE]' not in c]
    assert payloads[0] == {'reasoning': '思考中…'}
    assert payloads[1] == {'delta': '答案是 42'}
    assert frames[-1].strip() == 'data: [DONE]'


@pytest.mark.asyncio
async def test_anthropic_stream_emits_error_on_exception():
    fake_client = MagicMock()
    fake_client.messages.stream = MagicMock(side_effect=RuntimeError('boom'))
    frames = []
    async for chunk in _stream_anthropic(fake_client, [{"role": "user", "content": "Q"}],
                                          'claude-fable-5', 1024, {}):
        frames.append(chunk)
    assert any('"error"' in f and 'boom' in f for f in frames)
```

需要 `pytest-asyncio`；如未装：`pip install pytest-asyncio` 并在 `backend/pytest.ini` 加 `asyncio_mode = auto`。

- [ ] **Step 2: 跑测验证失败**

Run: `cd backend && pytest tests/test_chat_anthropic_stream.py -v`
Expected: FAIL（_stream_anthropic 不存在）

- [ ] **Step 3: 改 chat.py**

把 `_stream_chat` 改名为 `_stream_openai`（同时把 Task 7 的 `extras` 形参保持）：

```python
async def _stream_openai(client, messages, max_tokens, model, extras=None):
    """逐 token 推送 SSE 事件 (OpenAI 兼容协议)。"""
    try:
        kwargs = dict(model=model, messages=messages, stream=True,
                      max_tokens=max_tokens, temperature=0.7)
        if extras: kwargs.update(extras)
        stream = await client.chat.completions.create(**kwargs)
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta:
                data = {}
                if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                    data['reasoning'] = delta.reasoning_content
                if delta.content:
                    data['delta'] = delta.content
                if data:
                    yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as exc:
        yield f"data: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"
```

新增 `_stream_anthropic`：

```python
async def _stream_anthropic(client, messages, model, max_tokens, extras=None):
    """逐 token 推送 SSE 事件 (Anthropic 协议) — 与 _stream_openai 帧形状完全一致。"""
    system_text, ua_msgs = _split_system(messages)
    anthropic_msgs = [_openai_msg_to_anthropic(m) for m in ua_msgs]
    try:
        kwargs = dict(model=model, max_tokens=max_tokens, messages=anthropic_msgs)
        if system_text:
            kwargs['system'] = system_text
        if extras: kwargs.update(extras)
        async with client.messages.stream(**kwargs) as stream:
            async for event in stream:
                if getattr(event, 'type', None) != 'content_block_delta':
                    continue
                d = getattr(event, 'delta', None)
                if d is None:
                    continue
                if d.type == 'thinking_delta':
                    yield f"data: {json.dumps({'reasoning': d.thinking}, ensure_ascii=False)}\n\n"
                elif d.type == 'text_delta':
                    yield f"data: {json.dumps({'delta': d.text}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as exc:
        yield f"data: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"
```

`chat_completions` 改派发：

```python
@router.post("/completions")
async def chat_completions(req: ChatRequest, request: Request):
    model = req.model or settings.LLM_MODEL
    client, protocol = _resolve_client(req)

    if client is None:
        detail = "LLM 未配置（请设置 API Key）"
        if req.stream:
            return StreamingResponse(
                iter([f"data: {json.dumps({'error': detail}, ensure_ascii=False)}\n\n"]),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache"},
            )
        return {"error": detail}

    extras = _build_request_extras(protocol, model, req.reasoning_mode)

    if req.stream:
        if protocol == 'anthropic':
            gen = _stream_anthropic(client, req.messages, model, req.max_tokens, extras)
        else:
            gen = _stream_openai(client, req.messages, req.max_tokens, model, extras)
        return StreamingResponse(
            gen, media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive",
                     "X-Accel-Buffering": "no"},
        )

    # 非流式 fallback — 本期只走 OpenAI 路径; Anthropic 非流式留 future
    if protocol == 'anthropic':
        return {"error": "Anthropic 非流式 fallback 本期未实现, 请用 stream=true"}
    try:
        kwargs = dict(model=model, messages=req.messages, stream=False,
                      max_tokens=req.max_tokens, temperature=0.7)
        if extras: kwargs.update(extras)
        completion = await client.chat.completions.create(**kwargs)
        content = completion.choices[0].message.content if completion.choices else ""
        return {"content": content}
    except Exception as exc:
        return {"error": str(exc)}
```

- [ ] **Step 4: 跑测验证通过**

Run: `cd backend && pytest tests/test_chat_anthropic_stream.py tests/test_chat_openai_to_anthropic_msg.py tests/test_chat_build_request_extras.py tests/test_chat_models_api.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/chat.py backend/tests/test_chat_anthropic_stream.py
git commit -m "feat(chat): Anthropic 协议双 stream — _stream_anthropic + _stream_openai 帧形状一致"
```

---

### Task 13: Anthropic 端到端手测（含工具循环）

⚠️ 提示词工具循环（`<tool_call>{json}</tool_call>`）依赖 Claude 对结构化指令的遵循度；本任务做实测验证，若不达标再单独 spec 加 fallback。

- [ ] **Step 1: 用真实 Anthropic key 跑一遍**

确保用户拿到 Anthropic API key + 配代理（国内默认 endpoint 不通）。

```bash
npm run dev
```

- 厂商切到 Anthropic
- 🔑 填入 sk-ant-...，模型选 claude-fable-5
- 输入「请用 read_file 工具读取 backend/app/main.py 然后总结其作用」
- 观察：
  - 模型应输出 `<tool_call>{"tool":"read_file","path":"backend/app/main.py"}</tool_call>`
  - 工具调用结果回喂后，模型给出总结
  - reasoning 模式 deep 时应该有 🧠 灰色思考气泡

- [ ] **Step 2: 用 CDP 探针记录现场（可选）**

```bash
python scripts/cdp_probe.py --once anthropic_smoke
```

- [ ] **Step 3: 写下结果**

在 `docs/devlogs/` 加一条记录（结果 OK / 不达标）。如不达标，新开 issue：「Anthropic 提示词工具循环遵循度低 — 需 fallback」。

- [ ] **Step 4: Commit（仅 devlog）**

```bash
git add docs/devlogs/
git commit -m "docs(devlog): Anthropic 协议端到端验证 — 工具循环遵循度记录"
```

---

## PR-4 Vision 探测 + 持久化缓存

### Task 14: 后端 /probe-vision endpoint + 持久化

**Files:**
- Modify: `backend/app/api/chat.py`（加 TEST_IMG_BASE64 / ProbeVisionRequest / probe_vision / _load_vision_cache / _save_vision_cache / DELETE /probe-vision/cache）
- Test: `backend/tests/test_chat_probe_vision.py`（新增）

cache 文件：`{settings.DATA_DIR}/vision_cache.json`，原子写：`.tmp` → rename。

- [ ] **Step 1: 写失败测试**

`backend/tests/test_chat_probe_vision.py`:

```python
"""场景: /api/chat/probe-vision — 用一张 76x100 的"test vision"图探当前模型是否能 OCR。

cache 命中直接返回; auth 错不写缓存; 普通错写 False 入缓存; DELETE 清空。
"""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolate_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATA_DIR", str(tmp_path))
    cache_path = Path(tmp_path) / "vision_cache.json"
    if cache_path.exists():
        cache_path.unlink()
    yield


def test_probe_vision_cache_hit_skips_call():
    cache_path = Path(settings.DATA_DIR) / "vision_cache.json"
    cache_path.write_text(json.dumps({"https://api.openai.com/v1::gpt-4o": True}))
    resp = client.post("/api/chat/probe-vision", json={
        "base_url": "https://api.openai.com/v1", "api_key": "sk-X",
        "model": "gpt-4o", "protocol": "openai",
    })
    assert resp.status_code == 200
    assert resp.json() == {"vision": True, "cached": True}


def test_probe_vision_openai_extracts_test_vision_and_writes_cache():
    fake_client = MagicMock()
    fake_msg = MagicMock()
    fake_msg.content = "Test vision"
    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=fake_msg)]
    fake_client.chat.completions.create = AsyncMock(return_value=fake_resp)

    with patch("app.api.chat._get_async_client", return_value=fake_client):
        resp = client.post("/api/chat/probe-vision", json={
            "base_url": "https://api.openai.com/v1", "api_key": "sk-X",
            "model": "gpt-4o", "protocol": "openai",
        })
    assert resp.status_code == 200
    assert resp.json() == {"vision": True, "cached": False}
    cache = json.loads((Path(settings.DATA_DIR) / "vision_cache.json").read_text())
    assert cache["https://api.openai.com/v1::gpt-4o"] is True


def test_probe_vision_auth_error_does_not_write_cache():
    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(
        side_effect=Exception("401 Unauthorized: invalid api key"))
    with patch("app.api.chat._get_async_client", return_value=fake_client):
        resp = client.post("/api/chat/probe-vision", json={
            "base_url": "u", "api_key": "bad", "model": "gpt-4o", "protocol": "openai",
        })
    body = resp.json()
    assert body["vision"] is False
    assert body.get("error") == "auth"
    assert not (Path(settings.DATA_DIR) / "vision_cache.json").exists()


def test_probe_vision_non_auth_error_writes_false_to_cache():
    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(side_effect=Exception("500 server error"))
    with patch("app.api.chat._get_async_client", return_value=fake_client):
        resp = client.post("/api/chat/probe-vision", json={
            "base_url": "u", "api_key": "sk-X", "model": "gpt-foo", "protocol": "openai",
        })
    assert resp.json() == {"vision": False, "cached": False}
    cache = json.loads((Path(settings.DATA_DIR) / "vision_cache.json").read_text())
    assert cache["u::gpt-foo"] is False


def test_delete_probe_vision_cache_clears_file():
    (Path(settings.DATA_DIR) / "vision_cache.json").write_text('{"a::b": true}')
    resp = client.delete("/api/chat/probe-vision/cache")
    assert resp.status_code == 200
    assert json.loads((Path(settings.DATA_DIR) / "vision_cache.json").read_text()) == {}
```

- [ ] **Step 2: 跑测验证失败**

Run: `cd backend && pytest tests/test_chat_probe_vision.py -v`
Expected: FAIL（端点和函数不存在）

- [ ] **Step 3: 实现 — TEST_IMG_BASE64**

复刻 Apix 的 76×100 写有 `test vision` 的 PNG 字节，base64 编码。**直接从 Apix 仓库复制**：

```bash
# 在 Apix 源码里找:
#   server/api/probe_vision.py 或类似文件 (含 TEST_IMG_BASE64 字面量)
# 提取 base64 字符串赋值到 chat.py 里
```

若 Apix 没有现成 base64，本地用 Pillow 生成一次：

```python
# scripts/make_probe_img.py (一次性, 不入仓库)
from PIL import Image, ImageDraw, ImageFont
import base64, io
img = Image.new('RGB', (76, 100), 'white')
draw = ImageDraw.Draw(img)
draw.text((4, 30), 'test', fill='black')
draw.text((4, 55), 'vision', fill='black')
buf = io.BytesIO(); img.save(buf, 'PNG')
print(base64.b64encode(buf.getvalue()).decode())
```

把生成的 base64 字符串粘到 `chat.py`：

```python
# 76x100 PNG 写有 'test vision' 文字, 用于 vision 能力探测
TEST_IMG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUg..."   # ← 真实 base64 粘这里
)
```

- [ ] **Step 4: 实现 cache + endpoint**

`backend/app/api/chat.py` 顶部 import 加：

```python
import os
import tempfile
from pathlib import Path
```

加 helper：

```python
def _vision_cache_path() -> Path:
    p = Path(settings.DATA_DIR)
    p.mkdir(parents=True, exist_ok=True)
    return p / "vision_cache.json"


def _load_vision_cache() -> dict:
    path = _vision_cache_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}


def _save_vision_cache(cache: dict) -> None:
    path = _vision_cache_path()
    # 原子写: .tmp 同目录 + os.replace (跨平台原子 rename)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.vision_cache.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
```

加 ProbeVisionRequest + 两个路由：

```python
class ProbeVisionRequest(BaseModel):
    base_url: str
    api_key: str
    model: str
    protocol: Literal['openai', 'anthropic'] = 'openai'


_VISION_PROMPT = ("You are given an image.\n"
                  "The image contains only text.\n"
                  "Extract the exact text from the image.\n"
                  "Return only the text. No explanation.")

_AUTH_ERR_TOKENS = ('unauthorized', 'authentication', 'invalid api key',
                    'api key', 'permission denied', '401')


@router.post("/probe-vision")
async def probe_vision(req: ProbeVisionRequest):
    """探测 model 是否支持 vision; 用一张 OCR 测试图发请求, 看回包是否包含 test/vision 两词。"""
    cache = _load_vision_cache()
    key = f"{req.base_url}::{req.model}"
    if key in cache:
        return {"vision": cache[key], "cached": True}

    try:
        if req.protocol == 'openai':
            client = _get_async_client(req.base_url, req.api_key)
            resp = await client.chat.completions.create(
                model=req.model,
                messages=[
                    {"role": "system", "content": "You are a precise OCR assistant."},
                    {"role": "user", "content": [
                        {"type": "text", "text": _VISION_PROMPT},
                        {"type": "image_url",
                         "image_url": {"url": f"data:image/png;base64,{TEST_IMG_BASE64}"}},
                    ]},
                ],
                max_tokens=100, stream=False,
            )
            content = (resp.choices[0].message.content or "").strip().lower()
        else:  # anthropic
            client = _get_anthropic_client(req.api_key)
            resp = await client.messages.create(
                model=req.model, max_tokens=100,
                messages=[{"role": "user", "content": [
                    {"type": "text", "text": _VISION_PROMPT},
                    {"type": "image", "source": {
                        "type": "base64", "media_type": "image/png", "data": TEST_IMG_BASE64}},
                ]}],
            )
            content = (resp.content[0].text if resp.content else "").strip().lower()

        is_vision = ("test" in content and "vision" in content)
    except Exception as exc:
        err = str(exc).lower()
        if any(tok in err for tok in _AUTH_ERR_TOKENS):
            return {"vision": False, "cached": False, "error": "auth"}
        is_vision = False   # 非 auth 错: 判 False + 写缓存

    cache[key] = is_vision
    _save_vision_cache(cache)
    return {"vision": is_vision, "cached": False}


@router.delete("/probe-vision/cache")
async def clear_vision_cache():
    _save_vision_cache({})
    return {"ok": True}
```

- [ ] **Step 5: 跑测验证通过**

Run: `cd backend && pytest tests/test_chat_probe_vision.py -v`
Expected: PASS（5 cases）

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/chat.py backend/tests/test_chat_probe_vision.py
git commit -m "feat(chat): /probe-vision endpoint — OCR 探图 + 持久化缓存 + DELETE 清空"
```

---

### Task 15: modelVision store（前端缓存 + 探测调度）

**Files:**
- Create: `frontend/src/stores/modelVision.js`
- Test: `frontend/src/__tests__/modelVision-store.test.js`

- [ ] **Step 1: 写失败测试**

`frontend/src/__tests__/modelVision-store.test.js`:

```js
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useModelVisionStore } from '@/stores/modelVision'

function mockHttp(impl) {
  globalThis.window = globalThis.window || {}
  window.api = window.api || {}
  window.api.http = { request: vi.fn(impl) }
}

describe('modelVision store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('hasVision returns undefined before probe', () => {
    const s = useModelVisionStore()
    expect(s.hasVision('u', 'm')).toBeUndefined()
  })

  it('probe writes cache and returns bool', async () => {
    mockHttp(async (_, __, body) => ({
      ok: true, body: { vision: true, cached: false },
    }))
    const s = useModelVisionStore()
    const v = await s.probe('http://x/v1', 'sk-X', 'gpt-4o', 'openai')
    expect(v).toBe(true)
    expect(s.hasVision('http://x/v1', 'gpt-4o')).toBe(true)
  })

  it('isPending true during probe, false after', async () => {
    let resolve
    mockHttp(() => new Promise(r => { resolve = r }))
    const s = useModelVisionStore()
    const p = s.probe('u', 'k', 'm', 'openai')
    expect(s.isPending('u', 'm')).toBe(true)
    resolve({ ok: true, body: { vision: false } })
    await p
    expect(s.isPending('u', 'm')).toBe(false)
  })

  it('probe dedupes concurrent calls for same key', async () => {
    let calls = 0
    mockHttp(() => { calls++; return Promise.resolve({ ok: true, body: { vision: true } }) })
    const s = useModelVisionStore()
    const [a, b] = await Promise.all([
      s.probe('u', 'k', 'm', 'openai'),
      s.probe('u', 'k', 'm', 'openai'),
    ])
    expect(calls).toBe(1)
    expect(a).toBe(b)
  })

  it('clearForBaseUrl drops only entries with that baseUrl', async () => {
    mockHttp(async () => ({ ok: true, body: { vision: true } }))
    const s = useModelVisionStore()
    await s.probe('u1', 'k', 'm1', 'openai')
    await s.probe('u2', 'k', 'm2', 'openai')
    s.clearForBaseUrl('u1')
    expect(s.hasVision('u1', 'm1')).toBeUndefined()
    expect(s.hasVision('u2', 'm2')).toBe(true)
  })

  it('clearAll calls DELETE /probe-vision/cache and clears memory', async () => {
    const calls = []
    mockHttp(async (method, url) => { calls.push([method, url]); return { ok: true, body: {} } })
    const s = useModelVisionStore()
    await s.probe('u', 'k', 'm', 'openai')
    await s.clearAll()
    expect(calls).toContainEqual(['DELETE', '/api/chat/probe-vision/cache'])
    expect(s.hasVision('u', 'm')).toBeUndefined()
  })
})
```

- [ ] **Step 2: 跑测验证失败**

Run: `cd frontend && npx vitest run src/__tests__/modelVision-store.test.js`
Expected: FAIL

- [ ] **Step 3: 实现**

`frontend/src/stores/modelVision.js`:

```js
import { ref } from 'vue'
import { defineStore } from 'pinia'

function keyOf(baseUrl, model) { return `${baseUrl}::${model}` }

export const useModelVisionStore = defineStore('modelVision', () => {
  const cache = ref(new Map())            // key -> bool
  const pending = ref(new Map())          // key -> Promise<bool>

  function hasVision(baseUrl, model) {
    return cache.value.get(keyOf(baseUrl, model))
  }

  function isPending(baseUrl, model) {
    return pending.value.has(keyOf(baseUrl, model))
  }

  async function probe(baseUrl, apiKey, model, protocol) {
    const k = keyOf(baseUrl, model)
    // dedupe in-flight
    const existing = pending.value.get(k)
    if (existing) return existing
    if (cache.value.has(k)) return cache.value.get(k)

    const task = (async () => {
      try {
        const res = await window.api.http.request('POST', '/api/chat/probe-vision', {
          base_url: baseUrl, api_key: apiKey, model, protocol: protocol || 'openai',
        })
        const data = res?.body || {}
        // auth 错: 不写缓存; 让用户改 key 后重探
        if (data.error === 'auth') return false
        const v = !!data.vision
        // 触发响应式: 重建 Map (Pinia 跟踪 ref 的 .value 替换)
        const next = new Map(cache.value)
        next.set(k, v)
        cache.value = next
        return v
      } catch {
        return false
      } finally {
        const np = new Map(pending.value)
        np.delete(k)
        pending.value = np
      }
    })()

    const np = new Map(pending.value)
    np.set(k, task)
    pending.value = np
    return task
  }

  async function clearAll() {
    try {
      await window.api.http.request('DELETE', '/api/chat/probe-vision/cache')
    } catch { /* 即使后端清空失败也清前端内存, 让用户能重探 */ }
    cache.value = new Map()
    pending.value = new Map()
  }

  function clearForBaseUrl(baseUrl) {
    const next = new Map()
    for (const [k, v] of cache.value) {
      if (!k.startsWith(`${baseUrl}::`)) next.set(k, v)
    }
    cache.value = next
  }

  return { cache, pending, hasVision, isPending, probe, clearAll, clearForBaseUrl }
})
```

- [ ] **Step 4: 跑测验证通过**

Run: `cd frontend && npx vitest run src/__tests__/modelVision-store.test.js`
Expected: PASS（6 cases）

- [ ] **Step 5: Commit**

```bash
git add frontend/src/stores/modelVision.js frontend/src/__tests__/modelVision-store.test.js
git commit -m "feat(stores): modelVision store — 探测缓存 + dedupe + clearAll/clearForBaseUrl"
```

---

### Task 16: 触发时机 — 切模型异步探 + 切 key 清同 baseUrl 缓存

**Files:**
- Modify: `frontend/src/stores/aiSettings.js`（setProvider / setApiKey / setModel 钩 modelVision）

⚠️ 不阻塞 UI；探测在后台跑，UI 通过 `hasVision` 三态显示徽章/📎 状态。

- [ ] **Step 1: 改 setApiKey — 清同 baseUrl 缓存**

`setApiKey`:

```js
async function setApiKey(key) {
  const oldBase = getBaseUrl()
  apiKey.value = key
  if (isCustomProvider(provider.value)) {
    useCustomProvidersStore().update(customProviderUuid(provider.value), { apiKey: key })
  }
  // 换 key = 换厂商权限 — 同 baseUrl 旧 vision 结果失效
  try { useModelVisionStore().clearForBaseUrl(oldBase) } catch { /* store 未就绪也安全 */ }
  persist()
  await fetchModels()
  persist()
}
```

文件顶部加 `import { useModelVisionStore } from './modelVision'`。

- [ ] **Step 2: 改 setModel — 切到新 model 时异步起 probe**

`aiSettings.js` 加 `setModel` action（若已有则改）：

```js
function setModel(m) {
  if (model.value === m) return
  model.value = m
  persist()
  // 异步起探测; 不 await, 不阻塞 UI
  _schedulProbeForCurrent()
}

function _schedulProbeForCurrent() {
  const base = getBaseUrl()
  if (!base || !model.value || !apiKey.value) return
  const proto = providerMeta().protocol || 'openai'
  try {
    useModelVisionStore().probe(base, apiKey.value, model.value, proto)
  } catch { /* swallow */ }
}
```

`setProvider` / `fetchModels` 末尾也调一次 `_schedulProbeForCurrent()`（model 被自动校正后才有意义）。

return 里加 `setModel`。

- [ ] **Step 3: 跑既有测试，确认不破**

Run: `cd frontend && npx vitest run src/__tests__/ai-settings-store.test.js`
Expected: PASS（注意 mock `window.api` 时新代码会触发 probe；既有测试若用 vi.spyOn(window.api.http, 'request') 应自动 mock）

如失败：在 store setup 顶部加 `if (typeof window === 'undefined' || !window.api?.http) return` 防御。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/stores/aiSettings.js
git commit -m "feat(aiSettings): 切 model 异步起 vision 探测 + 切 apiKey 清同 baseUrl 缓存"
```

---

### Task 17: 模型 select + 徽章 UI（含 vision/reasoning/context 三徽章）

**Files:**
- Modify: `frontend/src/ide/AssistantPanel.vue`（model-hint 换 select + 徽章）

- [ ] **Step 1: 改模板**

[AssistantPanel.vue:329-332](../../../frontend/src/ide/AssistantPanel.vue#L329) 的 `<span class="model-hint">` 整段替换为：

```vue
<el-select
  :model-value="aiSettings.model"
  size="small"
  class="model-select"
  :disabled="chat.streaming"
  @change="aiSettings.setModel"
>
  <el-option v-for="m in aiSettings.models" :key="m" :label="m" :value="m">
    <span class="model-row">
      <span class="model-name">{{ m }}</span>
      <span class="model-badges">
        <el-tag v-if="capOf(m).vision === true" size="small" type="success" effect="plain">👁</el-tag>
        <el-tag v-else-if="capOf(m).vision === undefined && capOf(m).pending" size="small" type="info" effect="plain">⋯</el-tag>
        <el-tag v-if="capOf(m).reasoning === 'native'" size="small" type="warning" effect="plain">🧠</el-tag>
        <el-tag v-if="capOf(m).context" size="small" type="info" effect="plain">{{ formatContext(capOf(m).context) }}</el-tag>
      </span>
    </span>
  </el-option>
</el-select>
```

- [ ] **Step 2: 加 capOf helper**

`<script setup>` 顶部：

```js
import { capabilityOf, formatContext } from '@/services/llm/modelCapabilities'
import { useModelVisionStore } from '@/stores/modelVision'

const modelVision = useModelVisionStore()

function capOf(m) {
  const base = capabilityOf(aiSettings.provider, m)
  const baseUrl = aiSettings.getBaseUrl()
  return {
    ...base,
    vision: modelVision.hasVision(baseUrl, m),       // true/false/undefined
    pending: modelVision.isPending(baseUrl, m),
  }
}
```

- [ ] **Step 3: CSS（`<style scoped>` 末尾）**

```css
.model-select { width: 200px; margin-right: 6px; }
.model-row { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.model-name { flex: 1; overflow: hidden; text-overflow: ellipsis; }
.model-badges { display: inline-flex; gap: 4px; }
.model-badges .el-tag { padding: 0 6px; height: 18px; line-height: 18px; }
```

- [ ] **Step 4: 手测**

```bash
npm run dev
```

- 厂商切 OpenAI + 输 key → models 拉取 → 切到 gpt-4o → 一会儿后 👁 亮（probe 完成）
- 切 deepseek-v4-pro → 🧠 + 128K 徽章
- 切 anthropic + claude-fable-5 → 👁 + 🧠 + 200K

- [ ] **Step 5: Commit**

```bash
git add frontend/src/ide/AssistantPanel.vue
git commit -m "feat(assistant): 模型 select + 徽章 (👁 vision/🧠 reasoning/上下文) — vision 三态"
```

---

## PR-5 图片上传（📎 + 拖拽 + 多模态）

### Task 18: chat store pendingAttachments + add/remove/clear actions

**Files:**
- Modify: `frontend/src/stores/chat.js`（加 pendingAttachments + 三个 action + sendMessage 多模态）
- Test: `frontend/src/__tests__/chat-attachments.test.js`（新增）

附件单元: `{ id, name, size, mimeType, base64DataUrl, thumbDataUrl }`。

- [ ] **Step 1: 写失败测试**

`frontend/src/__tests__/chat-attachments.test.js`:

```js
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

function mockFile(name, type, size, content = 'AAAA') {
  const blob = new Blob([content], { type })
  Object.defineProperty(blob, 'name', { value: name })
  Object.defineProperty(blob, 'size', { value: size })
  return blob
}

describe('chat attachments (Spec A)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    // FileReader → 同步返回 base64
    global.FileReader = class {
      readAsDataURL(file) {
        this.result = `data:${file.type};base64,QUFBQQ==`
        setTimeout(() => this.onload?.({ target: this }), 0)
      }
    }
  })

  it('addAttachment pushes normalized entry', async () => {
    const { useChatStore } = await import('@/stores/chat')
    const chat = useChatStore()
    await chat.addAttachment(mockFile('a.png', 'image/png', 1024))
    expect(chat.pendingAttachments).toHaveLength(1)
    const a = chat.pendingAttachments[0]
    expect(a.name).toBe('a.png')
    expect(a.mimeType).toBe('image/png')
    expect(a.base64DataUrl).toContain('data:image/png;base64,')
    expect(a.thumbDataUrl).toBeTruthy()
  })

  it('rejects files > 5 MB', async () => {
    const { useChatStore } = await import('@/stores/chat')
    const chat = useChatStore()
    await expect(chat.addAttachment(mockFile('big.png', 'image/png', 6 * 1024 * 1024)))
      .rejects.toThrow(/超过/)
  })

  it('rejects non-image MIME', async () => {
    const { useChatStore } = await import('@/stores/chat')
    const chat = useChatStore()
    await expect(chat.addAttachment(mockFile('a.txt', 'text/plain', 100)))
      .rejects.toThrow(/不支持/)
  })

  it('caps to 5 attachments per message', async () => {
    const { useChatStore } = await import('@/stores/chat')
    const chat = useChatStore()
    for (let i = 0; i < 5; i++) {
      await chat.addAttachment(mockFile(`a${i}.png`, 'image/png', 100))
    }
    await expect(chat.addAttachment(mockFile('a6.png', 'image/png', 100)))
      .rejects.toThrow(/最多/)
  })

  it('removeAttachment + clearAttachments work', async () => {
    const { useChatStore } = await import('@/stores/chat')
    const chat = useChatStore()
    await chat.addAttachment(mockFile('a.png', 'image/png', 100))
    await chat.addAttachment(mockFile('b.png', 'image/png', 100))
    chat.removeAttachment(chat.pendingAttachments[0].id)
    expect(chat.pendingAttachments).toHaveLength(1)
    chat.clearAttachments()
    expect(chat.pendingAttachments).toHaveLength(0)
  })
})
```

- [ ] **Step 2: 跑测验证失败**

Run: `cd frontend && npx vitest run src/__tests__/chat-attachments.test.js`
Expected: FAIL（action 不存在）

- [ ] **Step 3: 实现 — chat.js 加 state + actions**

`frontend/src/stores/chat.js` 在 `messages = ref([])` 之后加：

```js
const pendingAttachments = ref([])

const ALLOWED_MIME = ['image/png', 'image/jpeg', 'image/webp', 'image/gif']
const MAX_SIZE = 5 * 1024 * 1024
const MAX_COUNT = 5

function _readAsDataURL(file) {
  return new Promise((resolve, reject) => {
    const fr = new FileReader()
    fr.onload = () => resolve(fr.result)
    fr.onerror = () => reject(new Error('读取文件失败'))
    fr.readAsDataURL(file)
  })
}

async function _makeThumb(dataUrl, max = 200) {
  // 单测环境 (jsdom) 无 canvas; 直接返回原 dataUrl
  if (typeof document === 'undefined' || !document.createElement('canvas').getContext) {
    return dataUrl
  }
  return new Promise((resolve) => {
    const img = new Image()
    img.onload = () => {
      const ratio = Math.min(1, max / Math.max(img.width, img.height))
      const w = Math.round(img.width * ratio), h = Math.round(img.height * ratio)
      const cvs = document.createElement('canvas')
      cvs.width = w; cvs.height = h
      cvs.getContext('2d').drawImage(img, 0, 0, w, h)
      try { resolve(cvs.toDataURL('image/jpeg', 0.8)) }
      catch { resolve(dataUrl) }
    }
    img.onerror = () => resolve(dataUrl)
    img.src = dataUrl
  })
}

async function addAttachment(file) {
  if (!ALLOWED_MIME.includes(file.type)) {
    throw new Error(`不支持的文件类型: ${file.type || '未知'}（仅 PNG/JPEG/WEBP/GIF）`)
  }
  if (file.size > MAX_SIZE) {
    throw new Error(`文件超过 5MB: ${(file.size / 1024 / 1024).toFixed(1)}MB`)
  }
  if (pendingAttachments.value.length >= MAX_COUNT) {
    throw new Error(`单条消息最多 ${MAX_COUNT} 张图`)
  }
  const dataUrl = await _readAsDataURL(file)
  const thumb = await _makeThumb(dataUrl)
  pendingAttachments.value = [...pendingAttachments.value, {
    id: `att_${_nextId()}`,
    name: file.name || 'image',
    size: file.size,
    mimeType: file.type,
    base64DataUrl: dataUrl,
    thumbDataUrl: thumb,
  }]
}

function removeAttachment(id) {
  pendingAttachments.value = pendingAttachments.value.filter((a) => a.id !== id)
}

function clearAttachments() { pendingAttachments.value = [] }
```

记得 store return 里加 `pendingAttachments`, `addAttachment`, `removeAttachment`, `clearAttachments`。

- [ ] **Step 4: 跑测验证通过**

Run: `cd frontend && npx vitest run src/__tests__/chat-attachments.test.js`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/stores/chat.js frontend/src/__tests__/chat-attachments.test.js
git commit -m "feat(chat): pendingAttachments + addAttachment/remove/clear actions (≤5MB×5)"
```

---

### Task 19: sendMessage 走多模态 content + helper 适配数组

**Files:**
- Modify: `frontend/src/stores/chat.js`（sendMessage / contentTextOf / 构建 apiMessages 段）
- Modify: `frontend/src/ide/chat/model.js`（contentTextOf / activeChunksOf 兼容数组 content）
- Test: `frontend/src/__tests__/chat-attachments.test.js`（追加 sendMessage 形态测试）

- [ ] **Step 1: 加失败测试**

在 `chat-attachments.test.js` 末尾追加：

```js
describe('sendMessage multimodal (Spec A)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('attachments 存在时 user message content 是 OpenAI 数组形式', async () => {
    const captured = { body: null }
    vi.doMock('@/ide/chat/stream', () => ({
      streamChat: async ({ body }) => { captured.body = body },
    }))
    const { useChatStore } = await import('@/stores/chat')
    const { useAiSettingsStore } = await import('@/stores/aiSettings')
    const ai = useAiSettingsStore()
    ai.provider = 'openai'; ai.apiKey = 'sk'; ai.model = 'gpt-4o'
    const chat = useChatStore()
    chat.pendingAttachments = [
      { id: 'a1', name: 'a.png', size: 1, mimeType: 'image/png',
        base64DataUrl: 'data:image/png;base64,AAAA', thumbDataUrl: 'd' },
    ]
    await chat.sendMessage('看看')
    const last = captured.body.messages.at(-2)   // 最后一条非 system 应是 user
    expect(Array.isArray(last.content)).toBe(true)
    expect(last.content[0]).toEqual({ type: 'text', text: '看看' })
    expect(last.content[1].type).toBe('image_url')
    expect(last.content[1].image_url.url).toContain('data:image/png;base64,')
    expect(chat.pendingAttachments).toHaveLength(0)   // 已清空
  })

  it('无附件时 user content 仍是 string', async () => {
    const captured = { body: null }
    vi.doMock('@/ide/chat/stream', () => ({
      streamChat: async ({ body }) => { captured.body = body },
    }))
    const { useChatStore } = await import('@/stores/chat')
    const chat = useChatStore()
    await chat.sendMessage('hi')
    const last = captured.body.messages.at(-2)
    expect(typeof last.content).toBe('string')
  })
})
```

- [ ] **Step 2: 跑测验证失败**

Run: `cd frontend && npx vitest run src/__tests__/chat-attachments.test.js -t "sendMessage multimodal"`
Expected: FAIL

- [ ] **Step 3: 改 contentTextOf（兼容数组 content）**

`frontend/src/ide/chat/model.js` 找到 `export function contentTextOf(msg)` 并修改（保留旧 chunks 走法）：

```js
export function contentTextOf(msg) {
  // 兼容: msg.content 是数组 → 拼接 type==='text' 段
  if (Array.isArray(msg?.content)) {
    return msg.content.filter((p) => p?.type === 'text').map((p) => p.text || '').join('')
  }
  // user 消息 string 形态 (旧)
  if (typeof msg?.content === 'string' && !msg.versions && !msg.chunks) {
    return msg.content
  }
  // assistant 消息: 走 chunks / versions
  const chunks = activeChunksOf(msg)
  return chunks.filter((c) => c.type === 'content').map((c) => c.content || '').join('')
}
```

> 注：现有 `contentTextOf` 实现取 chunks → 拼 `content` 类型；这里前置数组分支，让 user 消息的多模态数组也能转回纯文本（给 UI 显示用）。

- [ ] **Step 4: 改 sendMessage / 构建 apiMessages**

`chat.js` 找到 sendMessage 中创建 user 消息那段，把 user payload 改为支持多模态：

```js
// sendMessage(userContent) 内部:
const attachments = [...pendingAttachments.value]
const userContent = attachments.length === 0
  ? text
  : [
      { type: 'text', text },
      ...attachments.map((a) => ({
        type: 'image_url',
        image_url: { url: a.base64DataUrl },
      })),
    ]
// 创建 user message; _attachments 仅前端展示用
const userMsg = _addMessage('user', null, { content: userContent, _attachments: attachments })
// 注: _addMessage 收到 payload=null + extra.content 时, content 直接赋值, chunks 为空
clearAttachments()
```

`_addMessage` 内已有 `...extra` 展开会覆盖 chunks/timestamp 之外的字段；当 `content` 是数组时， `chunks` 仍按 payload 派生（payload=null → []）。`contentTextOf` 已能从 `m.content` 读出文本，UI 不破。

`chat.js:716-718` 构建 historyMsgs 段替换为：

```js
const historyMsgs = visibleMessages.value.map((m) => {
  if (m.role === 'assistant') {
    return { role: 'assistant', content: stripToolCalls(contentTextOf(m)) }
  }
  // user: 多模态数组原样传; 否则用文本
  return {
    role: 'user',
    content: Array.isArray(m.content) ? m.content : contentTextOf(m),
  }
})
```

`chat.js` 同样位置的 `regenMessage` 分支（`chat.js:755-762`）做相同改动。

- [ ] **Step 5: 跑测验证通过**

Run: `cd frontend && npx vitest run src/__tests__/chat-attachments.test.js src/__tests__/chat-chunks.test.js src/__tests__/chat-branch.test.js`
Expected: PASS（既有 chunks/branch 测试不破）

- [ ] **Step 6: Commit**

```bash
git add frontend/src/stores/chat.js frontend/src/ide/chat/model.js frontend/src/__tests__/chat-attachments.test.js
git commit -m "feat(chat): sendMessage 多模态 content + historyMsgs 数组原样传 + contentTextOf 兼容"
```

---

### Task 20: AssistantPanel 📎 上传按钮 + 拖拽 + 预览条

**Files:**
- Modify: `frontend/src/ide/AssistantPanel.vue`（输入区加 📎/拖拽/预览）

- [ ] **Step 1: 加 📎 按钮（工具栏发送按钮左侧）**

`AssistantPanel.vue:342-350` 发送按钮组前面插入：

```vue
<input
  ref="fileInputRef"
  type="file"
  accept="image/png,image/jpeg,image/webp,image/gif"
  multiple
  hidden
  @change="onFilesPicked"
/>
<el-tooltip :content="attachTooltip" placement="top">
  <el-button
    size="small"
    class="attach-btn"
    :disabled="attachDisabled"
    @click="onAttachClick"
  >
    <span v-if="visionPending">⋯</span>
    <span v-else>📎</span>
  </el-button>
</el-tooltip>
```

- [ ] **Step 2: 加输入区拖拽监听**

`<el-input ...>` 外面包一层 `<div class="textarea-wrap" @dragover.prevent @drop.prevent="onDrop">`，并在 `<el-input>` 之前加预览条：

```vue
<div class="textarea-wrap" @dragover.prevent @drop.prevent="onDrop">
  <div v-if="chat.pendingAttachments.length" class="attachments-strip">
    <div v-for="a in chat.pendingAttachments" :key="a.id" class="attachment-item">
      <img :src="a.thumbDataUrl" :alt="a.name" />
      <span class="attachment-meta">{{ a.name }} · {{ formatBytes(a.size) }}</span>
      <el-button size="small" text @click="chat.removeAttachment(a.id)">✕</el-button>
    </div>
  </div>
  <el-input ... />
</div>
```

- [ ] **Step 3: `<script setup>` 加逻辑**

```js
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'

const fileInputRef = ref(null)

const visionState = computed(() => {
  const base = aiSettings.getBaseUrl()
  return modelVision.hasVision(base, aiSettings.model)   // true/false/undefined
})
const visionPending = computed(() => modelVision.isPending(aiSettings.getBaseUrl(), aiSettings.model))

const attachDisabled = computed(() => {
  if (chat.streaming) return true
  if (visionState.value === true) return false
  return true   // false / undefined → 都不允许点
})

const attachTooltip = computed(() => {
  if (visionState.value === true) return '上传图片 (≤5MB × ≤5)'
  if (visionState.value === false) return `当前模型不支持图像 (${aiSettings.model})`
  if (visionPending.value) return '正在检测视觉能力…'
  return '当前模型未知是否支持图像 (切换模型自动探测)'
})

function onAttachClick() {
  if (visionState.value !== true) return
  fileInputRef.value?.click()
}

async function onFilesPicked(e) {
  const files = Array.from(e.target.files || [])
  e.target.value = ''   // 允许选同名文件重传
  for (const f of files) {
    try { await chat.addAttachment(f) }
    catch (err) { ElMessage.error(err.message || '附件添加失败') }
  }
}

async function onDrop(e) {
  if (visionState.value !== true) {
    ElMessage.warning(attachTooltip.value)
    return
  }
  const files = Array.from(e.dataTransfer?.files || [])
  for (const f of files) {
    try { await chat.addAttachment(f) }
    catch (err) { ElMessage.error(err.message || '附件添加失败') }
  }
}

function formatBytes(n) {
  if (n < 1024) return `${n}B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)}KB`
  return `${(n / 1024 / 1024).toFixed(1)}MB`
}
```

- [ ] **Step 4: CSS**

```css
.textarea-wrap { position: relative; }
.attachments-strip {
  display: flex; flex-wrap: wrap; gap: 6px;
  padding: 6px 8px; background: var(--el-fill-color-light); border-radius: 4px 4px 0 0;
}
.attachment-item {
  display: flex; align-items: center; gap: 6px;
  background: var(--el-bg-color); padding: 2px 6px; border-radius: 4px;
  border: 1px solid var(--el-border-color-lighter);
}
.attachment-item img { width: 32px; height: 32px; object-fit: cover; border-radius: 2px; }
.attachment-meta { font-size: 12px; color: var(--el-text-color-secondary); max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.attach-btn { padding: 4px 8px; }
.attach-btn:disabled { opacity: 0.45; }
```

- [ ] **Step 5: 手测**

```bash
npm run dev
```

- 切 deepseek-v3（非 vision）→ 📎 灰，title「不支持图像」
- 切 gpt-4o + 探测完 → 📎 亮；点击/拖拽 PNG 进去 → 预览条出现
- 5MB 大图 → toast 报错
- 发送 → 预览条清空；user 气泡显示缩略图（Task 21）

- [ ] **Step 6: Commit**

```bash
git add frontend/src/ide/AssistantPanel.vue
git commit -m "feat(assistant): 📎 上传按钮 + 拖拽 + 预览条 — 仅 vision 模型启用"
```

---

### Task 21: user 消息渲染加附件缩略图

**Files:**
- Modify: `frontend/src/ide/AssistantPanel.vue`（user 气泡 + 大图预览）

- [ ] **Step 1: 改 user 消息模板**

`AssistantPanel.vue:193-198` 替换：

```vue
<div v-else class="msg-body user-msg">
  <div class="msg-content">
    <div v-if="msg._attachments?.length" class="msg-attachments">
      <img
        v-for="a in msg._attachments"
        :key="a.id"
        :src="a.thumbDataUrl"
        :alt="a.name"
        class="msg-attachment-thumb"
        @click="openImagePreview(a.base64DataUrl)"
      />
    </div>
    <pre class="user-text">{{ contentText(msg) }}</pre>
  </div>
</div>
```

- [ ] **Step 2: 加大图预览（el-image-viewer）**

`<script setup>`：

```js
import { ElImageViewer } from 'element-plus'

const previewUrl = ref(null)
function openImagePreview(url) { previewUrl.value = url }
function closeImagePreview() { previewUrl.value = null }
```

模板末尾：

```vue
<el-image-viewer v-if="previewUrl" :url-list="[previewUrl]" hide-on-click-modal @close="closeImagePreview" />
```

- [ ] **Step 3: CSS**

```css
.msg-attachments { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 6px; }
.msg-attachment-thumb {
  width: 80px; height: 80px; object-fit: cover; border-radius: 4px; cursor: zoom-in;
  border: 1px solid var(--el-border-color-lighter);
}
```

- [ ] **Step 4: 手测**

发条带图消息 → 气泡里出现 80×80 缩略图 → 点击放大预览。重生成对话不影响 \_attachments 显示（trailingAfter 模型 + extras 透传都通过）。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/ide/AssistantPanel.vue
git commit -m "feat(assistant): user 消息气泡显示附件缩略图 + 点击大图预览"
```

---

### Task 22: 8 个厂商 SVG 图标 + 厂商下拉用 icon

**Files:**
- Create: `frontend/src/assets/icons/llm_providers/{deepseek,openai,claude,moonshot,qwen,google,ollama,custom}.svg`
- Modify: `frontend/src/ide/AssistantPanel.vue`（provider-select option 用 icon）

- [ ] **Step 1: 从 Apix 复制 8 个 svg**

```bash
mkdir -p frontend/src/assets/icons/llm_providers
# 从 Apix 仓库 (JJJJSTIYYYY/Apix) 的 src/renderer/assets/icons/llm_providers/ 复制:
#   deepseek.svg openai.svg claude.svg moonshot.svg qwen.svg google.svg ollama.svg custom.svg
# Apix LICENSE 已确认开源, commit 注明来源
```

将复制后的 8 个文件提到 `frontend/src/assets/icons/llm_providers/`。

- [ ] **Step 2: 加 iconUrlOf helper**

`frontend/src/services/llm/icons.js`（新文件）:

```js
// Vite 推荐: 动态 import.meta.glob 把目录扫成 url 映射
const ICONS = import.meta.glob('@/assets/icons/llm_providers/*.svg', { eager: true, query: '?url', import: 'default' })

const MAP = Object.fromEntries(
  Object.entries(ICONS).map(([path, url]) => {
    const key = path.split('/').pop().replace('.svg', '')   // 'claude' 等
    return [key, url]
  }),
)

export function iconUrlOf(iconKey) {
  return MAP[iconKey] || MAP.custom
}
```

- [ ] **Step 3: 改厂商下拉**

`AssistantPanel.vue:288-301` 厂商 select 改为：

```vue
<el-select
  :model-value="aiSettings.provider"
  size="small"
  class="provider-select"
  :disabled="chat.streaming"
  @change="onProviderChange"
>
  <template #prefix>
    <img :src="iconUrlOf(aiSettings.providerMeta().iconKey)" class="provider-icon" alt="" />
  </template>
  <el-option v-for="p in PROVIDERS" :key="p.id" :label="p.label" :value="p.id">
    <span class="provider-row">
      <img :src="iconUrlOf(p.iconKey)" class="provider-icon" alt="" />
      <span>{{ p.label }}</span>
    </span>
  </el-option>
</el-select>
```

`<script setup>`：

```js
import { iconUrlOf } from '@/services/llm/icons'
```

CSS：

```css
.provider-icon { width: 16px; height: 16px; object-fit: contain; vertical-align: middle; }
.provider-row { display: inline-flex; align-items: center; gap: 6px; }
```

- [ ] **Step 4: 手测**

```bash
npm run dev
```

下拉每项有 icon；选中项的前缀 icon 同步变化。custom 用 custom.svg。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/assets/icons/llm_providers frontend/src/services/llm/icons.js frontend/src/ide/AssistantPanel.vue
git commit -m "feat(assistant): 8 厂商 svg 图标 + 厂商下拉前缀/选项 icon (来自 Apix)"
```

---

## 收官 — 全测 + 自检

- [ ] **Step 1: 全套前端测试**

Run: `cd frontend && npx vitest run`
Expected: 全部 PASS（含既有套件）

- [ ] **Step 2: 全套后端测试**

Run: `cd backend && pytest`
Expected: 全部 PASS

- [ ] **Step 3: 手测全链路（DeepSeek 默认环境 + Anthropic + Vision）**

```bash
npm run dev
```

依次：
1. 厂商 deepseek + deepseek-v4-pro + reasoning deep → 发条问题，看 🧠 思考气泡
2. 切 OpenAI + gpt-4o（待 vision 探完）→ 拖一张截图 + 文本「描述这张图」→ 模型回包应描述图片
3. 切 Anthropic + claude-fable-5 + reasoning deep → 同上拖图 → 模型回包
4. 切到 deepseek-v3（prompt-only）→ 🧠 灰，📎 灰，reasoningMode 应自动从 deep 降到 auto
5. 自定义厂商（🔑 弹窗填 baseUrl + key）→ 写到 customProviders[default]，刷新页面后保留

- [ ] **Step 4: 看 docs/devlogs/ 记一笔 Apix 借鉴落地总结**

新建 `docs/devlogs/Desktop_阶段11_聊天框Apix化.md`，列：
- 落了哪些 spec 章节
- 哪些推到了 Spec B（设置页 / 自定义厂商多组 CRUD / 批量 vision 探测 / 清缓存 UI / agent 独立 key）
- 实际工时 / 行数对比 spec 估算
- 已知遗留（Anthropic 工具循环遵循度、国内代理依赖）

- [ ] **Step 5: 最终 Commit**

```bash
git add docs/devlogs/
git commit -m "docs(devlog): 阶段11 聊天框 Apix 化收官 — 5 PR 全部落地"
```

---

## 自检清单（Self-Review）

### Spec 覆盖（每条都有对应 task）

- §1 PROVIDERS 扩 8 项 + protocol/iconKey/fallbackModels → Task 2
- §2 customProviders schema + 迁移 → Task 1 + Task 3
- §3.1 fetchModels protocol 字段 + ANTHROPIC_MODELS 短路 → Task 4
- §3.2 modelCapabilities + capabilityOf → Task 5
- §3.3 模型 select + 徽章 → Task 17
- §3.4 modelReasoningSupport 委托（两态收敛） → Task 6
- §4.1 /probe-vision endpoint + DELETE 清缓存 + vision_cache.json 原子写 → Task 14
- §4.2 modelVision store + 触发时机 → Task 15 + Task 16
- §5.1 _build_request_extras → Task 7
- §5.2 ChatRequest reasoning_mode + protocol → Task 7 + Task 8
- §5.3 reasoning radio UI → Task 9
- §5.4 自动降级 → Task 9
- §6.1 📎 UI + 拖拽 → Task 20
- §6.2 chat store pendingAttachments → Task 18
- §6.3 contentTextOf 数组兼容 + 构建 apiMessages 改造 → Task 19
- §6.4 user 消息渲染附件 → Task 21
- §7 后端协议分层（anthropic SDK + 双 stream + msg 转换 + requirements） → Task 10/11/12 + Task 13 手测
- §7.6 厂商 icon → Task 22

### 类型 / 命名一致性

- `protocol`: 'openai' | 'anthropic'（spec / 前端 / 后端 / 测试 一致）
- `reasoning_mode`: 'auto' | 'fast' | 'deep'（一致）
- 函数名 `_build_request_extras` / `_stream_openai` / `_stream_anthropic` / `_get_anthropic_client` / `_split_system` / `_openai_msg_to_anthropic`（一致）
- chat store 暴露 `pendingAttachments` / `addAttachment` / `removeAttachment` / `clearAttachments`（一致）
- modelVision 暴露 `hasVision` / `isPending` / `probe` / `clearAll` / `clearForBaseUrl`（一致）
- customProviders 暴露 `list` / `add` / `update` / `remove` / `get` / `autoFetchModels`（一致）
- iconKey 值域：`deepseek/openai/claude/moonshot/qwen/google/ollama/custom`（PROVIDERS 与 icon 文件名一致）

### 风险与缓解

- ⚠️ `el-radio-button` disabled 灰度 → Task 9 加 `.is-disabled` 自定义 CSS 兜底
- ⚠️ Anthropic 国内 endpoint 不通 → 用户配代理；Spec B 会做代理盘活
- ⚠️ vision probe 烧 token → 100 tokens × 1 次/未知模型，可忽略
- ⚠️ Anthropic 提示词工具循环遵循度 → Task 13 手测验证；若不达标单独开 issue
- ⚠️ `provider='custom:<uuid>'` 散落 split → Task 3 引 `isCustomProvider` / `customProviderUuid` 集中

---
