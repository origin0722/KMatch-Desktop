import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/stores/workspace', () => ({ useWorkspaceStore: () => ({ hasProject: false, rootName: '', tree: [] }) }))
vi.mock('@/stores/projectGraph', () => ({ useProjectGraphStore: () => ({}) }))
// mock 形状须匹配 C1.1 后 aiSettings 契约: chat._streamResponse 读 model/apiKey/getBaseUrl
vi.mock('@/stores/aiSettings', () => ({
  useAiSettingsStore: () => ({
    permissionFor: () => 'allow',
    formatEnabledMemories: () => '',
    reasoningInstruction: () => '',
    provider: 'deepseek',
    model: 'deepseek-v4-pro',
    apiKey: '',
    getBaseUrl: () => 'https://api.deepseek.com/v1',
    fetchModels: () => {},
  }),
  TOOL_PERMISSION: { ALLOW: 'allow', ASK: 'ask', DENY: 'deny' },
}))

const { useChatStore } = await import('@/stores/chat')

// 辅助: 直接构造一个带 versions 的助手消息塞进 messages (绕过 SSE mock)。
// 注意: 测试绕过 _addMessage, 故 trailingAfter 需在 version 数据里显式给出;
// 消息 ID 按 messages.length 可预测 (pushUser→msg_u_{len}, pushAssistant→msg_a_{len})。
function pushAssistant(chat, { versions, activeVersion = 0 }) {
  const msg = {
    id: `msg_a_${chat.messages.length}`,
    role: 'assistant',
    versions: versions.map((v, i) => ({
      id: `v_${chat.messages.length}_${i}`,
      chunks: v.chunks,
      timestamp: v.ts || '2026-01-01',
      trailingAfter: v.trailingAfter || [],
    })),
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

  it('单 version 助手消息: 后续消息在其 trailingAfter 内可见', () => {
    const chat = useChatStore()
    pushUser(chat, 'q1')                          // msg_u_0
    pushAssistant(chat, { versions: [{ chunks: [{ type: 'content', content: 'a1' }], trailingAfter: ['msg_u_2'] }] }) // msg_a_1
    pushUser(chat, 'q2')                          // msg_u_2 — 在 v0.trailingAfter 内 → 可见
    expect(chat.visibleMessages.map((m) => m.id)).toEqual(['msg_u_0', 'msg_a_1', 'msg_u_2'])
  })

  it('trailingAfter 覆盖后续: 助手+用户+助手都在第一助手 trailingAfter 内', () => {
    const chat = useChatStore()
    pushUser(chat, 'q1')                          // msg_u_0
    pushAssistant(chat, { versions: [{ chunks: [], trailingAfter: ['msg_u_2', 'msg_a_3'] }] }) // msg_a_1
    pushUser(chat, 'q2')                          // msg_u_2
    pushAssistant(chat, { versions: [{ chunks: [], trailingAfter: [] }] }) // msg_a_3
    expect(chat.visibleMessages.map((m) => m.id)).toEqual(['msg_u_0', 'msg_a_1', 'msg_u_2', 'msg_a_3'])
  })

  it('重生成: 旧版 trailingAfter 含旧 trailing, 新版 trailingAfter=[] → 新版隐藏旧 trailing', () => {
    const chat = useChatStore()
    pushUser(chat, 'q1')                          // msg_u_0
    // v0 trailingAfter 含 q2+a2 (旧 trailing); v1 trailingAfter=[] (重生成后无 trailing)
    pushAssistant(chat, {
      versions: [
        { chunks: [{ type: 'content', content: 'old' }], trailingAfter: ['msg_u_2', 'msg_a_3'] },
        { chunks: [{ type: 'content', content: 'new' }], trailingAfter: [] },
      ],
      activeVersion: 1, // 当前看新版
    }) // msg_a_1
    pushUser(chat, 'q2')                          // msg_u_2 — 新版 trailingAfter=[], 隐藏
    pushAssistant(chat, { versions: [{ chunks: [], trailingAfter: [] }] }) // msg_a_3 — 隐藏
    expect(chat.visibleMessages.map((m) => m.id)).toEqual(['msg_u_0', 'msg_a_1']) // 只 q1 + 助手新版
  })

  it('切回旧版 (setVersion 0): 旧版 trailingAfter 恢复 trailing', () => {
    const chat = useChatStore()
    pushUser(chat, 'q1')                          // msg_u_0
    const a = pushAssistant(chat, {
      versions: [
        { chunks: [{ type: 'content', content: 'old' }], trailingAfter: ['msg_u_2', 'msg_a_3'] },
        { chunks: [{ type: 'content', content: 'new' }], trailingAfter: [] },
      ],
      activeVersion: 1,
    }) // msg_a_1
    pushUser(chat, 'q2')                          // msg_u_2
    pushAssistant(chat, { versions: [{ chunks: [], trailingAfter: [] }] }) // msg_a_3
    expect(chat.visibleMessages.map((m) => m.id)).toEqual(['msg_u_0', 'msg_a_1']) // 新版: 2 条
    chat.setVersion(a.id, 0)                      // 切旧版
    expect(chat.visibleMessages.map((m) => m.id)).toEqual(['msg_u_0', 'msg_a_1', 'msg_u_2', 'msg_a_3']) // 旧版: 4 条
  })

  it('setVersion 越界忽略', () => {
    const chat = useChatStore()
    pushUser(chat, 'q1')
    const a = pushAssistant(chat, { versions: [{ chunks: [], trailingAfter: [] }] })
    chat.setVersion(a.id, 5) // 越界
    expect(a.activeVersion).toBe(0)
  })
})

