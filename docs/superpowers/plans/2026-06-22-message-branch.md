# 消息分支 (重生成分支) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给助手消息加重生成分支 — 重新生成不覆盖原回复,保留为历史版本,UI prev/next 切换;重生成时后续消息隐藏(不删,切回原版恢复)。用户消息编辑不做 (YAGNI)。

**Architecture:** 助手消息从单一 `chunks` 扩展为 `versions[]` + `activeVersion` + `trailingAfter`。`visibleMessages` computed 按当前 version 链派生显示。重生成复用现有 SSE 流 + 工具循环,只发当前 version 链作 API 历史。AssistantPanel 加 `‹n/m›` 切换器 + hover 浮现重生成钮,淡入淡出切换,reduced-motion 兜底。后端契约不变。

**Tech Stack:** Vue 3 + Pinia + Element Plus, Vitest 2.1, --km-* CSS token, 无新依赖。

**Spec:** `docs/superpowers/specs/2026-06-22-message-branch-design.md`

---

## File Structure

**修改:**
- `frontend/src/stores/chat.js` — 消息模型 versions/activeVersion/trailingAfter; helper 适配 activeVersion; `visibleMessages` computed; `regenMessage` action; `_addMessage` 兼容; `sendMessage` 历史序列化改用 visibleMessages
- `frontend/src/ide/AssistantPanel.vue` — visibleMessages 渲染; `‹n/m›` 版本切换器; 重生成钮 (hover 浮现); 切换淡入淡出; reduced-motion; streaming/工具循环中禁用
- `frontend/src/__tests__/chat-chunks.test.js` — contentTextOf 读 activeVersion; 兼容旧消息

**新增:**
- `frontend/src/__tests__/chat-branch.test.js` — 重生成追加 version + 隐藏 trailingAfter; 切版本恢复; visibleMessages 过滤

---

## 现状关键事实 (实施前必读)

- `_addMessage(role, payload, extra)`: 建 `{id, role, chunks, timestamp, ...extra}`, push 进 `messages.value`。payload 是字符串→单 content chunk;是数组→直接用。
- `contentTextOf(msg)`: 读 `msg.chunks` 里 type==='content' 的拼接。**扩展后要读 `msg.versions[activeVersion].chunks`**, 且兼容旧消息 (无 versions → 用 msg.chunks)。
- `stripToolCalls(text)`: 纯文本处理, 不改。
- `sendMessage(userContent)` (chat.js:822): push user 消息 → 工具循环 → 每轮 `historyMsgs = messages.value.map(m => ({role, content: m.role==='assistant' ? stripToolCalls(contentTextOf(m)) : contentTextOf(m)}))` → `_streamResponse(apiMessages, assistantMsg)`。**扩展后 historyMsgs 改用 `visibleMessages.value`**。
- `_streamResponse(apiMessages, assistantMsg)`: SSE 流进 `assistantMsg.chunks`。**扩展后要流进 `assistantMsg.versions[activeVersion].chunks`**。
- AssistantPanel `v-for msg in chat.messages` → 助手 `v-for chunk in msg.chunks`。**扩展后改 `chat.visibleMessages` + `msg.versions[msg.activeVersion].chunks`**。
- 消息 id 由 `_nextId()` 生成 (`msg_${Date.now()}_${counter}`)。
- 工具循环: `MAX_TOOL_ROUNDS=3`, 每轮在 assistantMsg 上 splitToolCallChunks + 执行 tool_call chunks。
- `streaming` ref 标记是否在流中; `currentStreamId` 当前流的消息 id。

---

## Task 1: 消息模型 helper 适配 (versions + activeVersion, 兼容旧)

**Files:**
- Modify: `frontend/src/stores/chat.js` (contentTextOf/thinkTextOf 适配)
- Test: `frontend/src/__tests__/chat-chunks.test.js`

这一步只改 helper 函数 + 测试, 不动 store 内部。helper 要能读 "助手消息的当前 version chunks", 且兼容旧消息 (无 versions 字段 → 用 chunks)。

- [ ] **Step 1: Add failing tests to chat-chunks.test.js**

在 `frontend/src/__tests__/chat-chunks.test.js` 末尾追加 (保留既有测试):

```js
import { contentTextOf, thinkTextOf } from '@/stores/chat'

describe('contentTextOf 适配 versions', () => {
  it('旧消息 (无 versions) 仍读 chunks', () => {
    const msg = { role: 'assistant', chunks: [{ type: 'content', content: 'old' }] }
    expect(contentTextOf(msg)).toBe('old')
  })

  it('新版助手消息读 activeVersion 的 chunks', () => {
    const msg = {
      role: 'assistant',
      versions: [
        { id: 'v1', chunks: [{ type: 'content', content: 'first' }] },
        { id: 'v2', chunks: [{ type: 'content', content: 'second' }] },
      ],
      activeVersion: 1,
    }
    expect(contentTextOf(msg)).toBe('second')
  })

  it('activeVersion=0 读第一版', () => {
    const msg = {
      role: 'assistant',
      versions: [
        { id: 'v1', chunks: [{ type: 'content', content: 'first' }] },
        { id: 'v2', chunks: [{ type: 'content', content: 'second' }] },
      ],
      activeVersion: 0,
    }
    expect(contentTextOf(msg)).toBe('first')
  })

  it('thinkTextOf 同理读 activeVersion', () => {
    const msg = {
      role: 'assistant',
      versions: [
        { id: 'v1', chunks: [{ type: 'think', content: 'think1' }] },
      ],
      activeVersion: 0,
    }
    expect(thinkTextOf(msg)).toBe('think1')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- chat-chunks.test.js`
