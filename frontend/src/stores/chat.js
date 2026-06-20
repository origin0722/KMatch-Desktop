/**
 * AI 助手对话 Store — 阶段3
 *
 * 阶段2: SSE 流式对话
 * 阶段3: 代码上下文注入 + 工具调用 (读文件/列目录)
 *
 * 工具调用流程:
 *   1. 发送消息 (含当前文件上下文 + 工具定义)
 *   2. AI 回复: 纯文本 → 直接展示; 含 <|tool_call|> → 执行工具 → 回传结果 → 继续
 *   3. 最多 3 轮工具循环，防止无限循环
 */
import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { useWorkspaceStore } from '@/stores/workspace'

const MAX_TOOL_ROUNDS = 3

// 可用工具定义
const TOOLS = [
  {
    name: 'read_file',
    description: '读取项目中的文件内容。参数: path (相对路径)。',
    parameters: { path: 'string (相对项目根目录的文件路径)' },
  },
  {
    name: 'list_directory',
    description: '列出目录内容。参数: path (相对路径，默认根目录)。',
    parameters: { path: 'string (可选，默认为项目根目录)' },
  },
]

function buildSystemPrompt(context) {
  let ctxBlock = ''
  if (context) {
    const parts = []
    if (context.projectRoot) {
      parts.push(`- 项目根: ${context.projectRoot}`)
    }
    if (context.activeFile) {
      parts.push(`- 当前打开: ${context.activeFile}`)
    }
    if (context.fileContent) {
      const maxLen = 8000
      const truncated = context.fileContent.length > maxLen
        ? context.fileContent.slice(0, maxLen) + '\n... (内容已截断)'
        : context.fileContent
      parts.push(`- 当前文件内容:\n\`\`\`\n${truncated}\n\`\`\``)
    }
    if (context.fileTree) {
      parts.push(`- 项目文件:\n${context.fileTree}`)
    }
    if (parts.length) {
      ctxBlock = '\n\n## 当前工作区上下文\n' + parts.join('\n')
    }
  }

  const toolBlock = `
## 可用工具
你可以通过以下格式调用工具来读取项目文件:
\`\`\`tool_call
{"tool": "read_file", "path": "相对路径"}
\`\`\`
\`\`\`tool_call
{"tool": "list_directory", "path": "相对路径(可选)"}
\`\`\`
工具调用后会返回文件内容，然后你再继续回答。`

  return {
    role: 'system',
    content:
      '你是 KMatch IDE 的 AI 编程助手。你可以阅读项目文件、解释代码、提供改进建议、帮助调试。\n'
      + '回答用中文，代码块标注语言。保持回答简洁实用。\n'
      + '如果你需要查看某个文件来更好地回答问题，使用 tool_call 格式请求读取。'
      + ctxBlock
      + toolBlock,
  }
}

function parseToolCalls(text) {
  const re = /```tool_call\n([\s\S]*?)```/g
  const calls = []
  let m
  while ((m = re.exec(text)) !== null) {
    try {
      calls.push(JSON.parse(m[1].trim()))
    } catch { /* skip malformed */ }
  }
  return calls
}

function stripToolCalls(text) {
  if (!text) return ''
  return text.replace(/```tool_call\n[\s\S]*?```/g, '').trim()
}

/** 检测是否在 Electron 环境 */
function hasIpc() {
  return typeof window !== 'undefined' && !!window.api?.fs
}