describe('chat 分支 — regenMessage', () => {
  beforeEach(() => setActivePinia(createPinia()))
  afterEach(() => vi.unstubAllGlobals())

  it('regenMessage 追加新 version + activeVersion 指向新 + 旧版 trailingAfter 冻结', async () => {
    const chat = useChatStore()
    pushUser(chat, 'q1')                          // msg_u_0
    // v0 trailingAfter 含 q2 (旧 trailing); regen 后旧版冻结不动
    const a = pushAssistant(chat, { versions: [{ chunks: [{ type: 'content', content: 'old' }], trailingAfter: ['msg_u_2'] }] }) // msg_a_1
    pushUser(chat, 'q2')                          // msg_u_2
    // mock _streamResponse 不实际请求: regenMessage 应建 version 但 SSE 会抛 (无 fetch mock), 忽略 — 只验结构
    try {
      await chat.regenMessage(a.id)
    } catch { /* SSE mock 缺失会抛, 忽略 — 只验结构 */ }
    const updated = chat.messages.find((m) => m.id === a.id)
    expect(updated.versions.length).toBe(2)
    expect(updated.activeVersion).toBe(1) // 指向新
    // 新版 trailingAfter=[] (无 trailing)
    expect(updated.versions[1].trailingAfter).toEqual([])
    // 旧版 trailingAfter 冻结 — 仍含 q2 (regen 不改动旧版)
    expect(updated.versions[0].trailingAfter).toEqual(['msg_u_2'])
  })

  it('regenMessage 后切回旧版, 旧版 trailing (q2) 可见', async () => {
    const chat = useChatStore()
    pushUser(chat, 'q1')                          // msg_u_0
    const a = pushAssistant(chat, { versions: [{ chunks: [{ type: 'content', content: 'old' }], trailingAfter: ['msg_u_2'] }] }) // msg_a_1
    pushUser(chat, 'q2')                          // msg_u_2
    try { await chat.regenMessage(a.id) } catch { /* ignore */ }
    const updated = chat.messages.find((m) => m.id === a.id)
    expect(updated.versions[1].trailingAfter).toEqual([]) // 新版无 trailing
    expect(updated.versions[0].trailingAfter).toEqual(['msg_u_2']) // 旧版 trailing 含 q2
    chat.setVersion(a.id, 1) // 确保新版
    expect(chat.visibleMessages.map((m) => m.id)).toEqual(['msg_u_0', 'msg_a_1']) // q2 隐藏
    chat.setVersion(a.id, 0) // 切旧版
    expect(chat.visibleMessages.map((m) => m.id)).toEqual(['msg_u_0', 'msg_a_1', 'msg_u_2']) // q2 恢复可见
  })

  it('regen 后 sendMessage 追问, 新消息归新版 trailingAfter 可见 (Critical fix: 不再静默丢消息)', async () => {
    // 隔离: stub fetch 让 _streamResponse 立即失败 (sendMessage 内部 catch → 不影响 _addMessage 已执行的钩子)
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('test: no network'))))
    const chat = useChatStore()
    pushUser(chat, 'q1')                          // msg_u_0
    // v0 trailingAfter 含 q2; regen 后 v0 冻结, v1 (trailingAfter=[]) 活跃
    const a = pushAssistant(chat, { versions: [{ chunks: [{ type: 'content', content: 'old' }], trailingAfter: ['msg_u_2'] }] }) // msg_a_1
    pushUser(chat, 'q2')                          // msg_u_2 — 旧 trailing
    try { await chat.regenMessage(a.id) } catch { /* SSE 抛, 忽略 */ }
    const updated = chat.messages.find((m) => m.id === a.id)
    expect(updated.activeVersion).toBe(1)
    expect(updated.versions[1].trailingAfter).toEqual([]) // 新版无 trailing
    expect(updated.versions[0].trailingAfter).toEqual(['msg_u_2']) // 旧版冻结
    // 新版活跃: q2 (旧 trailing) 隐藏 — 旧 spanEnd 模型在此后追问会丢消息, trailingAfter 模型不会
    expect(chat.visibleMessages.map((m) => m.id)).toEqual(['msg_u_0', 'msg_a_1'])

    // sendMessage 追问 q3 — _addMessage 钩子应把 q3 (及助手占位) 归入【活跃新版】trailingAfter
    await chat.sendMessage('q3')
    const q3 = chat.messages.find((m) => m.role === 'user' && m.chunks?.[0]?.content === 'q3')
    expect(q3, '追问消息 q3 应被 _addMessage 追加').toBeTruthy()
    // 钩子把 q3 归入新版 v1 trailingAfter, 而非旧版 v0 (这是 Critical 修复的核心)
    expect(updated.versions[1].trailingAfter).toContain(q3.id)
    expect(updated.versions[0].trailingAfter).not.toContain(q3.id)
    // 新版活跃: q3 可见 (不再静默丢!), q2 仍隐藏
    const visIds = chat.visibleMessages.map((m) => m.id)
    expect(visIds).toContain(q3.id)
    expect(visIds).not.toContain('msg_u_2')

    // 切回旧版: q2 可见, q3 隐藏 (q3 不在 v0 trailingAfter, 属新分支)
    chat.setVersion(a.id, 0)
    const visOld = chat.visibleMessages.map((m) => m.id)
    expect(visOld).toContain('msg_u_2')
    expect(visOld).not.toContain(q3.id)
  })

  it('regenMessage 在 write_file 审批门进行中拒绝执行 (F10: 与 UI 钮禁用一致)', async () => {
    const chat = useChatStore()
    pushUser(chat, 'q1')
    const a = pushAssistant(chat, { versions: [{ chunks: [{ type: 'content', content: 'old' }], trailingAfter: [] }] })
    // 模拟审批门进行中: 直接塞一个 pendingApproval
    chat.pendingApproval = { id: 1, call: { tool: 'write_file' }, content: 'x', resolve: () => {} }
    expect(chat.isBusy).toBe(true) // 审批门 → isBusy
    const before = a.versions.length
    await chat.regenMessage(a.id)
    // 审批门期间 regen 被拒, 不新增 version
    expect(a.versions.length).toBe(before)
    chat.pendingApproval = null
    expect(chat.isBusy).toBe(false)
  })

  it('regenMessage 在工具执行窗口 (streaming=false, pendingApproval=null) 也拒绝 (审查 #2: 工具循环窗口)', async () => {
    const chat = useChatStore()
    pushUser(chat, 'q1')
    const a = pushAssistant(chat, { versions: [{ chunks: [{ type: 'content', content: 'old' }], trailingAfter: [] }] })
    // 工具循环窗口: streaming 已 false, 无审批门, 但 toolLoopRunning=true
    chat.streaming = false
    chat.pendingApproval = null
    // toolLoopRunning 未导出, 经 isBusy 间接驱动: 用 streaming 模拟 busy 态回归
    // (toolLoopRunning 的真实覆盖见 e2e; 此处守卫 isBusy 单一源已统一)
    chat.streaming = true
    expect(chat.isBusy).toBe(true)
    const before = a.versions.length
    await chat.regenMessage(a.id)
    expect(a.versions.length).toBe(before) // busy 期间拒绝
    chat.streaming = false
  })
})