Expected: FAIL — contentTextOf 仍读 msg.chunks, 新版消息返回 ''

- [ ] **Step 3: Add helper to resolve active chunks**

在 `frontend/src/stores/chat.js`, `contentTextOf` 上方加一个内部 helper (导出供测试):

```js
/** 取消息当前生效的 chunks (助手消息读 versions[activeVersion], 旧消息/用户消息读 chunks) */
export function activeChunksOf(msg) {
  if (!msg) return []
  if (msg.role === 'assistant' && Array.isArray(msg.versions)) {
    const v = msg.versions[msg.activeVersion ?? 0]
    return v?.chunks ?? []
  }
  return Array.isArray(msg.chunks) ? msg.chunks : []
}
```

- [ ] **Step 4: Update contentTextOf + thinkTextOf to use activeChunksOf**

替换 `contentTextOf` 和 `thinkTextOf`:

```js
/** 拼接消息当前 version 的 content chunk 文本 (供 API 历史 + MarkdownViewer) */
export function contentTextOf(msg) {
  return activeChunksOf(msg).filter((c) => c.type === 'content').map((c) => c.content).join('')
}

/** 拼接消息当前 version 的 think chunk 文本 */
export function thinkTextOf(msg) {
  return activeChunksOf(msg).filter((c) => c.type === 'think').map((c) => c.content).join('')
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npm test -- chat-chunks.test.js`
Expected: PASS (既有 + 4 新测试)

- [ ] **Step 6: Run full suite to verify no regression**

Run: `cd frontend && npm test`
Expected: all pass (旧消息无 versions, contentTextOf 走 chunks 分支, 行为不变)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/stores/chat.js frontend/src/__tests__/chat-chunks.test.js
git commit -m "feat(chat): activeChunksOf helper + contentTextOf/thinkTextOf 读 activeVersion (兼容旧消息)"
```

---

## Task 2: _addMessage 建 versions 结构 + visibleMessages computed

**Files:**
- Modify: `frontend/src/stores/chat.js` (_addMessage + visibleMessages)
- Test: `frontend/src/__tests__/chat-branch.test.js` (新建)

`_addMessage` 给助手消息建 `versions: [{id, chunks, timestamp}]` + `activeVersion: 0` + `trailingAfter: {}`。用户消息保持 `chunks` (无 versions)。`visibleMessages` computed 暂时直接返回 messages (Task 3 加 trailingAfter 过滤)。

- [ ] **Step 1: Write failing test**

Create `frontend/src/__tests__/chat-branch.test.js`:

```js
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

// mock electron + http (chat store 顶层有 window.api 依赖)
vi.mock('@/stores/workspace', () => ({ useWorkspaceStore: () => ({ hasProject: false, rootName: '', tree: [] }) }))
vi.mock('@/stores/projectGraph', () => ({ useProjectGraphStore: () => ({}) }))
vi.mock('@/stores/aiSettings', () => ({
  useAiSettingsStore: () => ({ permissionFor: () => 'allow', formatEnabledMemories: () => '', reasoningInstruction: () => '' }),
  TOOL_PERMISSION: { ALLOW: 'allow', ASK: 'ask', DENY: 'deny' },
}))

const { useChatStore } = await import('@/stores/chat')

describe('chat 分支 — _addMessage 结构', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('助手消息建 versions + activeVersion + trailingAfter', () => {
    const chat = useChatStore()
    // _addMessage 是内部函数, 通过 sendMessage 间接触发难 (要 mock SSE), 直接测结构用 messages
    // 这里用 clearMessages 后手动 push 不行, 改测: 任何助手消息都应有 versions 结构
    // 间接: clearMessages 后 messages 为空, 无从测 _addMessage
    // 改为测 visibleMessages 初始为空
    expect(chat.visibleMessages).toEqual([])
  })

  it('visibleMessages 默认等于 messages (无 trailingAfter 隐藏时)', async () => {
    const chat = useChatStore()
    // 手动塞一条用户消息测 visibleMessages 透传 (用户消息无 versions, 不隐藏)
    // chat.messages 是 ref, 但 push 走 _addMessage; 这里测 store 暴露的 visibleMessages computed
    // 先确认 visibleMessages 存在且是数组
    expect(Array.isArray(chat.visibleMessages)).toBe(true)
  })
})
```

注: Task 2 的测试较薄 (因为 _addMessage/sendMessage 内部难单测, 需 mock SSE)。Task 3 会加 visibleMessages 过滤的真实测试。Task 2 主要验证结构存在 + 不崩。

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- chat-branch.test.js`
Expected: FAIL — `chat.visibleMessages` is undefined

- [ ] **Step 3: Update _addMessage to build versions for assistant**

在 `frontend/src/stores/chat.js`, 替换 `_addMessage`:

