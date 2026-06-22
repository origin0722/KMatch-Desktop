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
