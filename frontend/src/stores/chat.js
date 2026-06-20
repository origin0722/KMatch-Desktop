/**
 * AI 助手对话 Store — 阶段3
 *
 * 阶段2: SSE 流式对话
 * 阶段3: 代码上下文注入 + 工具调用 (读文件/列目录)
 * 阶段3.1: write_file 工具 + 权限审批门 (复用后端 hard_check_code_safety)
 *
 * 工具调用流程:
 *   1. 发送消息 (含当前文件上下文 + 工具定义)
 *   2. AI 回复: 纯文本 → 直接展示; 含 tool_call → 执行工具 → 回传结果 → 继续
 *   3. 最多 3 轮工具循环，防止无限循环
 *
 * write_file 审批门: 命中 write_file 时先调后端 /api/chat/safety-check 做 AST 预检,
 *   再弹审批卡 (用户可编辑内容/批准/拒绝); 拒绝则把"用户拒绝写入"回传 AI。
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
  {
    name: 'write_file',
    description: '写入/创建项目文件 (需用户审批)。参数: path (相对路径), content (文件内容)。',
    parameters: {
      path: 'string (相对项目根目录的文件路径)',
      content: 'string (完整文件内容)',
    },
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
你可以通过以下格式调用工具来读写项目文件:
\`\`\`tool_call
{"tool": "read_file", "path": "相对路径"}
\`\`\`
\`\`\`tool_call
{"tool": "list_directory", "path": "相对路径(可选)"}
\`\`\`
\`\`\`tool_call
{"tool": "write_file", "path": "相对路径", "content": "完整文件内容"}
\`\`\`
- read_file/list_directory 调用后返回结果, 你再继续回答。
- write_file 会触发用户审批门 (Python 文件先经 AST 安全预检), 用户可能批准或拒绝;
  批准后返回写入成功, 拒绝则返回"用户拒绝写入", 你应据此调整后续回答。
- write_file 的 content 必须是完整可用的文件内容, 不要写占位符。`

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
  const messages = ref([])
  const streaming = ref(false)
  const currentStreamId = ref(null)
  const error = ref(null)
  const abortController = ref(null)

  // ---- write_file 权限审批门 (阶段3.1) ----
  // pendingApproval 非空时, UI 渲染审批卡; resolveApproval 由按钮触发。
  // { id, call, content, safetyIssues, safe, checked, resolve }
  const pendingApproval = ref(null)
  let _approvalId = 0

  // ---- 厂商 & API Key ----
  const PROVIDERS = [
    { id: 'deepseek', label: 'DeepSeek', baseUrl: 'https://api.deepseek.com/v1' },
    { id: 'openai', label: 'OpenAI', baseUrl: 'https://api.openai.com/v1' },
    { id: 'ollama', label: 'Ollama (本地)', baseUrl: 'http://localhost:11434/v1' },
    { id: 'custom', label: '自定义', baseUrl: '' },
  ]

  const STORAGE_KEY_PROVIDER = 'kmatch-chat-provider'
  const STORAGE_KEY_APIKEY = 'kmatch-chat-apikey'

  function _loadStr(key, fallback = '') {
    try { return localStorage.getItem(key) || fallback } catch { return fallback }
  }
  function _saveStr(key, val) {
    try { localStorage.setItem(key, val) } catch { /* noop */ }
  }

  const provider = ref(_loadStr(STORAGE_KEY_PROVIDER, 'deepseek'))
  const apiKey = ref(_loadStr(STORAGE_KEY_APIKEY, ''))
  const model = ref('deepseek-v4-pro')  // 自动从厂商拉取后设置
  const models = ref([])                // 厂商返回的模型列表

  const hasMessages = computed(() => messages.value.length > 0)

  function providerMeta() {
    return PROVIDERS.find((p) => p.id === provider.value) || PROVIDERS[0]
  }

  // ---- 自动拉取模型列表 ----
  async function fetchModels() {
    const meta = providerMeta()
    const key = apiKey.value.trim()
    if (!key) {
      // 无 key 时用默认模型列表
      models.value = _fallbackModels(provider.value)
      if (!model.value || !models.value.find((m) => m === model.value)) {
        model.value = models.value[0] || ''
      }
      return
    }
    const base = meta.baseUrl || promptBaseUrl()
    if (!base) {
      models.value = _fallbackModels(provider.value)
      return
    }
    try {
      // S1: 走 IPC 代理 (window.api.http), 桌面应用无需浏览器 fetch
      const res = await window.api.http.request('POST', '/api/chat/models', { base_url: base, api_key: key })
      const data = res.body
      if (!res.ok) throw new Error(typeof data === 'string' ? data : (data?.error || `HTTP ${res.status}`))
      if (data.models?.length) {
        models.value = data.models.sort()
        // 自动选第一个，或保留当前有效模型
        if (!model.value || !data.models.includes(model.value)) {
          model.value = data.models[0]
        }
      } else {
        models.value = _fallbackModels(provider.value)
      }
    } catch {
      models.value = _fallbackModels(provider.value)
    }
  }

  function promptBaseUrl() {
    if (typeof window !== 'undefined') {
      const url = window.prompt('请输入自定义 API Base URL (如 https://api.example.com/v1):')
      return url?.trim() || ''
    }
    return ''
  }

  function _fallbackModels(pid) {
    const map = {
      deepseek: ['deepseek-v4-pro', 'deepseek-v3', 'deepseek-reasoner'],
      openai: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo'],
      ollama: ['llama3', 'qwen2.5', 'codellama'],
      custom: [],
    }
    return map[pid] || []
  }

  function setProvider(pid) {
    provider.value = pid
    _saveStr(STORAGE_KEY_PROVIDER, pid)
    fetchModels()
  }

  function setApiKey(key) {
    apiKey.value = key
    _saveStr(STORAGE_KEY_APIKEY, key)
    fetchModels()
  }

  function getBaseUrl() {
    const meta = providerMeta()
    return meta.baseUrl || ''
  }

  // ============================================================
  // 内部方法
  // ============================================================
  let _idCounter = 0
  function _nextId() { return `msg_${Date.now()}_${++_idCounter}` }

  function _addMessage(role, content, extra = {}) {
    const msg = { id: _nextId(), role, content, timestamp: new Date().toISOString(), think: '', ...extra }
    messages.value.push(msg)
    return msg
  }

  /** 解析单个 SSE block, 更新 assistantMsg; 返回 'error' 表示遇到错误应中止 */
  function _applySseBlock(block, assistantMsg) {
    if (!block.trim()) return null
    const dataStr = block.match(/^data:\s*(.+)$/m)?.[1]
    if (!dataStr || dataStr === '[DONE]') return null
    try {
      const data = JSON.parse(dataStr)
      if (data.error) { error.value = data.error; assistantMsg.content = `❌ ${data.error}`; return 'error' }
      if (data.reasoning) assistantMsg.think = (assistantMsg.think || '') + data.reasoning
      if (data.delta) assistantMsg.content += data.delta
    } catch { /* skip */ }
    return null
  }

  // S1: 走 IPC SSE 代理 (window.api.http.stream), 桌面应用无需浏览器 fetch fallback。
  // preload 暴露 stream/onChunk/onDone/onError, http-proxy.js 转发后端 SSE。
  async function _streamResponse(apiMessages, assistantMsg) {
    const body = {
      messages: apiMessages,
      stream: true,
      max_tokens: 4096,
      model: model.value,
      api_key: apiKey.value || undefined,
      base_url: getBaseUrl() || undefined,
    }

    return new Promise((resolve, reject) => {
      let buffer = ''
      let settled = false
      const finish = () => {
        if (settled) return
        settled = true
        offChunk(); offDone(); offError()
        resolve()
      }
      const offChunk = window.api.http.onChunk((_reqId, block) => {
        if (settled) return
        buffer += block
        const parts = buffer.split('\n\n')
        buffer = parts.pop()
        for (const b of parts) {
          if (_applySseBlock(b, assistantMsg) === 'error') { finish(); return }
        }
      })
      const offDone = window.api.http.onDone(() => finish())
      const offError = window.api.http.onError((_reqId, err) => {
        if (settled) return
        settled = true
        offChunk(); offDone(); offError()
        reject(new Error(err || 'SSE 流失败'))
      })
      // 用户点停止: abort 时结束等待 (IPC 流无法真正中断, 后端流自然结束)
      abortController.value.signal.addEventListener('abort', () => finish())

      window.api.http.stream('/api/chat/completions', body).catch((e) => {
        if (settled) return
        settled = true
        offChunk(); offDone(); offError()
        reject(e)
      })
    })
  }

  /** 调后端 /api/chat/safety-check 做 AST 安全预检 (仅 .py 真正检查) */
  async function _safetyCheck(code, filename) {
    try {
      const res = await window.api.http.request('POST', '/api/chat/safety-check', {
        code, filename: filename || null,
      })
      const data = res.body
      if (!res.ok) return { checked: false, safe: true, issues: [], error: data?.error || `HTTP ${res.status}` }
      return {
        checked: !!data.checked,
        safe: data.safe !== false,
        issues: data.issues || [],
      }
    } catch (e) {
      // 预检失败不阻断审批 (降级: 让用户自行判断), 仅提示
      return { checked: false, safe: true, issues: [], error: e.message || '安全预检请求失败' }
    }
  }

  /** 弹审批卡, 等待用户决定; 返回 { approved, content } */
  function _requestApproval(call, safety) {
    return new Promise((resolve) => {
      pendingApproval.value = {
        id: `appr_${++_approvalId}`,
        call,
        content: call.content ?? '',
        safetyIssues: safety.issues || [],
        safe: safety.safe,
        checked: safety.checked,
        safetyError: safety.error || null,
        resolve,
      }
    })
  }

  /** UI 触发: 批准/拒绝 write_file. decision = { approved, content? } */
  function resolveApproval(decision) {
    const p = pendingApproval.value
    if (!p) return
    pendingApproval.value = null
    p.resolve(decision || { approved: false })
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
      if (call.tool === 'write_file') {
        const relPath = call.path
        if (!relPath) return { error: '缺少 path 参数' }
        if (call.content === undefined || call.content === null) return { error: '缺少 content 参数' }
        if (!hasIpc()) return { error: '文件写入仅在 Electron 桌面应用中可用（请打开项目后使用）' }

        // 1) 后端 AST 安全预检 (Python 文件; 复用 hard_check_code_safety)
        const safety = await _safetyCheck(call.content, relPath)

        // 2) 审批门: 等待用户决定 (用户可编辑内容)
        const decision = await _requestApproval(call, safety)
        if (!decision.approved) {
          return { path: relPath, rejected: true, error: '用户拒绝写入' }
        }

        // 3) 执行写入 (用可能被用户编辑后的 content)
        const finalContent = decision.content ?? call.content
        await window.api.fs.writeFile(relPath, finalContent)

        // 4) 刷新文件树 + 在编辑器打开该文件
        try {
          const ws = useWorkspaceStore()
          await ws.refreshTree?.()
          await ws.openFile?.(relPath)
        } catch { /* 刷新/打开失败不影响写入结果上报 */ }

        return { path: relPath, written: true, bytes: finalContent.length }
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
        let toolContent
        if (tr.result.error) {
          toolContent = `❌ ${tr.call.tool}(${tr.call.path || ''}) 失败: ${tr.result.error}`
        } else if (tr.call.tool === 'write_file') {
          toolContent = `📝 write_file(${tr.result.path}) 已写入 ${tr.result.bytes ?? 0} 字节`
        } else {
          toolContent = `📖 ${tr.call.tool}(${tr.result.path || ''})`
        }
        _addMessage('tool', toolContent, {
          toolCall: tr.call,
          toolResult: tr.result,
        })
      }

      // 将工具结果注入到消息中，作为新的 user 消息
      const toolResultSummary = toolResults.map((tr) => {
        if (tr.result.error) return `工具 ${tr.call.tool} 失败: ${tr.result.error}`
        if (tr.result.written) return `文件 ${tr.result.path} 已成功写入 (${tr.result.bytes} 字节)。`
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
    // 取消未决的 write_file 审批 (按拒绝处理, 解开 await)
    if (pendingApproval.value) {
      const p = pendingApproval.value
      pendingApproval.value = null
      p.resolve({ approved: false })
    }
    messages.value = []
    streaming.value = false
    currentStreamId.value = null
    error.value = null
  }

  // 初始化
  fetchModels()

  return {
    messages, streaming, currentStreamId, error,
    hasMessages,
    // write_file 审批门 (阶段3.1)
    pendingApproval, resolveApproval,
    // 厂商 & 模型
    provider, apiKey, model, models, PROVIDERS,
    setProvider, setApiKey, fetchModels,
    // 对话
    sendMessage, stopStreaming, clearMessages,
  }
})
