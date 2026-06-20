/**
 * AI 助手对话 Store — 阶段2
 *
 * 管理消息列表、流式对话、对话上下文。
 * SSE 流式接收后端 /api/chat/completions (DeepSeek, OpenAI 兼容)。
 */
import { ref, computed } from 'vue'
import { defineStore } from 'pinia'

// 默认系统提示词 — IDE 编程助手定位
const SYSTEM_PROMPT = {
  role: 'system',
  content:
    '你是 KMatch IDE 的 AI 编程助手，帮助用户阅读、理解、修改项目代码。\n'
    + '你可以：解释代码逻辑、提供改进建议、帮助调试、生成代码片段。\n'
    + '回答用中文，代码块标注语言。保持回答简洁。',
}

export const useChatStore = defineStore('chat', () => {
  // ============================================================
  // 状态
  // ============================================================
  const messages = ref([])           // [{role, content, id, timestamp}]
  const streaming = ref(false)       // 正在接收流式回复
  const currentStreamId = ref(null)  // 当前流式消息 ID
  const error = ref(null)
  const abortController = ref(null)

  // ============================================================
  // 计算属性
  // ============================================================
  const hasMessages = computed(() => messages.value.length > 0)
  const lastMessage = computed(() => messages.value[messages.value.length - 1] || null)

  // ============================================================
  // 内部方法
  // ============================================================
  let _idCounter = 0
  function _nextId() {
    return `msg_${Date.now()}_${++_idCounter}`
  }

  function _addMessage(role, content) {
    const msg = {
      id: _nextId(),
      role,
      content,
      timestamp: new Date().toISOString(),
    }
    messages.value.push(msg)
    return msg
  }

  // ============================================================
  // Actions
  // ============================================================

  /** 发送用户消息并获取 AI 回复 (SSE 流式) */
  async function sendMessage(userContent) {
    if (streaming.value || !userContent.trim()) return

    error.value = null

    // 添加用户消息
    _addMessage('user', userContent.trim())

    // 构建 API 消息列表 (系统提示词 + 对话历史)
    const apiMessages = [
      SYSTEM_PROMPT,
      ...messages.value.map((m) => ({ role: m.role, content: m.content })),
    ]

    // 添加助手占位消息
    const assistantMsg = _addMessage('assistant', '')
    currentStreamId.value = assistantMsg.id
    streaming.value = true

    // 创建 AbortController
    abortController.value = new AbortController()

    try {
      let resp
      try {
        resp = await fetch('/api/chat/completions', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ messages: apiMessages, stream: true, max_tokens: 4096 }),
          signal: abortController.value.signal,
        })
      } catch (e) {
        if (e.name === 'AbortError') {
          // 用户手动停止
          if (assistantMsg.content === '') {
            assistantMsg.content = '(已停止)'
          }
          return
        }
        throw e
      }

      if (!resp.ok) {
        const text = await resp.text().catch(() => '')
        throw new Error(text || `HTTP ${resp.status}`)
      }

      // 读取 SSE 流
      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const blocks = buffer.split('\n\n')
        buffer = blocks.pop()

        for (const block of blocks) {
          if (!block.trim()) continue
          const dataStr = block.match(/^data:\s*(.+)$/m)?.[1]
          if (!dataStr) continue

          // 流结束标记
          if (dataStr === '[DONE]') continue

          try {
            const data = JSON.parse(dataStr)
            if (data.error) {
              error.value = data.error
              // 在消息中显示错误
              if (assistantMsg.content === '') {
                assistantMsg.content = `❌ 错误: ${data.error}`
              }
              return
            }
            if (data.delta) {
              assistantMsg.content += data.delta
            }
          } catch {
            // 解析失败的行静默跳过
          }
        }
      }
    } catch (e) {
      if (e.name === 'AbortError') {
        if (assistantMsg.content === '') {
          assistantMsg.content = '(已停止)'
        }
        return
      }
      const msg = e.response?.data?.detail || e.message || '对话请求失败'
      error.value = msg
      if (assistantMsg.content === '') {
        assistantMsg.content = `❌ ${msg}`
      }
    } finally {
      streaming.value = false
      currentStreamId.value = null
      abortController.value = null
    }
  }

  /** 停止当前流式回复 */
  function stopStreaming() {
    abortController.value?.abort()
  }

  /** 清空对话历史 */
  function clearMessages() {
    abortController.value?.abort()
    messages.value = []
    streaming.value = false
    currentStreamId.value = null
    error.value = null
  }

  return {
    messages,
    streaming,
    currentStreamId,
    error,
    hasMessages,
    lastMessage,
    sendMessage,
    stopStreaming,
    clearMessages,
  }
})
