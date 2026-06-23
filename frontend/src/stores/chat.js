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
import { useProjectGraphStore } from '@/stores/projectGraph'
import { streamChat } from '@/ide/chat/useChatStream'
import { useAiSettingsStore } from '@/stores/aiSettings'
import {
  buildToolBlock,
  buildAdvertisedToolNames,
  toolPermissionError,
} from '@/ide/tools/registry'
import {
  hasProfile,
  profileTheoryLevel,
  profilePracticeLevel,
  profileWeakTopicNames,
  learningPathLength,
  learningEstimatedHours,
} from '@/ide/chat/types'

const MAX_TOOL_ROUNDS = 3

/**
 * 构建学情画像提示块 (C3: 经 chat/types.js 类型化 helper 读取, 不再硬编码 profile/knowledgeGraph 字段名)。
 * @param {Object} ctx  context (含 profile, knowledgeGraph)
 * @param {string} title  画像块标题
 * @returns {string}  画像块 (含前置换行), 无内容返回 ''
 */
function buildProfileBlock(ctx, title) {
  const p = ctx?.profile
  if (!hasProfile(p)) return ''
  const lines = []
  const theory = profileTheoryLevel(p)
  const practice = profilePracticeLevel(p)
  if (theory != null) lines.push(`- 理论水平: ${theory}/5`)
  if (practice != null) lines.push(`- 实操水平: ${practice}/5`)
  const weak = profileWeakTopicNames(p, 5)
  if (weak.length) lines.push('- 薄弱知识点: ' + weak.join('、'))
  // 学习路径信息仅非导学模式注入 (导学模式聚焦薄弱点); 由调用方决定是否传 kg
  if (ctx?.knowledgeGraph) {
    const pathLen = learningPathLength(ctx.knowledgeGraph)
    if (pathLen) {
      const hours = learningEstimatedHours(ctx.knowledgeGraph)
      lines.push(`- 学习路径: ${pathLen} 个节点, 预计 ${hours ?? '?'}h`)
    }
  }
  if (!lines.length) return ''
  return `\n\n## ${title}\n` + lines.join('\n')
}

export function buildSystemPrompt(context) {
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

  const toolBlock = buildToolBlock(context?.allowedTools)
  const memoriesBlock = context?.memoriesBlock || ''
  const reasoningBlock = context?.reasoningInstruction
    ? `\n\n## 思考模式\n${context.reasoningInstruction}`
    : ''

  // ---- 阶段4③ 启发式交互导学模式 (赛题(4)②) ----
  if (context && context.tutorMode) {
    // 注入学情画像 (经 types.js helper 读取, 导学模式聚焦薄弱点, 不含学习路径)
    const profileBlock = buildProfileBlock({ profile: context.profile }, '学习者学情画像 (个性化引导依据)')

    return {
      role: 'system',
      content:
        '你是 KMatch IDE 的启发式导学助手。核心原则: 【以引导式回答替代直接给出答案】, 像苏格拉底式导师那样通过提问和提示让学习者自己得出结论, 而非直接抛出代码或答案。\n'
        + '\n## 启发式导学规则 (赛题(4)② 动态追问与启发式交互导学)'
        + '\n1. 不直接给完整答案/完整代码。先给思路、提示、方向, 让学习者尝试; 仅当其反复卡住(≥2轮)或明确要求时才逐步揭示, 且优先给带空白的框架而非完整解。'
        + '\n2. 动态追问: 每次回复末尾提一个针对当前问题的追问, 探测学习者理解深度、引导下一步思考 (如"你觉得这里为什么会报错?"/"如果输入是空列表会怎样?"), 推动多轮交互。'
        + '\n3. 因材施教: 依据下方学情画像调整引导粒度——薄弱者多铺垫类比, 进阶者直指原理与权衡。'
        + '\n4. 事实底座抗幻觉: 涉及项目代码时先用 read_file/generate_project_graph 等工具查证真实代码与结构, 严禁凭记忆臆造项目细节; 解释通用概念时也只讲你确信的内容。'
        + '\n5. 简洁: 每轮回复聚焦一个引导点 + 一个追问, 不要长篇大论。'
        + profileBlock
        + memoriesBlock
        + reasoningBlock
        + ctxBlock
        + toolBlock,
    }
  }

  // 阶段9: 双向联动 — 非导学模式也注入学情画像 (含学习路径), 助手可回答"为什么这样规划"
  const profileBlock = buildProfileBlock(context, '学习者学情画像 (可据此回答"为什么这样规划")')

  return {
    role: 'system',
    content:
      '你是 KMatch IDE 的 AI 编程助手。你可以阅读项目文件、解释代码、提供改进建议、帮助调试。\n'
      + '回答用中文，代码块标注语言。保持回答简洁实用。\n'
      + '如果你需要查看某个文件来更好地回答问题，使用 tool_call 格式请求读取。'
      + profileBlock
      + memoriesBlock
      + reasoningBlock
      + ctxBlock
      + toolBlock,
  }
}

