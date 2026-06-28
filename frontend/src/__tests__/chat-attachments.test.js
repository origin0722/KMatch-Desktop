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