export const useChatStore = defineStore('chat', () => {
  // ============================================================
  // 状态
  // ============================================================
  const messages = ref([])           // [{role, content, id, timestamp, toolCall?, toolResult?}]
  const streaming = ref(false)
  const currentStreamId = ref(null)
  const error = ref(null)
  const abortController = ref(null)

  const hasMessages = computed(() => messages.value.length > 0)

  // ============================================================
  // 内部方法
  // ============================================================
  let _idCounter = 0
  function _nextId() { return `msg_${Date.now()}_${++_idCounter}` }

  function _addMessage(role, content, extra = {}) {
    const msg = { id: _nextId(), role, content, timestamp: new Date().toISOString(), ...extra }
    messages.value.push(msg)
    return msg
  }

  async function _streamResponse(apiMessages, assistantMsg) {
    const resp = await fetch('/api/chat/completions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: apiMessages, stream: true, max_tokens: 4096 }),
      signal: abortController.value.signal,
    })

    if (!resp.ok) {
      const text = await resp.text().catch(() => '')
      throw new Error(text || `HTTP ${resp.status}`)
    }

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
        if (!dataStr || dataStr === '[DONE]') continue
        try {
          const data = JSON.parse(dataStr)
          if (data.error) { error.value = data.error; assistantMsg.content = `❌ ${data.error}`; return }
          if (data.delta) assistantMsg.content += data.delta
        } catch { /* skip */ }
      }
    }
  }

  /** 执行单个工具调用 */
  async function _executeTool(call) {
    try {
      if (call.tool === 'read_file') {
        const relPath = call.path
        if (!relPath) return { error: '缺少 path 参数' }
        if (!hasIpc()) return { error: '文件读取仅在 Electron 桌面应用中可用（请打开项目后使用）' }
        const content = await window.api.fs.readFile(relPath)
        return { path: relPath, content }
      }
      if (call.tool === 'list_directory') {
        const relPath = call.path || ''
        if (!hasIpc()) return { error: '目录列表仅在 Electron 桌面应用中可用（请打开项目后使用）' }
        const files = await window.api.fs.listDirectory(relPath, { deep: false })
        return { path: relPath || '(root)', files: (files || []).map((f) => f.path || f) }
      }
      return { error: `未知工具: ${call.tool}` }
    } catch (e) {
      return { error: e.message || '工具执行失败' }
    }
  }

  // ============================================================
  // Actions
  // ============================================================

  /** 收集工作区上下文 */
  async function _collectContext() {
    const ws = useWorkspaceStore()
    if (!ws.hasProject) return null

    const ctx = { projectRoot: ws.rootName || ws.root }
    if (ws.activeFile) {
      ctx.activeFile = ws.activeFile
      try {
        ctx.fileContent = await window.api.fs.readFile(ws.activeFile)
      } catch { /* file not readable */ }
    }
    // 文件树摘要 (前 30 个文件)
    const tree = ws.tree || []
    if (tree.length > 0) {
      ctx.fileTree = tree.slice(0, 30).map((f) => f.path).join('\n')
      if (tree.length > 30) ctx.fileTree += `\n... 共 ${tree.length} 个文件`
    }
    return ctx
  }

  /** 发送用户消息并获取 AI 回复 (SSE 流式 + 工具循环) */
  async function sendMessage(userContent) {
    if (streaming.value || !userContent.trim()) return

    error.value = null
    abortController.value = new AbortController()

    // 添加用户消息
    _addMessage('user', userContent.trim())

    // 收集工作区上下文
    const context = await _collectContext()

    // 工具循环 (最多 MAX_TOOL_ROUNDS 轮)
    let toolRound = 0

    while (toolRound < MAX_TOOL_ROUNDS) {
      toolRound++

      // 构建 API 消息列表 (strip tool_call blocks from assistant messages)
      const systemMsg = buildSystemPrompt(context)
      const historyMsgs = messages.value
        .filter((m) => m.role !== 'tool')
        .map((m) => ({
          role: m.role,
          content: m.role === 'assistant' ? stripToolCalls(m.content) : m.content,
        }))
      const apiMessages = [systemMsg, ...historyMsgs]

      // 添加助手占位消息
      const assistantMsg = _addMessage('assistant', '')
      currentStreamId.value = assistantMsg.id
      streaming.value = true

      try {
        await _streamResponse(apiMessages, assistantMsg)
      } catch (e) {
        if (e.name === 'AbortError') {
          if (assistantMsg.content === '') assistantMsg.content = '(已停止)'
          streaming.value = false; currentStreamId.value = null; return
        }
        error.value = e.message || '对话请求失败'
        if (assistantMsg.content === '') assistantMsg.content = `❌ ${error.value}`
        streaming.value = false; currentStreamId.value = null; return
      }

      streaming.value = false
      currentStreamId.value = null

      // 检查是否有 tool_call
      const toolCalls = parseToolCalls(assistantMsg.content)
      if (toolCalls.length === 0) {
        // 纯文本回复，完成
        break
      }

      // 执行工具调用
      const toolResults = []
      for (const call of toolCalls) {
        const result = await _executeTool(call)
        toolResults.push({ call, result })
      }

      if (toolResults.length === 0) break

      // 添加工具消息
      for (const tr of toolResults) {
        const toolContent = tr.result.error
          ? `❌ ${tr.call.tool}(${tr.call.path || ''}) 失败: ${tr.result.error}`
          : `📖 ${tr.call.tool}(${tr.result.path || ''})`
        _addMessage('tool', toolContent, {
          toolCall: tr.call,
          toolResult: tr.result,
        })
      }

      // 将工具结果注入到消息中，作为新的 user 消息
      const toolResultSummary = toolResults.map((tr) => {
        if (tr.result.error) return `工具 ${tr.call.tool} 失败: ${tr.result.error}`
        if (tr.result.content) return `文件 ${tr.result.path} 内容:\n\`\`\`\n${tr.result.content.slice(0, 6000)}\n\`\`\``
        if (tr.result.files) return `目录 ${tr.result.path} 内容:\n${tr.result.files.join('\n')}`
        return ''
      }).filter(Boolean).join('\n\n')

      if (toolResultSummary) {
        _addMessage('user', `[工具返回]\n${toolResultSummary}`)
      }

      // 继续循环，让 AI 基于工具结果回答
    }
  }

  function stopStreaming() {
    abortController.value?.abort()
  }

  function clearMessages() {
    abortController.value?.abort()
    messages.value = []
    streaming.value = false
    currentStreamId.value = null
    error.value = null
  }

  return {
    messages, streaming, currentStreamId, error,
    hasMessages,
    sendMessage, stopStreaming, clearMessages,
  }
})
