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

describe('sendMessage multimodal (Spec A)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    // 必需: 清模块缓存, 否则上方 describe 已缓存的 @/stores/chat 绑定了真实 streamChat,
    // vi.doMock 不会生效 (与 chat-ai-settings.test.js 同一模式)。
    vi.resetModules()
  })

  it('attachments 存在时 user message content 是 OpenAI 数组形式', async () => {
    const captured = { body: null }
    vi.doMock('@/ide/chat/useChatStream', () => ({
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
    // body.messages = [systemMsg, ...historyMsgs]; 首条用户消息即最后一条 → at(-1)
    // (spec 原写 at(-2) 指向 systemMsg, 已据代码轨迹修正)
    const last = captured.body.messages.at(-1)
    expect(Array.isArray(last.content)).toBe(true)
    expect(last.content[0]).toEqual({ type: 'text', text: '看看' })
    expect(last.content[1].type).toBe('image_url')
    expect(last.content[1].image_url.url).toContain('data:image/png;base64,')
    expect(chat.pendingAttachments).toHaveLength(0)   // 已清空
  })

  it('无附件时 user content 仍是 string', async () => {
    const captured = { body: null }
    vi.doMock('@/ide/chat/useChatStream', () => ({
      streamChat: async ({ body }) => { captured.body = body },
    }))
    const { useChatStore } = await import('@/stores/chat')
    const chat = useChatStore()
    await chat.sendMessage('hi')
    const last = captured.body.messages.at(-1)
    expect(typeof last.content).toBe('string')
  })
})