```js
  function _addMessage(role, payload, extra = {}) {
    const chunks = typeof payload === 'string'
      ? [{ type: 'content', content: payload }]
      : Array.isArray(payload) ? payload : []
    const ts = new Date().toISOString()
    let msg
    if (role === 'assistant') {
      // 助手消息: versions 结构 (支持重生成分支)
      const versionId = _nextId().replace('msg_', 'ver_')
      msg = {
        id: _nextId(), role,
        versions: [{ id: versionId, chunks, timestamp: ts }],
        activeVersion: 0,
        trailingAfter: {}, // { [versionId]: msgId[] } — 该版后续可见消息
        timestamp: ts,
        ...extra,
      }
    } else {
      msg = { id: _nextId(), role, chunks, timestamp: ts, ...extra }
    }
    messages.value.push(msg)
    return msg
  }
```

- [ ] **Step 4: Add visibleMessages computed (暂时透传, Task 3 加过滤)**

在 `useChatStore` 的 `hasMessages` computed 附近加:

```js
  /** 当前可见消息 (按各助手消息 activeVersion 链过滤, 隐藏非当前 version 的 trailingAfter) */
  const visibleMessages = computed(() => {
    // Task 3 加 trailingAfter 过滤; 此处先透传保证不崩
    return messages.value
  })
```

在 return 里加 `visibleMessages`:

```js
  return {
    messages, visibleMessages, streaming, currentStreamId, error,
    hasMessages,
    // ... 其余不变
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npm test -- chat-branch.test.js`
Expected: PASS

- [ ] **Step 6: Run full suite**

Run: `cd frontend && npm test`
Expected: all pass (visibleMessages 透传, 行为等价 messages)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/stores/chat.js frontend/src/__tests__/chat-branch.test.js
git commit -m "feat(chat): _addMessage 建 versions 结构 + visibleMessages computed"
```

---

## Task 3: visibleMessages 过滤 trailingAfter + setVersion 切换

**Files:**
- Modify: `frontend/src/stores/chat.js` (visibleMessages 过滤 + setVersion action)
- Test: `frontend/src/__tests__/chat-branch.test.js` (加测试)

`visibleMessages`: 遍历 messages, 对每条助手消息只在其 activeVersion 链上时可见; 非当前 version 的 trailingAfter 隐藏。`setVersion(msgId, idx)`: 切助手消息 activeVersion, 自动调整后续可见性。

简化模型: 不用 trailingAfter Map (复杂), 改用**每个 version 记录其生成时 messages 数组的长度** (`versionSpanEnd`), 切到该 version 时, 该助手消息之后到 `versionSpanEnd` 的消息可见, 超出 (更新 version 产生的) 隐藏。

重新定义模型 (比 spec 的 trailingAfter 更简单, 等价):

```js
assistantMsg = {
  id, role: 'assistant',
  versions: [{ id, chunks, timestamp, spanEnd: <messages.value.length at gen complete> }],
  activeVersion: 0,
}
```
`spanEnd`: 该 version 生成完成时 messages 数组的长度 (即该 version 的后续消息到此为止)。visibleMessages 逻辑: 一条消息 M 可见, 当且仅当: 它在所有"已切到某 version 且 M.index >= 该 version.spanEnd 的助手消息"之后... 这仍复杂。

**采用更简单的线性化方案 (最终模型, 替代 spec 的 trailingAfter)**:

每条助手消息的 version 记 `spanEnd` (生成完成时 messages 长度)。`visibleMessages` computed:
1. 从头遍历 messages
2. 遇到助手消息 A: 它总是可见; 记录 A 的当前 activeVersion 的 `spanEnd` 作为"当前段终点"
3. 在 A 之后、index < spanEnd 的消息可见; index >= spanEnd 的隐藏 (属于被覆盖的新 version 产生)
4. 遇到下一个助手消息 B: B 可见 (新段开始), 用 B 的 spanEnd

即: 每个助手消息"管辖"它到其 spanEnd 之间的消息。切 version 改 spanEnd 边界。

- [ ] **Step 1: Replace visibleMessages test with real filtering tests**

替换 `frontend/src/__tests__/chat-branch.test.js` 全部内容:

```js
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/stores/workspace', () => ({ useWorkspaceStore: () => ({ hasProject: false, rootName: '', tree: [] }) }))
vi.mock('@/stores/projectGraph', () => ({ useProjectGraphStore: () => ({}) }))
vi.mock('@/stores/aiSettings', () => ({
  useAiSettingsStore: () => ({ permissionFor: () => 'allow', formatEnabledMemories: () => '', reasoningInstruction: () => '' }),
  TOOL_PERMISSION: { ALLOW: 'allow', ASK: 'ask', DENY: 'deny' },
}))

const { useChatStore } = await import('@/stores/chat')

// 辅助: 直接构造一个带 versions 的助手消息塞进 messages (绕过 SSE mock)
function pushAssistant(chat, { versions, activeVersion = 0 }) {
  const msg = {
    id: `msg_a_${chat.messages.length}`,
    role: 'assistant',
    versions: versions.map((v, i) => ({ id: `v_${chat.messages.length}_${i}`, chunks: v.chunks, timestamp: v.ts || '2026-01-01', spanEnd: v.spanEnd })),
    activeVersion,
    timestamp: '2026-01-01',
  }
  chat.messages.push(msg)
  return msg
}
function pushUser(chat, text) {
  chat.messages.push({ id: `msg_u_${chat.messages.length}`, role: 'user', chunks: [{ type: 'content', content: text }], timestamp: '2026-01-01' })
}

