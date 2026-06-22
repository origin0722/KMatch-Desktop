import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/stores/workspace', () => ({ useWorkspaceStore: () => ({ hasProject: false, rootName: '', tree: [] }) }))
vi.mock('@/stores/projectGraph', () => ({ useProjectGraphStore: () => ({}) }))
vi.mock('@/stores/aiSettings', () => ({
  useAiSettingsStore: () => ({ permissionFor: () => 'allow', formatEnabledMemories: () => '', reasoningInstruction: () => '' }),
  TOOL_PERMISSION: { ALLOW: 'allow', ASK: 'ask', DENY: 'deny' },
}))

const { useChatStore } = await import('@/stores/chat')

describe('chat 分支 — visibleMessages 存在', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('visibleMessages 默认空数组', () => {
    const chat = useChatStore()
    expect(chat.visibleMessages).toEqual([])
  })

  it('visibleMessages 是数组', () => {
    const chat = useChatStore()
    expect(Array.isArray(chat.visibleMessages)).toBe(true)
  })
})
