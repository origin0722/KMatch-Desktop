/**
 * AI 助手 UX 修复回归 (v1.3.2 后批次):
 *  - editUserMessage: 编辑用户消息 → 文本替换 + 截断其后 + 重走助手回合 (附件保留)
 *  - stopStreaming: 未决审批按"中止"解开 (stopped 标记, 区别于用户主动拒绝)
 *  - AbortError: 部分输出后停止 → _stopped 角标 (正文不混入"(已停止)"); 空输出仍文本兜底
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

// streamChat 形状由各用例 vi.doMock 定制; 与 chat-attachments.test.js 同一模式 (resetModules + 动态 import)
vi.mock('@/stores/workspace', () => ({ useWorkspaceStore: () => ({ hasProject: false, rootName: '', tree: [] }) }))
vi.mock('@/stores/projectGraph', () => ({ useProjectGraphStore: () => ({}) }))

function makeAbortError() {
  const e = new Error('aborted')
  e.name = 'AbortError'
  return e
}

describe('chat UX — editUserMessage (编辑重发)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.resetModules()
  })

  it('编辑用户消息: 文本替换 + 其后消息截断 + 助手回合基于编辑后历史', async () => {
    const captured = []
    vi.doMock('@/ide/chat/useChatStream', () => ({
      streamChat: async ({ body }) => { captured.push(body) },
    }))
    const { useChatStore } = await import('@/stores/chat')
    const chat = useChatStore()

    await chat.sendMessage('第一问')                       // user + assistant
    const userMsg = chat.messages.find((m) => m.role === 'user')
    const assistantAfter = chat.messages.filter((m) => m.role === 'assistant')
    expect(assistantAfter.length).toBeGreaterThanOrEqual(1)

    await chat.editUserMessage(userMsg.id, '第一问（改：换个角度）')

    // 文本已替换
    expect(chat.messages.find((m) => m.id === userMsg.id).chunks[0].content)
      .toBe('第一问（改：换个角度）')
    // 其后消息被截断: 旧助手回复不在, 新助手回合追加
    const assistants = chat.messages.filter((m) => m.role === 'assistant')
    expect(assistants.length).toBe(1) // 旧回复被截断, 只剩编辑重发的新回合
    // 新回合 API 历史以编辑后的用户消息收尾
    const last = captured.at(-1).messages.at(-1)
    expect(last.role).toBe('user')
    expect(last.content).toBe('第一问（改：换个角度）')
  })

  it('带附件的多模态消息: 编辑只换 text 段, 附件保留', async () => {
    vi.doMock('@/ide/chat/useChatStream', () => ({ streamChat: async () => {} }))
    const { useChatStore } = await import('@/stores/chat')
    const chat = useChatStore()

    chat.messages.push({
      id: 'msg_u_att', role: 'user',
      content: [
        { type: 'text', text: '看这张图' },
        { type: 'image_url', image_url: { url: 'data:image/png;base64,AAAA' } },
      ],
      _attachments: [{ id: 'a1', name: 'a.png' }],
      chunks: [], timestamp: '2026-01-01',
    })
    await chat.editUserMessage('msg_u_att', '看这两张图')

    const m = chat.messages.find((x) => x.id === 'msg_u_att')
    expect(m.content[0]).toEqual({ type: 'text', text: '看这两张图' })
    expect(m.content[1].type).toBe('image_url')
    expect(m._attachments).toHaveLength(1)
  })

  it('isBusy 时静默 no-op (流中不允许编辑重发)', async () => {
    vi.doMock('@/ide/chat/useChatStream', () => ({ streamChat: async () => {} }))
    const { useChatStore } = await import('@/stores/chat')
    const chat = useChatStore()
    await chat.sendMessage('q')
    chat.streaming = true
    const before = chat.messages.length
    await chat.editUserMessage(chat.messages[0].id, '改')
    expect(chat.messages.length).toBe(before)
    expect(chat.messages[0].chunks[0].content).toBe('q')
  })
})

describe('chat UX — 停止 ≠ 拒绝写入 + 中断标记', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.resetModules()
  })

  it('stopStreaming 解开未决审批时带 stopped 标记 (非"拒绝")', async () => {
    const { useChatStore } = await import('@/stores/chat')
    const chat = useChatStore()
    const resolve = vi.fn()
    // 直接构造审批门挂起态 (形状对齐 _requestApproval)
    chat.pendingApproval = {
      id: 'appr_1', call: { tool: 'write_file', path: 'a.py', content: 'x' },
      content: 'x', safetyIssues: [], safe: true, checked: true, safetyError: null,
      resolve,
    }
    chat.stopStreaming()
    expect(resolve).toHaveBeenCalledWith({ approved: false, stopped: true })
    expect(chat.pendingApproval).toBe(null)
  })

  it('部分输出后停止: _stopped 角标, 正文保留且不混入"(已停止)"', async () => {
    vi.doMock('@/ide/chat/useChatStream', () => ({
      streamChat: async ({ onBlock }) => {
        onBlock(`data: ${JSON.stringify({ delta: '已经生成了一半的内容' })}`)
        throw makeAbortError()
      },
    }))
    const { useChatStore } = await import('@/stores/chat')
    const chat = useChatStore()
    await chat.sendMessage('q')

    const assistant = chat.messages.filter((m) => m.role === 'assistant').at(-1)
    expect(assistant._stopped).toBe(true)
    const text = assistant.versions[0].chunks.map((c) => c.content || '').join('')
    expect(text).toContain('已经生成了一半的内容')
    expect(text).not.toContain('(已停止)')
  })

  it('空输出即停止: 仍以"(已停止)"文本兜底 (不产生空消息)', async () => {
    vi.doMock('@/ide/chat/useChatStream', () => ({
      streamChat: async () => { throw makeAbortError() },
    }))
    const { useChatStore } = await import('@/stores/chat')
    const chat = useChatStore()
    await chat.sendMessage('q')

    const assistant = chat.messages.filter((m) => m.role === 'assistant').at(-1)
    const text = assistant.versions[0].chunks.map((c) => c.content || '').join('')
    expect(text).toContain('(已停止)')
  })
})