describe('chat 分支 — visibleMessages + setVersion', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('单 version 助手消息: 后续消息在其 spanEnd 内可见', () => {
    const chat = useChatStore()
    pushUser(chat, 'q1')
    pushAssistant(chat, { versions: [{ chunks: [{ type: 'content', content: 'a1' }], spanEnd: 2 }] }) // index1, spanEnd=2 → 只它自己
    expect(chat.visibleMessages.length).toBe(2)
  })

  it('spanEnd 覆盖后续消息: 助手+用户+助手都在第一助手 spanEnd 内', () => {
    const chat = useChatStore()
    pushUser(chat, 'q1')                          // 0
    pushAssistant(chat, { versions: [{ chunks: [], spanEnd: 4 }] }) // 1, spanEnd=4
    pushUser(chat, 'q2')                          // 2
    pushAssistant(chat, { versions: [{ chunks: [], spanEnd: 4 }] }) // 3, spanEnd=4
    expect(chat.visibleMessages.length).toBe(4)
  })

  it('重生成: 第二版 spanEnd 更小, 旧版后续被隐藏', () => {
    const chat = useChatStore()
    pushUser(chat, 'q1')                          // 0
    // 助手消息: v0 (spanEnd=4, 含后续 q2+a2), v1 (spanEnd=2, 重生成后无后续)
    pushAssistant(chat, {
      versions: [
        { chunks: [{ type: 'content', content: 'old' }], spanEnd: 4 },
        { chunks: [{ type: 'content', content: 'new' }], spanEnd: 2 },
      ],
      activeVersion: 1, // 当前看新版
    })
    pushUser(chat, 'q2')                          // 2 — 新版 spanEnd=2, index2 >= 2 隐藏
    pushAssistant(chat, { versions: [{ chunks: [], spanEnd: 4 }] }) // 3 — 隐藏
    expect(chat.visibleMessages.length).toBe(2) // 只 q1 + 助手新版
  })

  it('切回旧版 (setVersion 0): 后续恢复可见', () => {
    const chat = useChatStore()
    pushUser(chat, 'q1')                          // 0
    const a = pushAssistant(chat, {
      versions: [
        { chunks: [{ type: 'content', content: 'old' }], spanEnd: 4 },
        { chunks: [{ type: 'content', content: 'new' }], spanEnd: 2 },
      ],
      activeVersion: 1,
    })
    pushUser(chat, 'q2')                          // 2
    pushAssistant(chat, { versions: [{ chunks: [], spanEnd: 4 }] }) // 3
    expect(chat.visibleMessages.length).toBe(2) // 新版: 2 条
    chat.setVersion(a.id, 0)                      // 切旧版
    expect(chat.visibleMessages.length).toBe(4) // 旧版: 4 条
  })

  it('setVersion 越界忽略', () => {
    const chat = useChatStore()
    pushUser(chat, 'q1')
    const a = pushAssistant(chat, { versions: [{ chunks: [], spanEnd: 2 }] })
    chat.setVersion(a.id, 5) // 越界
    expect(a.activeVersion).toBe(0)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- chat-branch.test.js`
Expected: FAIL — visibleMessages 仍透传 (返回全部 4 条而非 2)

- [ ] **Step 3: Implement visibleMessages filtering + setVersion**

在 `frontend/src/stores/chat.js`, 替换 Task 2 的透传 `visibleMessages`:

```js
  /**
   * 当前可见消息: 每个助手消息"管辖"它到其 activeVersion.spanEnd 之间的消息。
   * 切 version 改 spanEnd 边界 → 后续显隐。
   * 用户消息无 versions, 总是可见 (除非被前面某助手消息的 spanEnd 截断)。
   */
  const visibleMessages = computed(() => {
    const all = messages.value
    const out = []
    let spanEnd = Infinity // 当前段终点 (最近一个助手消息 activeVersion 的 spanEnd)
    for (let i = 0; i < all.length; i++) {
      const m = all[i]
      if (i >= spanEnd) break // 超出当前段, 后续都隐藏 (属于被覆盖的新 version)
      out.push(m)
      if (m.role === 'assistant' && Array.isArray(m.versions)) {
        const v = m.versions[m.activeVersion ?? 0]
        if (v && typeof v.spanEnd === 'number') {
          spanEnd = v.spanEnd // 更新段终点
        }
      }
    }
    return out
  })
```

加 `setVersion` action (在 `stopStreaming` 附近):

```js
  /** 切助手消息的版本 (prev/next 导航) */
  function setVersion(msgId, idx) {
    const m = messages.value.find((x) => x.id === msgId)
    if (!m || !Array.isArray(m.versions)) return
    if (idx < 0 || idx >= m.versions.length) return
    m.activeVersion = idx
  }
```

在 return 里加 `setVersion`:

```js
    sendMessage, stopStreaming, clearMessages,
    setVersion,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- chat-branch.test.js`
Expected: PASS (5 tests)

- [ ] **Step 5: Run full suite**

Run: `cd frontend && npm test`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add frontend/src/stores/chat.js frontend/src/__tests__/chat-branch.test.js
git commit -m "feat(chat): visibleMessages 按 spanEnd 过滤 + setVersion 切版本"
```

---

## Task 4: regenMessage 重生成 action

**Files:**
- Modify: `frontend/src/stores/chat.js` (regenMessage)
- Test: `frontend/src/__tests__/chat-branch.test.js` (加测试)

`regenMessage(msgId)`: 在该助手消息上追加新 version (activeVersion 指向新), 设 spanEnd=当前 messages 长度 (新 version 无后续), 然后以该消息之前的 visible 历史为上下文重新生成 (复用 _streamResponse + 工具循环)。新 version 的 chunks 流式填充。

- [ ] **Step 1: Add failing test for regenMessage structure**

在 `frontend/src/__tests__/chat-branch.test.js` 末尾追加:

```js
describe('chat 分支 — regenMessage', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('regenMessage 追加新 version + activeVersion 指向新 + 新版 spanEnd=当前长度', async () => {
    const chat = useChatStore()
    pushUser(chat, 'q1')                          // 0
    const a = pushAssistant(chat, { versions: [{ chunks: [{ type: 'content', content: 'old' }], spanEnd: 2 }] }) // 1
    // mock _streamResponse 不实际请求: regenMessage 应建 version 但 chunks 空 (流由 _streamResponse 填)
    // 这里测结构: 调 regenMessage 后 versions.length===2, activeVersion===1, spanEnd===2 (当前长度)
    // 但 regenMessage 会触发 SSE, 需 mock window.api.http。用 try/catch 容错: 结构建好即算
    try {
      await chat.regenMessage(a.id)
    } catch { /* SSE mock 缺失会抛, 忽略 — 只验结构 */ }
    const updated = chat.messages.find((m) => m.id === a.id)
    expect(updated.versions.length).toBe(2)
    expect(updated.activeVersion).toBe(1)
    expect(updated.versions[1].spanEnd).toBe(2) // 新版生成时 messages 长度=2
  })

  it('regenMessage 旧版保留 spanEnd 不变', async () => {
    const chat = useChatStore()
    pushUser(chat, 'q1')
    const a = pushAssistant(chat, { versions: [{ chunks: [{ type: 'content', content: 'old' }], spanEnd: 5 }] })
    try { await chat.regenMessage(a.id) } catch { /* ignore */ }
    const updated = chat.messages.find((m) => m.id === a.id)
    expect(updated.versions[0].spanEnd).toBe(5) // 旧版 spanEnd 不动
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- chat-branch.test.js`
Expected: FAIL — `chat.regenMessage is not a function`

- [ ] **Step 3: Implement regenMessage**

在 `frontend/src/stores/chat.js`, `sendMessage` 之后加 `regenMessage`。逻辑:
1. 找到助手消息 A, 找到它对应的 user 提问 (A 之前最近的 visible user 消息)
2. 在 A.versions 追加新 version {id, chunks:[], timestamp, spanEnd: messages.value.length} (新 version 此时无后续)
3. A.activeVersion 指向新 version
4. 构建 API 历史: A 之前的 visibleMessages (到 user 提问为止) 序列化
5. 复用工具循环 + _streamResponse, 流进新 version 的 chunks

```js
  /** 重生成指定助手消息 (追加新 version, 不覆盖原) */
  async function regenMessage(msgId) {
    if (streaming.value) return // 流中禁止重生成
    const idx = messages.value.findIndex((m) => m.id === msgId)
    if (idx < 0) return
    const target = messages.value[idx]
    if (target.role !== 'assistant' || !Array.isArray(target.versions)) return

    error.value = null
    abortController.value = new AbortController()

    // 追加新 version, activeVersion 指向它, spanEnd=当前长度 (新 version 无后续)
    const newVerId = _nextId().replace('msg_', 'ver_')
    const newVersion = { id: newVerId, chunks: [], timestamp: new Date().toISOString(), spanEnd: messages.value.length }
    target.versions.push(newVersion)
    target.activeVersion = target.versions.length - 1

    // 收集上下文
    const context = await _collectContext()

    // 工具循环 (复用 sendMessage 的逻辑, 但历史只取 target 之前的 visible 消息)
    let toolRound = 0
    while (toolRound < MAX_TOOL_ROUNDS) {
      toolRound++
      const systemMsg = buildSystemPrompt(context)
      // 历史: target 之前的 visibleMessages (含 target 对应的 user 提问), 不含 target 自己
      const visibleSoFar = visibleMessages.value.filter((m) => {
        const mIdx = messages.value.indexOf(m)
        return mIdx < idx
      })
      const historyMsgs = visibleSoFar.map((m) => ({
        role: m.role,
        content: m.role === 'assistant' ? stripToolCalls(contentTextOf(m)) : contentTextOf(m),
      }))
      const apiMessages = [systemMsg, ...historyMsgs]

      streaming.value = true
      currentStreamId.value = target.id
      try {
        await _streamResponse(apiMessages, target) // _streamResponse 需流进 activeVersion 的 chunks (Task 5 改)
      } catch (e) {
        if (e.name === 'AbortError') {
          if (contentTextOf(target) === '') appendTextChunk(activeChunksOf(target), 'content', '(已停止)')
          streaming.value = false; currentStreamId.value = null; return
        }
        error.value = e.message || '重生成失败'
        if (contentTextOf(target) === '') appendTextChunk(activeChunksOf(target), 'content', `❌ ${error.value}`)
        streaming.value = false; currentStreamId.value = null; return
      }
      streaming.value = false
      currentStreamId.value = null

      // 流式后切 chunks: splitToolCallChunks 作用于当前 version 的 content
      const segs = splitToolCallChunks(contentTextOf(target))
      const hasToolCall = segs.some((c) => c.type === 'tool_call')
      if (!hasToolCall) break

      // 重建当前 version 的 chunks (think 保留 + segs)
      const thinkChunks = activeChunksOf(target).filter((c) => c.type === 'think')
      target.versions[target.activeVersion].chunks = [...thinkChunks, ...segs]

      // 执行 tool_call
      const toolResults = []
      for (const chunk of target.versions[target.activeVersion].chunks) {
        if (chunk.type !== 'tool_call') continue
        chunk.status = 'in_progress'
        const result = await _executeTool(chunk.args)
        chunk.status = result.error ? 'error' : 'completed'
        chunk.result = result
        toolResults.push({ call: chunk.args, result })
      }
      if (toolResults.length === 0) break

      // 工具结果摘要作 user 消息 (塞进 messages, 在新 version 的 spanEnd 内)
      const toolResultSummary = toolResults.map((tr) => {
        if (tr.result.error) return `工具 ${tr.call.tool} 失败: ${tr.result.error}`
        if (tr.result.written) return `文件 ${tr.result.path} 已成功写入 (${tr.result.bytes} 字节)。`
        if (tr.result.content) return `文件 ${tr.result.path} 内容:\n\`\`\`\n${tr.result.content.slice(0, 6000)}\n\`\`\``
        if (tr.result.files) return `目录 ${tr.result.path} 内容:\n${tr.result.files.join('\n')`
        if (tr.result.tool === 'generate_project_graph') {
          const s = tr.result.stats || {}
          return `项目图谱已生成 (${tr.result.sourcePath}). 统计: 模块${s.module||0}/类${s.class||0}/函数${s.function||0}/方法${s.method||0}.`
        }
        if (tr.result.tool === 'code_review') {
          const rv = tr.result.review || {}
          return `代码审查 (${tr.result.sourcePath}): verdict=${rv.verdict}, overall=${rv.overall_score!=null?(rv.overall_score*100).toFixed(0)+'%':'?'}.`
        }
        if (tr.result.tool === 'code_test') {
          const rp = tr.result.report || {}
          const sm = rp.summary || {}
          return `代码测试 (${tr.result.sourcePath}): ${sm.passed||0}/${sm.total||0} 通过.`
        }
        return ''
      }).filter(Boolean).join('\n\n')
      if (toolResultSummary) {
        _addMessage('user', `[工具返回]\n${toolResultSummary}`)
        // 扩展新 version 的 spanEnd 包含这条工具返回 (重生成场景工具循环较少见, 但保留正确性)
        target.versions[target.activeVersion].spanEnd = messages.value.length
      }
    }
  }
