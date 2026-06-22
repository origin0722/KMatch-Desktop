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
    pushUser(chat, 'q1')                          // 0
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

describe('chat 分支 — regenMessage', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('regenMessage 追加新 version + activeVersion 指向新 + 旧版 spanEnd 锁定', async () => {
    const chat = useChatStore()
    pushUser(chat, 'q1')                          // 0
    const a = pushAssistant(chat, { versions: [{ chunks: [{ type: 'content', content: 'old' }], spanEnd: Infinity }] }) // 1
    pushUser(chat, 'q2')                          // 2 — trailing under old version
    // mock _streamResponse 不实际请求: regenMessage 应建 version 但 SSE 会抛 (无 window.api.http mock)
    try {
      await chat.regenMessage(a.id)
    } catch { /* SSE mock 缺失会抛, 忽略 — 只验结构 */ }
    const updated = chat.messages.find((m) => m.id === a.id)
    expect(updated.versions.length).toBe(2)
    expect(updated.activeVersion).toBe(1) // 指向新
    // 新版无 trailing → spanEnd = targetIdx+1 (=2), 隐藏 q2 (index2 >= 2)
    expect(updated.versions[1].spanEnd).toBe(2)
    // 旧版 spanEnd 锁定为 regen 时的 messages 长度 (=3: q1, a, q2)
    expect(updated.versions[0].spanEnd).toBe(3)
  })

  it('regenMessage 后切回旧版, 旧版 trailing (q2) 可见', async () => {
    const chat = useChatStore()
    pushUser(chat, 'q1')                          // 0
    const a = pushAssistant(chat, { versions: [{ chunks: [{ type: 'content', content: 'old' }], spanEnd: Infinity }] }) // 1
    pushUser(chat, 'q2')                          // 2
    try { await chat.regenMessage(a.id) } catch { /* ignore */ }
    // spanEnd 语义: 新版 (无 trailing) = targetIdx+1 (=2); 旧版 (有 trailing q2) = messages.length (=3)
    const updated = chat.messages.find((m) => m.id === a.id)
    expect(updated.versions[1].spanEnd).toBe(2) // 新版无 trailing → 自己 index+1
    expect(updated.versions[0].spanEnd).toBe(3) // 旧版 trailing 到 q2 → length
    // 新版视角: q2 index2 >= 新版 spanEnd 2 → 隐藏
    chat.setVersion(a.id, 1) // 确保新版
    expect(chat.visibleMessages.length).toBe(2) // q1 + a新版 (q2 隐藏)
    chat.setVersion(a.id, 0) // 切旧版
    expect(chat.visibleMessages.length).toBe(3) // q1 + a旧版 + q2
  })
})