// ============================================================
// Chunk 模型纯函数 (C1.5 抽至 ide/chat/model.js; 此处 re-export 保持 @/stores/chat 既有契约)
//   { type: 'think',    content: string }
//   { type: 'content',  content: string }
//   { type: 'tool_call', id, tool, args, status: 'pending'|'in_progress'|'completed'|'error', result? }
// 相邻同类型 think/content 合并; tool_call 带状态机。
// ============================================================
export {
  parseToolCalls,
  stripToolCalls,
  appendTextChunk,
  activeChunksOf,
  contentTextOf,
  thinkTextOf,
  splitToolCallChunks,
} from '@/ide/chat/model'
import {
  appendTextChunk,
  activeChunksOf,
  contentTextOf,
  splitToolCallChunks,
  stripToolCalls,
} from '@/ide/chat/model'

/** 检测是否在 Electron 环境 */
function hasIpc() {
  return typeof window !== 'undefined' && !!window.api?.fs
}

/**
 * 把一轮工具执行结果汇总成回喂 AI 的 user 消息文本 (C1.4 单一源)。
 * sendMessage 与 regenMessage 共用, 消除原先 regen 的精简重复副本。
 */
export function summarizeToolResults(toolResults) {
  return toolResults.map((tr) => {
    if (tr.result.error) return `工具 ${tr.call.tool} 失败: ${tr.result.error}`
    // write_file 才有 written=true; generate_project_graph 的 written 是"是否落 Neo4j"语义不同,
    // 故 written 分支限定 write_file, 避免吞掉 graph 摘要 (review 发现)
    if (tr.result.written && tr.call.tool === 'write_file') return `文件 ${tr.result.path} 已成功写入 (${tr.result.bytes} 字节)。`
    if (tr.result.content) {
      // F7: 截断 6000 字符时明示, 让 AI 知道被截断 (大文件推理不再静默降级)
      const max = 6000
      const full = tr.result.content
      const truncated = full.length > max ? full.slice(0, max) + `\n... (内容已截断, 共 ${full.length} 字符, 仅显示前 ${max}; 如需后续内容请指明行号范围)` : full
      return `文件 ${tr.result.path} 内容:\n\`\`\`\n${truncated}\n\`\`\``
    }
    if (tr.result.files) return `目录 ${tr.result.path} 内容:\n${tr.result.files.join('\n')}`
    if (tr.result.tool === 'generate_project_graph') {
      const s = tr.result.stats || {}
      const ents = (tr.result.entities || []).slice(0, 20)
        .map((e) => `- ${e.kind} ${e.qualified_name} (行${e.line_start || '?'}-${e.line_end || '?'})`)
        .join('\n')
      return `项目图谱已生成 (${tr.result.sourcePath}, written=${tr.result.written}). 统计: 模块${s.module || 0}/类${s.class || 0}/函数${s.function || 0}/方法${s.method || 0}.\n实体清单:\n${ents || '(无)'}`
    }
    if (tr.result.tool === 'code_review') {
      const rv = tr.result.review || {}
      const dims = rv.dimensions || {}
      const dimLines = Object.entries(dims).map(([k, v]) => `${k}: ${((v.score ?? 0) * 100).toFixed(0)}%`).join(', ')
      const highIssues = (Object.values(dims).flatMap((d) => d.issues || []).filter((i) => i.severity === 'high')).slice(0, 5)
        .map((i) => `- [high] ${i.problem}`).join('\n')
      return `代码审查结果 (${tr.result.sourcePath}): verdict=${rv.verdict}, overall=${rv.overall_score != null ? (rv.overall_score * 100).toFixed(0) + '%' : '?'}, 通过阈值0.85. 维度: ${dimLines}.${rv.retry_hint ? ' 提示: ' + rv.retry_hint : ''}${highIssues ? '\n高危问题:\n' + highIssues : ''}`
    }
    if (tr.result.tool === 'code_test') {
      const rp = tr.result.report || {}
      const sm = rp.summary || {}
      const cov = rp.coverage || {}
      const fails = (rp.failed_tests || []).slice(0, 5)
        .map((f) => `- ${f.test_name}: ${f.suggestion || f.error_type || '失败'}`).join('\n')
      return `代码测试结果 (${tr.result.sourcePath}): ${sm.passed || 0}/${sm.total || 0} 通过, 行覆盖${((cov.line_coverage || 0) * 100).toFixed(0)}%, 分支覆盖${((cov.branch_coverage || 0) * 100).toFixed(0)}%, 函数覆盖${((cov.function_coverage || 0) * 100).toFixed(0)}%.${rp.note ? ' 备注: ' + rp.note : ''}${fails ? '\n失败用例:\n' + fails : ''}${rp.rejected ? ' (已拒绝: ' + (rp.reject_reason || '') + ')' : ''}`
    }
    return ''
  }).filter(Boolean).join('\n\n')
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

  // ---- 工具执行窗口锁 (审查 #2: streaming 只覆盖 SSE 相位, 工具循环在 streaming=false
  // 后跑; code_review/code_test 可能 ~10s。toolLoopRunning 覆盖此窗口, isBusy 统一禁用源) ----
  const toolLoopRunning = ref(false)
  const isBusy = computed(() => streaming.value || !!pendingApproval.value || toolLoopRunning.value)

  // 厂商 & 模型配置已迁至 aiSettings store (C1.1, 统一 AI 配置单一源);
  // chat 经 useAiSettingsStore() 读取 provider/model/apiKey/getBaseUrl。

  const STORAGE_KEY_TUTOR = 'kmatch-chat-tutor'

  function _loadStr(key, fallback = '') {
    try { return localStorage.getItem(key) || fallback } catch { return fallback }
  }
  function _saveStr(key, val) {
    try { localStorage.setItem(key, val) } catch { /* noop */ }
  }

  // ---- 阶段4③ 启发式导学模式 (赛题(4)②, 持久化) ----
  const tutorMode = ref(_loadStr(STORAGE_KEY_TUTOR, 'false') === 'true')

  const hasMessages = computed(() => messages.value.length > 0)

  /**
   * 当前可见消息: 每个助手消息"管辖"它之后的消息——由其 activeVersion.trailingAfter
   * (一组消息 ID) 决定哪些后续消息可见。切 version 换 trailingAfter → 后续显隐。
   *
   * trailingAfter 模型 (替代 spanEnd): 单一下标断点无法区分"旧 version 的尾随 (重生成
   * 时应隐藏)"与"重生成后新追加的消息 (应可见)", 会导致 regen 后追问静默丢消息。
   * trailingAfter 显式记录每个 version 自己的尾随 ID; 新版本从 [] 起, 新消息经
   * _addMessage 钩子归入当前活跃版本的 trailingAfter。
   *
   * 走法: 维护 visibleTrailing (null=尚未遇到助手, 对话顶部全可见; 否则为最近一个
   * 【可见】助手 active 版本 trailingAfter 的 Set)。每条消息 (含助手) 必须在
   * visibleTrailing 内才可见; 可见的助手消息会把 visibleTrailing 换成自己的。
   */
  const visibleMessages = computed(() => {
    const all = messages.value
    const out = []
    let visibleTrailing = null // null = 还没遇到助手 (对话顶部, 全可见)
    for (const m of all) {
      if (visibleTrailing !== null && !visibleTrailing.has(m.id)) continue // 属于非活跃分支, 隐藏
      out.push(m)
      if (m.role === 'assistant' && Array.isArray(m.versions)) {
        const v = m.versions[m.activeVersion ?? 0]
        visibleTrailing = new Set(Array.isArray(v?.trailingAfter) ? v.trailingAfter : [])
      }
    }
    return out
  })

  /** 由 aiSettings.reasoningMode 推导后端 reasoning 字段 (借鉴 Apix llm_adapter):
   *  AUTO → 不传 (模型默认; DeepSeek-V4 默认 thinking enabled)
   *  FAST → false (关闭思考, 秒回)
   *  DEEP → true  (开启思考) */
  function _reasoningForRequest() {
    try {
      const mode = useAiSettingsStore().reasoningMode
      if (mode === 'fast') return false
      if (mode === 'deep') return true
    } catch { /* aiSettings 未就绪, 走默认 */ }
    return undefined
  }

  function setTutorMode(on) {
    tutorMode.value = !!on
    _saveStr(STORAGE_KEY_TUTOR, tutorMode.value ? 'true' : 'false')
  }

  // ============================================================
  // 内部方法
  // ============================================================
  let _idCounter = 0
  function _nextId() { return `msg_${Date.now()}_${++_idCounter}` }

  function _addMessage(role, payload, extra = {}) {
    const chunks = typeof payload === 'string'
      ? [{ type: 'content', content: payload }]
      : Array.isArray(payload) ? payload : []
    const ts = new Date().toISOString()
    let msg
    if (role === 'assistant') {
      // 助手消息: versions 结构 (支持重生成分支)
      // trailingAfter = [] (开放): 线性追加的后续消息经下方钩子归入当前活跃版本,
      // 直到重生成追加新 version (新版本 trailingAfter=[], 旧版本冻结)。
      const versionId = _nextId().replace('msg_', 'ver_')
      msg = {
        id: _nextId(), role,
        versions: [{ id: versionId, chunks, timestamp: ts, trailingAfter: [] }],
        activeVersion: 0,
        timestamp: ts,
        ...extra,
      }
    } else {
      msg = { id: _nextId(), role, chunks, timestamp: ts, ...extra }
    }
    // trailingAfter 维护: 新消息归入"此前最后一个助手消息"的当前活跃版本分支。
    // 线性对话 → 每条新消息追加到上一助手的 trailingAfter → 可见;
    // regen 后新版本活跃 → 新消息归新版本 (旧版本冻结不收) → 新消息在新分支可见 (Critical: 不再静默丢)。
    let prevAssistant = null
    for (let i = messages.value.length - 1; i >= 0; i--) {
      const m = messages.value[i]
      if (m.role === 'assistant' && Array.isArray(m.versions)) { prevAssistant = m; break }
    }
    messages.value.push(msg)
    if (prevAssistant && prevAssistant.id !== msg.id) {
      const v = prevAssistant.versions[prevAssistant.activeVersion ?? 0]
      if (v && Array.isArray(v.trailingAfter)) v.trailingAfter.push(msg.id)
    }
    return msg
  }

  /**
   * 解析单个 SSE block, 累积进 assistantMsg 当前 version 的 chunks。
   * 返回 null=继续; 返回 Error=流内错误 (F2: 已渲染 ❌ chunk, streamChat 据 reject,
   *   _runToolRound catch 见 streamError 标记勿重复渲染)。
   */
  function _applySseBlock(block, assistantMsg) {
    if (!block.trim()) return null
    const dataStr = block.match(/^data:\s*(.+)$/m)?.[1]
    if (!dataStr || dataStr === '[DONE]') return null
    try {
      const data = JSON.parse(dataStr)
      if (data.error) {
        error.value = data.error
        appendTextChunk(activeChunksOf(assistantMsg), 'content', `❌ ${data.error}`)
        const e = new Error(data.error)
        e.streamError = true // 已渲染 chunk, 调用方勿重复
        return e
      }
      if (data.reasoning) appendTextChunk(activeChunksOf(assistantMsg), 'think', data.reasoning)
      if (data.delta) appendTextChunk(activeChunksOf(assistantMsg), 'content', data.delta)
    } catch { /* skip malformed block */ }
    return null
  }

  // SSE 流式: 传输层抽至 useChatStream (C1.3); 这里只构建 body + 解析 block。
  async function _streamResponse(apiMessages, assistantMsg) {
    const ai = useAiSettingsStore()
    const body = {
      messages: apiMessages,
      stream: true,
      max_tokens: 8192,
      model: ai.model,
      api_key: ai.apiKey || undefined,
      base_url: ai.getBaseUrl() || undefined,
    }
    // DeepSeek-V4 等思考模型经 extra_body.thinking 控制 (后端 _build_extra_body)
    const reasoning = _reasoningForRequest()
    if (reasoning !== undefined) body.reasoning = reasoning

    await streamChat({
      body,
      signal: abortController.value.signal,
      onBlock: (block) => _applySseBlock(block, assistantMsg),
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
    _cancelPendingApproval(decision)
  }

  /** F8 集中处理: 取消未决审批 (按 decision 解决 await, 默认拒绝), 防新退出路径忘 reject 导致 hung promise。 */
  function _cancelPendingApproval(decision = { approved: false }) {
    const p = pendingApproval.value
    if (!p) return
    pendingApproval.value = null
    p.resolve(decision)
  }

  /**
   * 解析委派工具的代码来源 (阶段4)
   * 优先 call.path (工作区文件, 便于符号联动), 否则用 call.code + call.filename。
   * 返回 { code, sourcePath } 或 { error }。sourcePath 用于 4b Monaco 跳转。
   */
  async function _resolveCode(call) {
    if (!hasIpc()) return { error: '该工具仅在 Electron 桌面应用中可用（请打开项目后使用）' }
    if (call.path) {
      try {
        const content = await window.api.fs.readFile(call.path)
        return { code: content, sourcePath: call.path }
      } catch (e) {
        return { error: `读取文件失败: ${e.message || e}` }
      }
    }
    if (call.code === undefined || call.code === null) return { error: '缺少 path 或 code 参数' }
    return { code: call.code, sourcePath: call.filename || 'main.py' }
  }

  /** 委派后端 /api/project/* 路由; 返回 { ok, status, data } */
  async function _delegate(urlPath, body, timeoutMs) {
    try {
      const res = await window.api.http.request('POST', urlPath, body, null, timeoutMs ? { timeoutMs } : undefined)
      const data = res.body
      if (!res.ok) {
        const detail = (data && typeof data === 'object' && (data.detail || data.error)) || `HTTP ${res.status}`
        // 503 = Neo4j 未就绪, 给 AI 可读提示
        if (res.status === 503) return { ok: false, error: '图谱引擎未就绪（Neo4j 未连接），请先启动 Neo4j' }
        return { ok: false, error: typeof detail === 'string' ? detail : JSON.stringify(detail) }
      }
      return { ok: true, data }
    } catch (e) {
      return { ok: false, error: e.message || '委派请求失败' }
    }
  }

  /** 执行单个工具调用 */
  async function _executeTool(call) {
    try {
      // F6: 坏 JSON 的 tool_call (splitToolCallChunks 标 _malformed) → 明确报错, 不静默丢
      if (call.tool === '_malformed') {
        return { error: `工具调用格式错误 (JSON 解析失败): ${call._raw?.slice(0, 120) || ''}` }
      }
      const aiSettings = useAiSettingsStore()
      const permissionError = toolPermissionError(call.tool, aiSettings.permissionFor(call.tool))
      if (permissionError) return { error: permissionError }

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

      // ---- 阶段4: 图谱委派工具 (复用 /api/project/* 路由) ----
      if (call.tool === 'generate_project_graph') {
        const src = await _resolveCode(call)
        if (src.error) return { error: src.error }
        const body = {
          source_type: 'text',
          code: src.code,
          filename: call.filename || 'main.py',
          write_to_neo4j: call.write_to_neo4j === true,
        }
        const r = await _delegate('/api/project/parse', body)
        if (!r.ok) return { error: r.error }
        const d = r.data || {}
        // 提取实体 (G6 nodes.properties 含 line_start/line_end/qualified_name/kind)
        const entities = (d.nodes || []).map((n) => ({
          id: n.id,
          name: n.label,
          kind: n.group,
          qualified_name: n.properties?.qualified_name || n.label,
          line_start: n.properties?.line_start,
          line_end: n.properties?.line_end,
        }))
        const result = {
          tool: 'generate_project_graph',
          projectId: d.project_id,
          stats: d.stats || {},
          entities,
          relations: d.edges || [],
          sourcePath: src.sourcePath,
          written: !!d.written_to_neo4j,
        }
        // 供 4b Monaco 符号联动
        try { useProjectGraphStore().setGraph(result, src.sourcePath) } catch { /* store 未就绪不影响 */ }
        return result
      }
      if (call.tool === 'code_review') {
        if (!call.target_direction) return { error: '缺少 target_direction 参数（开发目标方向）' }
        const src = await _resolveCode(call)
        if (src.error) return { error: src.error }
        const body = {
          code: src.code,
          target_direction: call.target_direction,
          knowledge_node_ids: call.knowledge_node_ids || null,
        }
        const r = await _delegate('/api/project/review', body)
        if (!r.ok) return { error: r.error }
        return { tool: 'code_review', review: r.data, sourcePath: src.sourcePath }
      }
      if (call.tool === 'code_test') {
        if (!call.target_direction) return { error: '缺少 target_direction 参数（开发目标方向）' }
        const src = await _resolveCode(call)
        if (src.error) return { error: src.error }
        const body = {
          source_type: 'text',
          code: src.code,
          filename: call.filename || 'main.py',
          target_direction: call.target_direction,
          knowledge_node_ids: call.knowledge_node_ids || null,
          mode: call.mode || 'generate',
        }
        // code_test (LLM 生成 + pytest 执行) 可达 60s+, 放宽超时
        const r = await _delegate('/api/project/test', body, 180000)
        if (!r.ok) return { error: r.error }
        return { tool: 'code_test', report: r.data, sourcePath: src.sourcePath }
      }

      return { error: `未知工具: ${call.tool}` }
    } catch (e) {
      return { error: e.message || '工具执行失败' }
    }
  }

  // ============================================================
  // Actions
  // ============================================================

  /** 收集工作区上下文 (含导学模式 + 学情画像, 供 buildSystemPrompt 分支) */
  async function _collectContext() {
    const ws = useWorkspaceStore()

    // 导学模式 + 学情画像即使无项目也要带上 (支持纯概念问答式导学)
    const ctx = { tutorMode: tutorMode.value }
    try {
      const { useAssessmentStore } = await import('@/stores/assessment')
      const a = useAssessmentStore()
      ctx.profile = a.profile
      if (a.hasResults) ctx.knowledgeGraph = a.knowledgeGraph
    } catch { /* assessment store 未就绪, 忽略 */ }

    try {
      const aiSettings = useAiSettingsStore()
      ctx.allowedTools = buildAdvertisedToolNames(aiSettings.permissionFor)
      ctx.memoriesBlock = aiSettings.formatEnabledMemories()
      ctx.reasoningInstruction = aiSettings.reasoningInstruction(aiSettings.provider, aiSettings.model)
    } catch { /* aiSettings store 未就绪, 忽略 */ }

    if (!ws.hasProject) return ctx

    ctx.projectRoot = ws.rootName || ws.root
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

  /**
   * 单轮工具循环体 (C1.4 抽出, sendMessage 与 regenMessage 共用):
   * 流式 → 切 tool_call chunks → 执行工具 → 摘要回喂。
   * @returns {'done'|'continue'|'abort'} done=无工具调用或无结果(循环结束); continue=有工具结果继续下轮; abort=流式被中止/出错
   */
  async function _runToolRound({ apiMessages, assistantMsg, errorLabel }) {
    streaming.value = true
    currentStreamId.value = assistantMsg.id
    try {
      await _streamResponse(apiMessages, assistantMsg)
    } catch (e) {
      if (e.name === 'AbortError') {
        if (contentTextOf(assistantMsg) === '') appendTextChunk(activeChunksOf(assistantMsg), 'content', '(已停止)')
        streaming.value = false; currentStreamId.value = null; return 'abort'
      }
      // F2: 流内错误 (e.streamError) 已由 _applySseBlock 渲染 ❌ chunk + 设 error.value, 勿重复
      if (!e.streamError) {
        error.value = e.message || errorLabel
        if (contentTextOf(assistantMsg) === '') appendTextChunk(activeChunksOf(assistantMsg), 'content', `❌ ${error.value}`)
      }
      streaming.value = false; currentStreamId.value = null; return 'abort'
    }
    streaming.value = false
    currentStreamId.value = null

    // 流式累积后, 把 content 文本切成 [content?, tool_call, ...] 段, 重建非 think chunks
    const segs = splitToolCallChunks(contentTextOf(assistantMsg))
    const hasToolCall = segs.some((c) => c.type === 'tool_call')
    if (!hasToolCall) return 'done' // 纯文本回复, 完成

    const thinkChunks = activeChunksOf(assistantMsg).filter((c) => c.type === 'think')
    assistantMsg.versions[assistantMsg.activeVersion].chunks = [...thinkChunks, ...segs]

    // 逐个执行 tool_call chunk: 状态机 pending → in_progress → completed/error
    const toolResults = []
    toolLoopRunning.value = true
    try {
      for (const chunk of activeChunksOf(assistantMsg)) {
        if (chunk.type !== 'tool_call') continue
        chunk.status = 'in_progress'
        const result = await _executeTool(chunk.args)
        chunk.status = result.error ? 'error' : 'completed'
        chunk.result = result
        toolResults.push({ call: chunk.args, result })
      }
    } finally {
      toolLoopRunning.value = false
    }

    if (toolResults.length === 0) return 'done'

    // 工具结果摘要作为新 user 消息塞回历史 (trailingAfter 由 _addMessage 钩子维护)
    const toolResultSummary = summarizeToolResults(toolResults)
    if (toolResultSummary) {
      _addMessage('user', `[工具返回]\n${toolResultSummary}`)
    }
    return 'continue'
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

      // 构建 API 消息列表 (assistant content 去掉 tool_call 块; chunks 模型无 tool 角色)
      // 用 visibleMessages: regen 隐藏的尾随消息不应进 API 历史 (见 regenMessage)
      const systemMsg = buildSystemPrompt(context)
      const historyMsgs = visibleMessages.value.map((m) => ({
        role: m.role,
        content: m.role === 'assistant' ? stripToolCalls(contentTextOf(m)) : contentTextOf(m),
      }))
      const apiMessages = [systemMsg, ...historyMsgs]

      // 每轮添加新的助手占位消息 (空 chunks)
      const assistantMsg = _addMessage('assistant', [])

      const outcome = await _runToolRound({ apiMessages, assistantMsg, errorLabel: '对话请求失败' })
      if (outcome !== 'continue') break // done (纯文本) 或 abort (中止/出错)
    }
  }

  /** 重生成指定助手消息 (追加新 version, 不覆盖原) */
  async function regenMessage(msgId) {
    // 流中 / 审批门 / 工具执行窗口 禁止重生成 (统一 isBusy, 审查 #2 修 F10 工具循环窗口)
    if (isBusy.value) return
    const target = messages.value.find((m) => m.id === msgId)
    if (!target || target.role !== 'assistant' || !Array.isArray(target.versions)) return
    const targetIdx = messages.value.indexOf(target)

    error.value = null
    abortController.value = new AbortController()

    // 1. 旧版 trailingAfter 冻结 (保留其旧 trailing IDs, 无需改动)
    // 2. 追加新 version (trailingAfter=[], 无 trailing), activeVersion 指向它
    const newVerId = _nextId().replace('msg_', 'ver_')
    target.versions.push({ id: newVerId, chunks: [], timestamp: new Date().toISOString(), trailingAfter: [] })
    target.activeVersion = target.versions.length - 1

    // 3. 收集上下文
    const context = await _collectContext()

    // 4. 工具循环 (复用 _runToolRound, 历史只取 target 之前的 visible 消息; 流进 target 新版本)
    let toolRound = 0
    while (toolRound < MAX_TOOL_ROUNDS) {
      toolRound++
      const systemMsg = buildSystemPrompt(context)
      const visibleSoFar = visibleMessages.value.filter((m) => messages.value.indexOf(m) < targetIdx)
      const historyMsgs = visibleSoFar.map((m) => ({
        role: m.role,
        content: m.role === 'assistant' ? stripToolCalls(contentTextOf(m)) : contentTextOf(m),
      }))
      const apiMessages = [systemMsg, ...historyMsgs]

      // trailingAfter 由 _addMessage 钩子自动维护 (target 为最后一个助手时, 工具结果归入新版本)
      const outcome = await _runToolRound({ apiMessages, assistantMsg: target, errorLabel: '重生成失败' })
      if (outcome !== 'continue') break
    }
  }

  function stopStreaming() {
    abortController.value?.abort()
    // F8: 停止时若有未决审批, 按拒绝解开 await (防 hung promise)
    _cancelPendingApproval()
  }

  /** 切助手消息的版本 (prev/next 导航) */
  function setVersion(msgId, idx) {
    const m = messages.value.find((x) => x.id === msgId)
    if (!m || !Array.isArray(m.versions)) return
    if (idx < 0 || idx >= m.versions.length) return
    m.activeVersion = idx
  }

  function clearMessages() {
    abortController.value?.abort()
    // F8: 集中取消未决审批 (按拒绝), 解开 await
    _cancelPendingApproval()
    messages.value = []
    streaming.value = false
    currentStreamId.value = null
    toolLoopRunning.value = false
    error.value = null
  }

  return {
    messages, visibleMessages, streaming, currentStreamId, error,
    hasMessages,
    isBusy,
    // write_file 审批门 (阶段3.1)
    pendingApproval, resolveApproval,
    // 启发式导学模式 (阶段4③)
    tutorMode, setTutorMode,
    // 对话
    sendMessage, stopStreaming, clearMessages,
    setVersion, regenMessage,
  }
})