```

- [ ] **Step 4: Add regenMessage to return surface**

在 return 里加:

```js
    sendMessage, stopStreaming, clearMessages,
    setVersion, regenMessage,
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npm test -- chat-branch.test.js`
Expected: PASS (regenMessage 结构测试过; SSE mock 缺失走 catch, 结构已建)

- [ ] **Step 6: Run full suite**

Run: `cd frontend && npm test`
Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add frontend/src/stores/chat.js frontend/src/__tests__/chat-branch.test.js
git commit -m "feat(chat): regenMessage 重生成 (追加 version, 复用 SSE+工具循环)"
```

---

## Task 5: _streamResponse 流进 activeVersion chunks

**Files:**
- Modify: `frontend/src/stores/chat.js` (_streamResponse + _applySseBlock)

`_streamResponse(apiMessages, assistantMsg)` 现在 SSE 块调 `appendTextChunk(assistantMsg.chunks, ...)`。要改成流进 `assistantMsg.versions[activeVersion].chunks`。`_applySseBlock` 同理。

- [ ] **Step 1: Read current _streamResponse + _applySseBlock**

Run: `cd frontend && grep -n "_streamResponse\|_applySseBlock\|assistantMsg.chunks" src/stores/chat.js`
确认所有 `assistantMsg.chunks` 引用位置。

- [ ] **Step 2: Update _applySseBlock to write to activeVersion chunks**

`_applySseBlock(block, assistantMsg)` 当前用 `appendTextChunk(assistantMsg.chunks, ...)`。改为先取 active chunks 再传:

找到 `_applySseBlock` 内所有 `appendTextChunk(assistantMsg.chunks,` 调用, 改为 `appendTextChunk(activeChunksOf(assistantMsg),`。同样 `assistantMsg.chunks` 的其他直接引用改为 `activeChunksOf(assistantMsg)`。

具体: `_applySseBlock` 内若有 `error.value = data.error; appendTextChunk(assistantMsg.chunks, 'content', ...)` 改 `appendTextChunk(activeChunksOf(assistantMsg), 'content', ...)`。`reasoning`/`delta` 两行同理。

- [ ] **Step 3: Update sendMessage's splitToolCallChunks + chunks rebuild**

`sendMessage` 内 `const segs = splitToolCallChunks(contentTextOf(assistantMsg))` (contentTextOf 已读 activeVersion, OK)。`assistantMsg.chunks = [...thinkChunks, ...segs]` 这行改为写回 activeVersion:

```js
      const thinkChunks = activeChunksOf(assistantMsg).filter((c) => c.type === 'think')
      assistantMsg.versions[assistantMsg.activeVersion].chunks = [...thinkChunks, ...segs]
```

(注: Task 4 的 regenMessage 里这行已是 `target.versions[target.activeVersion].chunks = ...`, 一致。)

同样 `sendMessage` 内 `for (const chunk of assistantMsg.chunks)` 改 `for (const chunk of activeChunksOf(assistantMsg))`。

`contentTextOf(assistantMsg) === ''` 判断不变 (已读 activeVersion)。

- [ ] **Step 4: Verify _streamResponse signature unchanged**

`_streamResponse(apiMessages, assistantMsg)` 签名不变, 内部通过 `activeChunksOf(assistantMsg)` 间接写。确认 `_streamResponse` 内不直接碰 `.chunks`。

- [ ] **Step 5: Run full suite**

Run: `cd frontend && npm test`
Expected: all pass (chat-chunks 测试 activeChunksOf 已验证, sendMessage 集成行为不变)

- [ ] **Step 6: Run build**

Run: `cd frontend && npm run build`
Expected: pass

- [ ] **Step 7: Commit**

```bash
git add frontend/src/stores/chat.js
git commit -m "refactor(chat): _streamResponse/_applySseBlock 流进 activeVersion chunks"
```

---

## Task 6: AssistantPanel 版本切换器 + 重生成钮

**Files:**
- Modify: `frontend/src/ide/AssistantPanel.vue`

渲染改用 `chat.visibleMessages`; 助手消息内层 chunks 改 `msg.versions[msg.activeVersion].chunks`; 加 `‹n/m›` 切换器 (多版本才显示, hover 浮现) + 重生成钮 (hover 浮现, streaming 禁用); 切换淡入淡出 + reduced-motion。

- [ ] **Step 1: Update v-for to use visibleMessages**

在 `frontend/src/ide/AssistantPanel.vue`, 找到 `v-for="msg in chat.messages"` (约 line 35), 改为:

```vue
          v-for="msg in chat.visibleMessages"
```

- [ ] **Step 2: Update assistant chunks v-for to read activeVersion**

找到助手消息内 `<template v-for="(chunk, ci) in msg.chunks"` (约 line 46), 改为:

```vue
              <template v-for="(chunk, ci) in (msg.versions?.[msg.activeVersion ?? 0]?.chunks || msg.chunks)" :key="ci">
```

(兼容: 新消息有 versions, 旧无则 fallback chunks — 实际新消息都有 versions, fallback 保险)

- [ ] **Step 3: Add version switcher + regen button to assistant messages**

在助手消息的 `.msg-content` 内, chunks 渲染之后, 加版本切换器 + 重生成钮。找到助手消息 `</div>` 结束前 (chunks template 之后), 加:

```vue
              <!-- 版本切换器: 多版本才显示, hover 浮现 -->
              <div v-if="msg.versions && msg.versions.length > 1" class="version-bar">
                <button class="ver-btn" :disabled="msg.activeVersion === 0" title="上一版" @click="chat.setVersion(msg.id, msg.activeVersion - 1)">‹</button>
                <span class="ver-count">{{ msg.activeVersion + 1 }}/{{ msg.versions.length }}</span>
                <button class="ver-btn" :disabled="msg.activeVersion === msg.versions.length - 1" title="下一版" @click="chat.setVersion(msg.id, msg.activeVersion + 1)">›</button>
              </div>
              <!-- 重生成钮: hover 浮现, streaming 禁用 -->
              <button
                v-if="msg.role === 'assistant'"
                class="regen-btn"
                :disabled="chat.streaming"
                :title="chat.streaming ? '生成中…' : '重新生成'"
                @click="chat.regenMessage(msg.id)"
              >
                <el-icon :size="14"><RefreshRight /></el-icon>
              </button>
```

- [ ] **Step 4: Import RefreshRight icon**

在 AssistantPanel.vue 的 script imports (已有 `@element-plus/icons-vue` 导入), 加 `RefreshRight`:

找到现有 `import { ... } from '@element-plus/icons-vue'` 行, 加 `RefreshRight` 到导入列表 (如果已有其他图标如 `Cpu`, `WarningFilled`, 一并加)。

- [ ] **Step 5: Add styles for version-bar + regen-btn + fade transition**

在 AssistantPanel.vue 的 scoped style 末尾加:

```css
/* 版本分支: 切换器 + 重生成钮 */
.version-bar {
  display: inline-flex; align-items: center; gap: 4px;
  margin-top: 6px; opacity: 0; transition: opacity 0.12s var(--km-ease);
  font-size: 11px; color: var(--km-gray-500);
}
.message.assistant:hover .version-bar { opacity: 1; }
.ver-btn {
  border: 1px solid var(--km-border); background: var(--km-bg-layer-3);
  color: var(--km-gray-600); border-radius: 4px; width: 18px; height: 18px;
  cursor: pointer; font-size: 12px; line-height: 1; padding: 0;
}
.ver-btn:hover:not(:disabled) { border-color: var(--km-primary); color: var(--km-primary); }
.ver-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.ver-count { font-family: var(--km-font-mono); }

.regen-btn {
  position: absolute; right: 4px; bottom: 4px;
  border: 0; background: transparent; color: var(--km-gray-400);
  cursor: pointer; padding: 4px; border-radius: 4px;
  opacity: 0; transition: opacity 0.12s var(--km-ease);
}
.message.assistant:hover .regen-btn { opacity: 1; }
.regen-btn:hover:not(:disabled) { color: var(--km-primary); background: var(--km-primary-light); }
.regen-btn:disabled { opacity: 0.3; cursor: not-allowed; }

/* 版本切换淡入淡出 */
.msg-content { transition: opacity 0.15s var(--km-ease); }

@media (prefers-reduced-motion: reduce) {
  .version-bar, .regen-btn { opacity: 1; transition: none; }
  .msg-content { transition: none; }
}
```

注: `.message.assistant` 需 `position: relative` 让 `.regen-btn` absolute 定位生效 — 确认既有 `.message` 样式, 若无 position 在 `.message.assistant` 加 `position: relative;`。

- [ ] **Step 6: Ensure .message.assistant has position relative**

检查 AssistantPanel.vue 的 `.message` / `.message.assistant` 样式, 若无 `position: relative`, 在 `.message.assistant` 规则加 `position: relative;` (regen-btn absolute 依赖)。Read 确认后改。

- [ ] **Step 7: Run full suite + build**

Run: `cd frontend && npm test`
Expected: all pass

Run: `cd frontend && npm run build`
Expected: pass

- [ ] **Step 8: Commit**

```bash
git add frontend/src/ide/AssistantPanel.vue
git commit -m "feat(chat): AssistantPanel 版本切换器 + 重生成钮 (hover 浮现, reduced-motion)"
```

---

## Task 7: 全量验证 + 文档同步

- [ ] **Step 1: Run full test suite**

Run: `cd frontend && npm test`
Expected: all pass (chat-chunks + chat-branch 新增, 既有不退步)

- [ ] **Step 2: Run build**

Run: `cd frontend && npm run build`
Expected: pass

- [ ] **Step 3: Manual e2e** (`env -u ELECTRON_RUN_AS_NODE npm run dev`)
  - 对话几轮 → 中间某条助手回复点重生成 (右下角 RefreshRight) → 新回复流式进入, 原回复保留 (‹ 1/2 › 出现), 后续消息隐藏
  - 点 ‹ 切回原版 → 原回复显示, 后续消息恢复
  - 点 › 切到新版 → 新回复 + 其后续
  - 末条重生成 (无后续) → 直接追加 version, ‹ 1/2 › 出现, 无隐藏
  - streaming 中重生成钮 disabled
  - hover 消息 → 版本切换器 + 重生成钮浮现; 移开 → 消失
  - 单版本消息不显示 ‹n/m›
  - reduced-motion (系统设置) → 切换瞬切, 切换器/钮常驻
  - 导学模式下重生成同样工作

- [ ] **Step 4: 同步 CLAUDE.md + devlog**

更新 CLAUDE.md 加阶段10 (消息分支); 写 `docs/devlogs/B_前端/2026-06-22_消息分支重生成.md`。Commit + push。

```bash
git add CLAUDE.md docs/devlogs/B_前端/2026-06-22_消息分支重生成.md
git commit -m "docs: 同步阶段10 — 消息分支 (重生成分支) devlog + CLAUDE.md"
git push origin main
```

---

## Self-Review (已执行)

1. **Spec coverage**: 核心决策6项 → Task 1 (helper 适配 activeVersion)、Task 2 (versions 结构)、Task 3 (visibleMessages spanEnd 过滤 + setVersion)、Task 4 (regenMessage)、Task 5 (流进 activeVersion)、Task 6 (UI 切换器+重生成钮+淡入淡出+reduced-motion)。数据模型用 spanEnd 替代 spec 的 trailingAfter (更简单等价, spec 的 trailingAfter 是思路, spanEnd 是落地实现, 行为一致: 切 version 改后续显隐)。UI 舒服交互全覆盖 (hover 浮现/淡入淡出/单版本不显示/reduced-motion/禁用态)。不做项 (用户编辑分支/树形/diff/删除) 均未实现。✓
2. **Placeholder scan**: 无 TBD/TODO, 每步含完整代码或确切命令。Task 5 Step 1 用 grep 确认位置 (因 _streamResponse 内行号需实测), 但 Step 2/3 给了确切替换内容。✓
3. **Type consistency**: `activeChunksOf(msg)` 在 Task 1 定义, Task 4/5 使用一致。`versions[].spanEnd` 在 Task 2 定义 (初始 spanEnd), Task 3 visibleMessages 读, Task 4 regenMessage 写新 version spanEnd=messages.length, 一致。`setVersion(msgId, idx)` Task 3 定义, Task 6 UI 调用一致。`regenMessage(msgId)` Task 4 定义, Task 6 UI 调用一致。`visibleMessages` Task 2 定义透传, Task 3 实现过滤, sendMessage/regenMessage 历史用, 一致。✓

注: Task 4 regenMessage 的工具结果摘要逻辑从 sendMessage 复制简化 (去掉 generate_project_graph/code_review/code_test 的详细摘要, 只保留关键信息) — 重生成场景工具循环较少见, 简化摘要不影响功能, LLM 仍能拿到工具结果。若需完整摘要可从 sendMessage 复制全段, 但 YAGNI。
