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
import { ref, computed, watch } from 'vue'
import { defineStore } from 'pinia'
import { useWorkspaceStore } from '@/stores/workspace'
import { useProjectGraphStore } from '@/stores/projectGraph'
import { useLearningResourcesStore } from '@/stores/learningResources'
import { getNode, semanticSearch, assemblePath, getPrerequisites } from '@/api/graph'
import { graphToExcalidraw, downloadExcalidraw } from '@/utils/excalidrawExport'
import { readProjectPyFiles, normalizeGraphResponse, getProjectGraph } from '@/api/project'
import { streamChat } from '@/ide/chat/useChatStream'
import { useAiSettingsStore } from '@/stores/aiSettings'
import { withOverrides } from '@/stores/agentLlm'
import {
  buildToolBlock,
  buildAdvertisedToolNames,
  toolPermissionError,
} from '@/ide/tools/registry'
import { detectTechStack } from '@/utils/techStack'
import {
  hasProfile,
  profileTheoryLevel,
  profilePracticeLevel,
  profileWeakTopicNames,
  learningPathLength,
  learningEstimatedHours,
} from '@/ide/chat/types'

const MAX_TOOL_ROUNDS = 6

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

  // 学情讲义: 用户答题后生成的针对性内容 (feedbackContent.resources), 注入后助手可基于讲义解答疑问
  let lectureBlock = ''
  const fc = context?.feedbackContent
  if (fc && Array.isArray(fc.resources) && fc.resources.length) {
    const parts = fc.resources.map((r, i) => {
      const title = r.title || r.target_node_id || `资源${i + 1}`
      const content = r.content || ''
      const max = 4000
      const truncated = content.length > max ? content.slice(0, max) + '\n... (内容已截断)' : content
      return `### ${title}\n${truncated}`
    })
    lectureBlock = '\n\n## 学情讲义 (用户已生成的针对性学习内容, 可据此解答疑问)\n' + parts.join('\n\n')
  }

  // 项目深度分析结论 + 技术栈: 用户跑过"深度分析"后助手可直接引用, 不必重新调 LLM 分析
  let projectAnalysisBlock = ''
  const pa = context?.projectAnalysis
  if (pa) {
    const parts = []
    if (pa.summary) parts.push(`- 概要: ${pa.summary}`)
    const arch = pa.architecture || {}
    const archBits = []
    if (arch.pattern) archBits.push(`模式 ${arch.pattern}`)
    if (arch.entry_points?.length) archBits.push(`入口点 ${arch.entry_points.join(', ')}`)
    if (pa.complexity?.level) archBits.push(`复杂度 ${pa.complexity.level}`)
    if (archBits.length) parts.push(`- 架构: ${archBits.join(' | ')}`)
    if (pa.tech_stack?.length) parts.push(`- 技术栈: ${pa.tech_stack.join(', ')}`)
    if (Array.isArray(pa.recommendations) && pa.recommendations.length) {
      parts.push(`- 学习建议: ${pa.recommendations.slice(0, 3).map((r, i) => `${i + 1}. ${r}`).join(' ')}`)
    }
    if (parts.length) {
      projectAnalysisBlock = '\n\n## 项目深度分析结论 (用户问项目架构/技术栈/学习建议时据此回答, 不要臆造)\n' + parts.join('\n')
    }
  } else if (context?.projectTechStack?.length) {
    // 无深度分析但有图谱: 注入 AST 自动检测的技术栈
    const ts = context.projectTechStack.slice(0, 10).map((t) => `${t.name}(${t.category})`).join(', ')
    projectAnalysisBlock = '\n\n## 项目技术栈 (项目图谱自动检测)\n- ' + ts
  }

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
        + '\n4. 事实底座抗幻觉: 涉及项目代码时先用 read_file/generate_project_graph 等工具查证真实代码与结构, 严禁凭记忆臆造项目细节; 知识点问题优先用 search_knowledge/get_knowledge_node 查证后再回答, 解释通用概念时也只讲你确信的内容。'
        + '\n5. 简洁: 每轮回复聚焦一个引导点 + 一个追问, 不要长篇大论。'
        + profileBlock
        + lectureBlock
        + projectAnalysisBlock
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
      + '如果你需要查看某个文件来更好地回答问题，使用 tool_call 格式请求读取。\n'
      + '涉及知识点时优先用 search_knowledge/get_knowledge_node 查证, 涉及项目架构时优先用 query_project_graph 查证, 严禁凭记忆臆造细节。'
      + profileBlock
      + lectureBlock
      + projectAnalysisBlock
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
  thinkTextOf,
  splitToolCallChunks,
  stripToolCalls,
} from '@/ide/chat/model'

/** 检测是否在 Electron 环境 */
function hasIpc() {
  return typeof window !== 'undefined' && !!window.api?.fs
}

// ---- 对话历史预算与持久化常量 ----
// 历史 API 消息字符预算 (≈1.2-1.6万 token 量级): 超出从头裁最旧, 治"长对话上下文无限膨胀"
const HISTORY_CHAR_BUDGET = 48000
const CHAT_HISTORY_KEY = 'kmatch-chat-history'
const CHAT_HISTORY_MAX_CHARS = 1500000

/**
 * 构建历史 API 消息 (带预算裁剪)。
 * - assistant 消息经 assistantApiContent 剥 tool_call 块; user 多模态数组原样/取文本
 * - 总字符超 budget 时从头丢弃最旧消息 (至少保留最后一条), 并保证历史以 user 开头
 * sendMessage 与 regenMessage 共用 (此前两处各写一份无裁剪的映射)。
 */
export function buildApiHistory(visible, budget = HISTORY_CHAR_BUDGET) {
  const mapped = visible.map((m) => m.role === 'assistant'
    ? { role: 'assistant', content: assistantApiContent(m) }
    : { role: 'user', content: Array.isArray(m.content) ? m.content : contentTextOf(m) }
  )
  const lenOf = (c) => (typeof c === 'string' ? c.length : JSON.stringify(c).length)
  let total = mapped.reduce((s, m) => s + lenOf(m.content), 0)
  // 最后一条 user 消息是当前回合的锚 — 永不被裁掉 (start 不得越过它)
  let lastUserIdx = -1
  for (let i = mapped.length - 1; i >= 0; i--) {
    if (mapped[i].role === 'user') { lastUserIdx = i; break }
  }
  const floor = lastUserIdx === -1 ? mapped.length - 1 : lastUserIdx
  let start = 0
  while (start < floor && total > budget) {
    total -= lenOf(mapped[start].content)
    start++
  }
  // 裁剪后可能落在 assistant 中间 — 历史以 user 开头 (OpenAI 兼容习惯)
  while (start < floor && mapped[start].role !== 'user') start++
  return mapped.slice(start)
}

/**
 * 序列化消息用于持久化 (localStorage): 丢弃多模态图片段与附件原始数据 (体积),
 * 保留文本内容与助手消息分支结构 — 重启恢复后 regen/版本导航仍可用。
 */
export function serializeMessages(messages) {
  return JSON.parse(JSON.stringify(messages.map((m) => {
    const clone = { ...m }
    if (Array.isArray(clone.content)) {
      clone.content = clone.content.filter((p) => p && p.type === 'text')
    }
    delete clone._attachments
    return clone
  })))
}

/** 校验恢复数据: 只收带字符串 id 的 user/assistant 消息; 坏数据返回空数组 (不让脏存储崩会话)。 */
export function restoreMessages(json) {
  try {
    const arr = JSON.parse(json)
    if (!Array.isArray(arr)) return []
    return arr.filter((m) => m && typeof m.id === 'string'
      && (m.role === 'user' || m.role === 'assistant'))
  } catch {
    return []
  }
}

/** 持久化体积兜底: JSON 超 maxChars 时从头丢最旧消息 (至少保留 2 条), 返回 JSON 串。 */
export function fitPersistJson(messages, maxChars = CHAT_HISTORY_MAX_CHARS) {
  const trimmed = [...messages]
  let json = JSON.stringify(trimmed)
  while (json.length > maxChars && trimmed.length > 2) {
    trimmed.shift()
    json = JSON.stringify(trimmed)
  }
  return json
}

/**
 * 活动文件内容缓存 (path → {mtime, content}):
 * 每次发消息都注入 active file 全文, 未编辑时的重读是纯浪费 IPC 往返;
 * stat 的 mtimeMs 未变直接用缓存, 文件被改动 (含外部改动) 自动失效。
 * stat 失败时退回直读不缓存, 保证正确性。
 */
const activeFileCache = new Map()

async function readActiveFileCached(filePath) {
  let mtime = null
  try { mtime = (await window.api.fs.stat(filePath))?.mtime } catch { /* stat 失败退直读 */ }
  const hit = activeFileCache.get(filePath)
  if (mtime != null && hit && hit.mtime === mtime) return hit.content
  const content = await window.api.fs.readFile(filePath)
  if (mtime != null) {
    if (activeFileCache.size >= 32) activeFileCache.delete(activeFileCache.keys().next().value)
    activeFileCache.set(filePath, { mtime, content })
  }
  return content
}

/**
 * 助手消息序列化给后端 API: 剥离 ```tool_call fence。
 * 全工具调用消息剥离后内容为空 → 用占位文本 (向厂商发空 assistant content 会使
 * 部分模型响应异常: 重复调工具 / 输出"2"之类无意义短答, 为空消息问题的辅助修复)。
 */
export function assistantApiContent(msg) {
  const stripped = stripToolCalls(contentTextOf(msg))
  return stripped || '（工具调用已执行，结果见后续对话）'
}

// ---- issue: 流式统计 (首 token / 速率 / 缓存命中 / 输入输出 token) ----
function _fmtTok(n) {
  if (n == null) return ''
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M'
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'k'
  return String(n)
}

/** 把最近一次回复的流式统计格式化为展示文本 (纯函数, 单测覆盖)。 */
export function formatChatStats(s) {
  if (!s) return ''
  const parts = []
  if (s.firstTokenSec != null) parts.push(`首 token ${s.firstTokenSec}s`)
  if (s.tokPerSec != null) parts.push(`${s.tokPerSec} tok/s`)
  if (s.cacheHitPct != null) parts.push(`缓存命中 ${s.cacheHitPct}%`)
  if (s.promptTokens != null) parts.push(`输入 ${_fmtTok(s.promptTokens)} tok`)
  if (s.completionTokens != null) parts.push(`输出 ${_fmtTok(s.completionTokens)} tok`)
  return parts.join(' · ')
}

/**
 * 把一轮工具执行结果汇总成回喂 AI 的 user 消息文本 (C1.4 单一源)。
 * sendMessage 与 regenMessage 共用, 消除原先 regen 的精简重复副本。
 */
export function summarizeToolResults(toolResults) {
  return toolResults.map((tr) => {
    const r = tr.result
    if (r.error) return `工具 ${tr.call.tool} 失败: ${r.error}`
    // hint 型降级结果 (未完成测评/未解析项目的引导) 须回喂 AI——否则它会看到
    // "0 个节点"之类的空数据而误解; 成功态也带 hint 的工具 (generate_learning_resources)
    // 含 generated 主数据, 不会命中此分支。
    if (r.hint && r.count == null && r.generated == null && r.entity_count == null) {
      return `工具 ${tr.call.tool} 提示: ${r.hint}`
    }
    // write_file 才有 written=true; generate_project_graph 的 written 是"是否落 Neo4j"语义不同,
    // 故 written 分支限定 write_file, 避免吞掉 graph 摘要 (review 发现)
    if (r.written && tr.call.tool === 'write_file') return `文件 ${r.path} 已成功写入 (${r.bytes} 字节)。`
    if (r.content) {
      // F7: 截断 6000 字符时明示, 让 AI 知道被截断 (大文件推理不再静默降级)
      const max = 6000
      const full = r.content
      const truncated = full.length > max ? full.slice(0, max) + `\n... (内容已截断, 共 ${full.length} 字符, 仅显示前 ${max}; 如需后续内容请指明行号范围)` : full
      return `文件 ${r.path} 内容:\n\`\`\`\n${truncated}\n\`\`\``
    }
    if (r.files) return `目录 ${r.path} 内容:\n${r.files.join('\n')}`
    if (r.tool === 'generate_project_graph') {
      const s = r.stats || {}
      const ents = (r.entities || []).slice(0, 20)
        .map((e) => `- ${e.kind} ${e.qualified_name} (行${e.line_start || '?'}-${e.line_end || '?'})`)
        .join('\n')
      return `项目图谱已生成 (${r.sourcePath}, written=${r.written}). 统计: 模块${s.module || 0}/类${s.class || 0}/函数${s.function || 0}/方法${s.method || 0}.\n实体清单:\n${ents || '(无)'}`
    }
    if (r.tool === 'code_review') {
      const rv = r.review || {}
      const dims = rv.dimensions || {}
      const dimLines = Object.entries(dims).map(([k, v]) => `${k}: ${((v.score ?? 0) * 100).toFixed(0)}%`).join(', ')
      const highIssues = (Object.values(dims).flatMap((d) => d.issues || []).filter((i) => i.severity === 'high')).slice(0, 5)
        .map((i) => `- [high] ${i.problem}`).join('\n')
      return `代码审查结果 (${r.sourcePath}): verdict=${rv.verdict}, overall=${rv.overall_score != null ? (rv.overall_score * 100).toFixed(0) + '%' : '?'}, 通过阈值0.85. 维度: ${dimLines}.${rv.retry_hint ? ' 提示: ' + rv.retry_hint : ''}${highIssues ? '\n高危问题:\n' + highIssues : ''}`
    }
    if (r.tool === 'code_test') {
      const rp = r.report || {}
      const sm = rp.summary || {}
      const cov = rp.coverage || {}
      const fails = (rp.failed_tests || []).slice(0, 5)
        .map((f) => `- ${f.test_name}: ${f.suggestion || f.error_type || '失败'}`).join('\n')
      return `代码测试结果 (${r.sourcePath}): ${sm.passed || 0}/${sm.total || 0} 通过, 行覆盖${((cov.line_coverage || 0) * 100).toFixed(0)}%, 分支覆盖${((cov.branch_coverage || 0) * 100).toFixed(0)}%, 函数覆盖${((cov.function_coverage || 0) * 100).toFixed(0)}%.${rp.note ? ' 备注: ' + rp.note : ''}${fails ? '\n失败用例:\n' + fails : ''}${rp.rejected ? ' (已拒绝: ' + (rp.reject_reason || '') + ')' : ''}`
    }
    // ---- P3 只读知识/图谱工具: 结果必须回喂 LLM (此前缺分支被 filter(Boolean) 静默丢弃,
    //      模型看不到 20 个路径节点 → 重复调工具 / 胡答"2" 的根因) ----
    if (r.tool === 'search_knowledge') {
      const nodes = (r.nodes || []).slice(0, 20)
        .map((n) => `- ${n.node_id} ${n.name} (${n.category || '未分类'} · 难度${n.difficulty ?? '?'})${n.summary ? ': ' + String(n.summary).slice(0, 80) : ''}`)
        .join('\n')
      return `知识检索结果 (${r.query}): 命中 ${r.count || 0} 个节点\n${nodes || '(无)'}`
    }
    if (r.tool === 'get_learning_path') {
      const path = (r.learning_path || []).slice(0, 20)
        .map((n, i) => `${i + 1}. ${n.node_id} ${n.name} (难度${n.difficulty ?? '?'}${n.category ? ' · ' + n.category : ''})`)
        .join('\n')
      const hours = r.estimated_total_hours != null ? `, 预计 ${r.estimated_total_hours}h` : ''
      return `个性化学习路径: 共 ${r.count || 0} 个节点${hours}\n${path || '(无)'}`
    }
    if (r.tool === 'export_graph_diagram') {
      return `图谱已导出为 Excalidraw 文件: ${r.path} (节点 ${r.nodes ?? '?'} 个, 连线 ${r.edges ?? 0} 条)。告诉用户可在 excalidraw.com 或 VS Code Excalidraw 插件中打开继续编辑。`
    }
    if (r.tool === 'get_knowledge_node') {
      return `知识点 ${r.node_id} ${r.name || ''} (难度${r.difficulty ?? '?'}${r.category ? ' · ' + r.category : ''})\n摘要: ${r.summary || '(无)'}`
    }
    if (r.tool === 'query_project_graph') {
      const ents = (r.entities || []).slice(0, 20)
        .map((e) => `- ${e.kind} ${e.qualified_name || e.name}`)
        .join('\n')
      const rels = (r.relations || []).slice(0, 20)
        .map((e) => `- ${e.source} ${e.label || e.relation || '→'} ${e.target}`)
        .join('\n')
      return `项目图谱 ${r.project_id || ''}: ${r.entity_count ?? 0} 实体 / ${r.relation_count ?? 0} 关系\n实体:\n${ents || '(无)'}${rels ? `\n关系:\n${rels}` : ''}`
    }
    if (r.tool === 'web_search') {
      const results = (r.results || []).slice(0, 8)
        .map((x) => `- ${x.title}: ${x.url}${x.snippet ? '\n  ' + String(x.snippet).slice(0, 120) : ''}`)
        .join('\n')
      return `联网搜索 (${r.query}): ${r.count || 0} 条结果\n${results || '(无)'}`
    }
    if (r.tool === 'search_weak_topics') {
      const results = (r.results || []).slice(0, 8)
        .map((x) => `- ${x.title}: ${x.url} (${x.target_node_id || '无溯源'})${x.snippet ? '\n  ' + String(x.snippet).slice(0, 100) : ''}`)
        .join('\n')
      return `薄弱点联网搜索 (${(r.weak_topics || []).join('、') || '画像薄弱点'}): ${r.count || 0} 条结果, 已落入「学习资源」页\n${results || '(无)'}`
    }
    if (r.tool === 'generate_learning_resources') {
      return `学习资源生成完成 (strategy=${r.strategy}): 新增 ${r.generated ?? 0} 份资源, 覆盖 ${r.node_count ?? 0} 个节点。${r.hint || '资源已落入「学习资源」页'}`
    }
    return ''
  }).filter(Boolean).join('\n\n')
}

export const useChatStore = defineStore('chat', () => {
  // ============================================================
  // 状态
  // ============================================================
  const messages = ref([])

  // ---- 对话持久化 (重启恢复当前会话) ----
  // store 初始化时从 localStorage 恢复; 变更经 800ms 防抖回写 (流式期间高频变更只落最后一次)。
  // 图片附件不入存储 (体积), 恢复后附件消息仅剩文本段。
  try {
    const saved = localStorage.getItem(CHAT_HISTORY_KEY)
    if (saved) {
      const restored = restoreMessages(saved)
      if (restored.length) messages.value = restored
    }
  } catch { /* localStorage 不可用则不恢复 */ }
  let _persistTimer = null
  watch(messages, () => {
    if (_persistTimer) clearTimeout(_persistTimer)
    _persistTimer = setTimeout(() => {
      try {
        localStorage.setItem(CHAT_HISTORY_KEY, fitPersistJson(serializeMessages(messages.value)))
      } catch { /* 配额满等写失败, 尽力而为 */ }
    }, 800)
  }, { deep: true })

  // ---- 附件 (Spec A 图片上传, 阶段PR-5) ----
  // 附件单元: { id, name, size, mimeType, base64DataUrl, thumbDataUrl }
  // base64DataUrl = 全分辨率 data URL (发往后端); thumbDataUrl = ≤200px JPEG (仅 UI 预览)
  const pendingAttachments = ref([])

  const ALLOWED_MIME = ['image/png', 'image/jpeg', 'image/webp', 'image/gif']
  const MAX_SIZE = 5 * 1024 * 1024
  const MAX_COUNT = 5

  function _readAsDataURL(file) {
    return new Promise((resolve, reject) => {
      const fr = new FileReader()
      fr.onload = () => resolve(fr.result)
      fr.onerror = () => reject(new Error('读取文件失败'))
      fr.readAsDataURL(file)
    })
  }

  async function _makeThumb(dataUrl, max = 200) {
    // 单测环境 (jsdom) 无 canvas (getContext('2d') 返回 null); 直接返回原 dataUrl
    if (typeof document === 'undefined' || !document.createElement('canvas').getContext('2d')) {
      return dataUrl
    }
    return new Promise((resolve) => {
      const img = new Image()
      img.onload = () => {
        const ratio = Math.min(1, max / Math.max(img.width, img.height))
        const w = Math.round(img.width * ratio), h = Math.round(img.height * ratio)
        const cvs = document.createElement('canvas')
        cvs.width = w; cvs.height = h
        cvs.getContext('2d').drawImage(img, 0, 0, w, h)
        try { resolve(cvs.toDataURL('image/jpeg', 0.8)) }
        catch { resolve(dataUrl) }
      }
      img.onerror = () => resolve(dataUrl)
      img.src = dataUrl
    })
  }

  async function addAttachment(file) {
    if (!ALLOWED_MIME.includes(file.type)) {
      throw new Error(`不支持的文件类型: ${file.type || '未知'}（仅 PNG/JPEG/WEBP/GIF）`)
    }
    if (file.size > MAX_SIZE) {
      throw new Error(`文件超过 5MB: ${(file.size / 1024 / 1024).toFixed(1)}MB`)
    }
    if (pendingAttachments.value.length >= MAX_COUNT) {
      throw new Error(`单条消息最多 ${MAX_COUNT} 张图`)
    }
    const dataUrl = await _readAsDataURL(file)
    const thumb = await _makeThumb(dataUrl)
    pendingAttachments.value = [...pendingAttachments.value, {
      id: `att_${_nextId()}`,
      name: file.name || 'image',
      size: file.size,
      mimeType: file.type,
      base64DataUrl: dataUrl,
      thumbDataUrl: thumb,
    }]
  }

  function removeAttachment(id) {
    pendingAttachments.value = pendingAttachments.value.filter((a) => a.id !== id)
  }

  function clearAttachments() { pendingAttachments.value = [] }

  const streaming = ref(false)
  const currentStreamId = ref(null)
  const error = ref(null)
  const abortController = ref(null)
  // issue: 最近一次回复的流式统计 (input 下方展示)
  const lastStats = ref(null)
  let _statsStart = 0
  let _streamStats = null

  // ---- 输入框草稿 (图谱/项目图谱详情面板"问 AI"预填通路) ----
  // 跨组件共享: 图谱视图 setDraft 预填 → 切到 chat 视图 AssistantPanel 绑定带出,
  // 用户可编辑后再发送 (不自动发送, 保留确认感)。
  const draft = ref('')
  function setDraft(text) { draft.value = text ?? '' }

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
        // issue-62: LLM 未配置 → 引导性文案 (非阻塞提示, 不再是一句冰冷报错)
        const friendly = /LLM 未配置|未设置 API Key|API Key/i.test(String(data.error))
          ? 'LLM 未配置，请到 设置 → AI 助手 配置厂商/模型/API Key 后再试'
          : data.error
        appendTextChunk(activeChunksOf(assistantMsg), 'content', `❌ ${friendly}`)
        const e = new Error(data.error)
        e.streamError = true // 已渲染 chunk, 调用方勿重复
        return e
      }
      if (data.reasoning) appendTextChunk(activeChunksOf(assistantMsg), 'think', data.reasoning)
      if (data.delta) {
        // 首 token 计时 (流式统计)
        if (_streamStats && _streamStats.firstDeltaMs == null) {
          _streamStats.firstDeltaMs = performance.now() - _statsStart
        }
        appendTextChunk(activeChunksOf(assistantMsg), 'content', data.delta)
      }
      if (data.usage && _streamStats) _streamStats.usage = data.usage
    } catch { /* skip malformed block */ }
    return null
  }

  // SSE 流式: 传输层抽至 useChatStream (C1.3); 这里只构建 body + 解析 block。
  async function _streamResponse(apiMessages, assistantMsg) {
    const ai = useAiSettingsStore()
    const body = {
      messages: apiMessages,
      stream: true,
      // issue-75: 推理内容计入 token, 8192 在长思考下会耗尽导致无正文
      max_tokens: 16384,
      model: ai.model,
      api_key: ai.apiKey || undefined,
      base_url: ai.getBaseUrl() || undefined,
      protocol: ai.providerMeta().protocol || 'openai',
      reasoning_mode: ai.reasoningMode,
    }

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

  // _readProjectPyFiles 已提取至 @/api/project (readProjectPyFiles), 供 chat 工具与 store 自动解析复用

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
        // 项目级: path 是目录 -> 读工作区所有 .py 多文件解析
        const isDir = call.path && call.path !== '' && !call.path.endsWith('.py')
        let body, sourcePath
        if (isDir) {
          const sources = await readProjectPyFiles(call.path)
          if (!Object.keys(sources).length) return { error: '项目中没有可解析的 .py 文件' }
          body = { source_type: 'files', sources, write_to_neo4j: call.write_to_neo4j !== false }
          sourcePath = call.path
        } else {
          const src = await _resolveCode(call)
          if (src.error) return { error: src.error }
          body = { source_type: 'text', code: src.code, filename: call.filename || 'main.py', write_to_neo4j: call.write_to_neo4j !== false }
          sourcePath = src.sourcePath
        }
        const r = await _delegate('/api/project/parse', body)
        if (!r.ok) return { error: r.error }
        const result = {
          tool: 'generate_project_graph',
          ...normalizeGraphResponse(r.data, sourcePath),
        }
        // 供 4b Monaco 符号联动
        try { useProjectGraphStore().setGraph(result, sourcePath) } catch { /* store 未就绪不影响 */ }
        return result
      }
      if (call.tool === 'code_review') {
        if (!call.target_direction) return { error: '缺少 target_direction 参数（开发目标方向）' }
        const src = await _resolveCode(call)
        if (src.error) return { error: src.error }
        const body = withOverrides({
          code: src.code,
          target_direction: call.target_direction,
          knowledge_node_ids: call.knowledge_node_ids || null,
        })
        const r = await _delegate('/api/project/review', body)
        if (!r.ok) return { error: r.error }
        return { tool: 'code_review', review: r.data, sourcePath: src.sourcePath }
      }
      if (call.tool === 'code_test') {
        if (!call.target_direction) return { error: '缺少 target_direction 参数（开发目标方向）' }
        const src = await _resolveCode(call)
        if (src.error) return { error: src.error }
        const body = withOverrides({
          source_type: 'text',
          code: src.code,
          filename: call.filename || 'main.py',
          target_direction: call.target_direction,
          knowledge_node_ids: call.knowledge_node_ids || null,
          mode: call.mode || 'generate',
        })
        // code_test (LLM 生成 + pytest 执行) 可达 60s+, 放宽超时
        const r = await _delegate('/api/project/test', body, 180000)
        if (!r.ok) return { error: r.error }
        // W5: 记录测试摘要 → 学情 submit 时作 practical_level 证据 (practical_evidence)
        try {
          const sm = r.data?.report?.summary
          if (sm) useProjectGraphStore().setLastTestReport({ passed: sm.passed, total: sm.total })
        } catch { /* store 未就绪不影响 */ }
        return { tool: 'code_test', report: r.data, sourcePath: src.sourcePath }
      }

      if (call.tool === 'web_search') {
        if (!call.query) return { error: '缺少 query 参数（搜索词）' }
        // 传 UI 配置的 tavilyKey (存 localStorage), 后端优先用传入 key, 免去 .env 配置
        // max_results 钳制到后端约束 (1-8), 防模型传越界值 422
        const maxResults = Math.min(8, Math.max(1, parseInt(call.max_results, 10) || 3))
        const r = await _delegate('/api/search/web', { query: call.query, max_results: maxResults, tavily_key: aiSettings.tavilyKey || undefined })
        if (!r.ok) return { error: r.error }
        const results = (r.data?.results || []).map((x) => ({
          title: x.title, url: x.url, snippet: x.snippet,
        }))
        // 结果落学习资源模块 (Learning.vue "联网资源" tab 读取)
        try { useLearningResourcesStore().addWebResources(call.query, results) } catch { /* store 未就绪不影响 */ }
        return { tool: 'web_search', query: call.query, results, count: results.length }
      }

      if (call.tool === 'search_weak_topics') {
        // 按画像薄弱点批量联网搜索 (issue-68): 结果带 target_node_id 溯源, 比泛泛 web_search 更贴合
        const { useAssessmentStore } = await import('@/stores/assessment')
        const aStore = useAssessmentStore()
        const weak = (Array.isArray(aStore.profile?.weak_topics) ? aStore.profile.weak_topics : []).slice(0, 5)
        if (!weak.length) {
          return {
            tool: 'search_weak_topics',
            hint: '用户尚未完成学情测评或暂无薄弱点, 无法按薄弱点搜索。请引导用户先完成测评, 或改用 web_search 泛搜索。',
          }
        }
        const topics = (Array.isArray(call.topics) && call.topics.length ? call.topics : weak.map((t) => t.node_id))
          .map((nid) => {
            const hit = weak.find((t) => t.node_id === nid)
            return { node_id: nid, name: (hit && (hit.name || '')) || '' }
          })
          .filter((t) => t.node_id)
        const maxPerTopic = Math.min(5, Math.max(1, parseInt(call.max_per_topic, 10) || 2))
        const r = await _delegate('/api/search/weak-topics', {
          topics,
          max_per_topic: maxPerTopic,
          direction: aStore.profile.target_direction || undefined,
          tavily_key: aiSettings.tavilyKey || undefined,
        })
        if (!r.ok) return { error: r.error }
        const results = (r.data?.results || []).map((x) => ({
          title: x.title, url: x.url, snippet: x.content || x.snippet || '', target_node_id: x.target_node_id,
        }))
        try { useLearningResourcesStore().addFeedbackLinks(results) } catch { /* store 未就绪不影响 */ }
        return {
          tool: 'search_weak_topics', count: results.length, results,
          weak_topics: topics.map((t) => t.node_id),
        }
      }

      if (call.tool === 'get_knowledge_node') {
        if (!call.node_id) return { error: '缺少 node_id 参数（知识点编号）' }
        try {
          const n = await getNode(call.node_id)
          return {
            tool: 'get_knowledge_node', node_id: call.node_id,
            name: n.name, summary: n.summary, difficulty: n.difficulty, category: n.category,
          }
        } catch (e) { return { error: e.response?.data?.detail || e.message || '知识点查询失败' } }
      }

      if (call.tool === 'generate_learning_resources') {
        // 调后端 content_generator 图谱驱动生成结构化资源 (讲义/实操/测试), 落「学习资源」模块
        const { useAssessmentStore } = await import('@/stores/assessment')
        const aStore = useAssessmentStore()
        // 降级: 未完成测评时返回引导文案而非硬报错 (AI 可据此引导用户)
        if (!aStore.sessionId || !aStore.profile) {
          return {
            tool: 'generate_learning_resources',
            hint: '用户尚未完成学情测评, 无法生成个性化资源。请引导用户前往「学习会话」完成答题测评, 之后再来生成学习资源。',
          }
        }
        const strategy = call.strategy || aStore.feedbackStrategy || 'scaffold'
        // #30: feedback 逐节点 LLM 再生常超 60s, 显式放宽到 150s
        const r = await _delegate('/api/diagnostics/feedback', {
          session_id: aStore.sessionId, strategy, profile: aStore.profile,
          tavily_key: aiSettings.tavilyKey || undefined,
        }, 150000)
        if (!r.ok) return { error: r.error }
        // 合并 resources 到 generatedContent (Learning.vue 读)
        const existing = aStore.generatedContent || { resources: [] }
        const newRes = r.data?.resources || []
        aStore.generatedContent = {
          ...existing,
          resources: [...(existing.resources || []), ...newRes],
          node_count: r.data?.node_count ?? existing.node_count,
        }
        return { tool: 'generate_learning_resources', strategy, generated: newRes.length, node_count: r.data?.node_count, hint: '资源已落入「学习资源」页, 学习路径图谱在「知识图谱」页' }
      }

      // ---- P3: 只读知识/项目图谱查询工具 (助手"看到"事实底座, 减少幻觉) ----
      if (call.tool === 'search_knowledge') {
        if (!call.query) return { error: '缺少 query 参数（检索词）' }
        const topK = Math.min(10, Math.max(1, parseInt(call.top_k, 10) || 5))
        try {
          const results = await semanticSearch(call.query, topK)
          const nodes = (results || []).map((n) => ({
            node_id: n.node_id, name: n.name, summary: n.summary,
            difficulty: n.difficulty, category: n.category,
          }))
          return { tool: 'search_knowledge', query: call.query, count: nodes.length, nodes }
        } catch (e) { return { error: e.response?.data?.detail || e.message || '知识检索失败' } }
      }

      if (call.tool === 'get_learning_path') {
        const { useAssessmentStore } = await import('@/stores/assessment')
        const aStore = useAssessmentStore()
        if (!aStore.profile) {
          return {
            tool: 'get_learning_path',
            hint: '用户尚未完成学情测评, 无法生成个性化学习路径。请引导用户前往「学习会话」完成答题测评。',
          }
        }
        const knownIds = (aStore.profile.known_topics || []).map((t) => t.node_id)
        const weakIds = (aStore.profile.weak_topics || []).map((t) => t.node_id)
        const level = Math.min(4, Math.max(1, parseInt(call.level, 10) || 2))
        // 后端 PathRequest 校验 le=20 (graph.py), 传大值会 422 — 前端钳到同界
        const maxNodes = Math.min(20, Math.max(1, parseInt(call.max_nodes, 10) || 20))
        try {
          const data = await assemblePath({ knownIds, weakIds, level, maxNodes })
          const path = (data?.learning_path || data?.nodes || []).map((n) => ({
            node_id: n.node_id, name: n.name, difficulty: n.difficulty, category: n.category,
          }))
          return {
            tool: 'get_learning_path', count: path.length, learning_path: path,
            estimated_total_hours: data?.estimated_total_hours ?? null,
          }
        } catch (e) { return { error: e.response?.data?.detail || e.message || '学习路径查询失败' } }
      }

      if (call.tool === 'query_project_graph') {
        // project_id 优先用参数, 否则取 store / localStorage 最近一次
        const pgStore = useProjectGraphStore()
        let pid = call.project_id || pgStore.graph?.projectId
        if (!pid) {
          try { pid = localStorage.getItem('kmatch-last-project-id') } catch { /* ignore */ }
        }
        if (!pid) {
          return {
            tool: 'query_project_graph',
            hint: '尚未解析过项目。请引导用户打开一个 Python 项目 (会自动解析成知识图谱), 之后再查询。',
          }
        }
        try {
          const data = await getProjectGraph(pid)
          const result = normalizeGraphResponse(data, '')
          return {
            tool: 'query_project_graph', project_id: pid,
            entity_count: result.entities.length,
            relation_count: result.relations.length,
            entities: result.entities.map((e) => ({ name: e.name, kind: e.kind, qualified_name: e.qualified_name })),
            relations: result.relations,
          }
        } catch (e) {
          const status = e.response?.status
          if (status === 404) {
            try { localStorage.removeItem('kmatch-last-project-id') } catch { /* ignore */ }
            return { error: `项目图谱不存在: ${pid} (可能后端重启或已删除), 请重新打开项目解析` }
          }
          return { error: e.response?.data?.detail || e.message || '项目图谱查询失败' }
        }
      }

      // ---- W3: 图谱 → .excalidraw 确定性导出 (坐标由 excalidrawExport 生成, 不走 LLM) ----
      if (call.tool === 'export_graph_diagram') {
        const want = call.graph // 'knowledge' | 'project' | undefined
        const pgStore = useProjectGraphStore()
        let nodes = null
        let edges = null
        let label = ''

        if (want !== 'knowledge' && pgStore.graph?.entities?.length) {
          // 项目图谱: 实体 + 调用关系都在 store, 零额外请求
          nodes = pgStore.graph.entities.map((e) => ({
            id: String(e.id), label: e.qualified_name || e.name || String(e.id),
          }))
          edges = (pgStore.graph.relations || []).map((r) => ({ source: String(r.source), target: String(r.target) }))
          label = `项目图谱-${pgStore.graph.projectId}`
        } else if (want === 'project') {
          // 显式点名项目图谱但不可用 → 明确告知, 不静默改导知识图谱
          return { tool: 'export_graph_diagram', hint: '项目图谱尚不可用 (需先打开一个 Python 项目自动解析)。请引导用户先打开项目, 或改导知识图谱。' }
        } else {
          // 知识图谱: 学习路径节点 + 逐节点前置依赖 (≤20 并行请求, 同 KnowledgeGraph 页做法)
          const { useAssessmentStore } = await import('@/stores/assessment')
          const aStore2 = useAssessmentStore()
          const path = aStore2.knowledgeGraph?.learning_path || []
          if (!path.length) {
            return { tool: 'export_graph_diagram', hint: '当前没有可导出的图谱 (知识图谱需先完成测评, 项目图谱需先打开 Python 项目)。请引导用户先准备图谱数据。' }
          }
          nodes = path.map((n) => ({ id: n.node_id, label: n.name || n.node_id }))
          edges = []
          try {
            const ids = path.map((n) => n.node_id).slice(0, 20)
            const prereqLists = await Promise.all(ids.map(async (nid) => {
              try { return { nid, pres: await getPrerequisites(nid) } } catch { return { nid, pres: [] } }
            }))
            const inPath = new Set(ids)
            const seen = new Set()
            for (const { nid, pres } of prereqLists) {
              for (const p of pres || []) {
                const pid2 = p?.node_id || p
                const key = `${pid2}->${nid}`
                if (inPath.has(pid2) && !seen.has(key)) {
                  seen.add(key)
                  edges.push({ source: pid2, target: nid })
                }
              }
            }
          } catch { /* 前置拉取失败 → 仅导出节点无线边, 不阻断 */ }
          label = `知识图谱-${aStore2.profile?.name || '学习路径'}`
        }

        const scene = graphToExcalidraw(nodes, edges)
        // 文件名消毒: 标签可能含路径分隔符/Windows 非法字符
        const safeLabel = label.replace(/[\\/:*?"<>|]/g, '_')
        const fileName = `KMatch-${safeLabel}-${Date.now()}.excalidraw`
        const json = JSON.stringify(scene)

        // 桌面端写入工作区根目录 (非代码文件, 不走审批门); 浏览器 dev 模式降级为下载
        let savedPath = fileName
        if (hasIpc()) {
          await window.api.fs.writeFile(fileName, json)
          try {
            const ws = useWorkspaceStore()
            await ws.refreshTree?.()
          } catch { /* 刷新失败不影响导出 */ }
        } else {
          downloadExcalidraw(scene, fileName)
          savedPath = `(浏览器下载) ${fileName}`
        }
        return { tool: 'export_graph_diagram', path: savedPath, nodes: nodes.length, edges: edges.length }
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
      if (a.feedbackContent) ctx.feedbackContent = a.feedbackContent
    } catch { /* assessment store 未就绪, 忽略 */ }

    // 项目深度分析结论 + 技术栈 (跑过"深度分析"后助手可直接引用; 有图谱无分析时注入 AST 技术栈检测)
    try {
      const pg = useProjectGraphStore()
      if (pg.analysis) ctx.projectAnalysis = pg.analysis
      if (pg.graph?.entities?.length) ctx.projectTechStack = detectTechStack(pg.graph.entities)
    } catch { /* projectGraph store 未就绪, 忽略 */ }

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
        ctx.fileContent = await readActiveFileCached(ws.activeFile)
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
    // 流式统计起点
    _statsStart = performance.now()
    _streamStats = { firstDeltaMs: null, usage: null }
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

    // issue: 结算流式统计 (首 token / tok-per-sec / 缓存命中)
    if (_streamStats) {
      const u = _streamStats.usage || {}
      const complete = u.completion_tokens || 0
      const firstMs = _streamStats.firstDeltaMs
      const elapsed = performance.now() - (_statsStart + (firstMs || 0))
      lastStats.value = {
        firstTokenSec: firstMs != null ? +(firstMs / 1000).toFixed(1) : null,
        tokPerSec: complete && elapsed > 0 ? Math.round(complete / (elapsed / 1000)) : null,
        promptTokens: u.prompt_tokens ?? null,
        completionTokens: complete || null,
        cacheHitPct: (u.prompt_cache_hit_tokens != null && u.prompt_tokens)
          ? +((u.prompt_cache_hit_tokens / u.prompt_tokens) * 100).toFixed(1)
          : null,
      }
      _streamStats = null
    }

    // issue-75: 长思考耗尽 token → 只有 think 无正文, 明确提示而非静默空白
    if (!contentTextOf(assistantMsg) && thinkTextOf(assistantMsg)) {
      appendTextChunk(activeChunksOf(assistantMsg), 'content',
        '⚠️ 思考超长被截断，未生成回复。可点击「重试」；若反复出现，请在 AI 设置中调低思考模式。')
    }

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
    // issue-07/m3: 统一用 isBusy (流中 + 审批门 + 工具执行窗口) 做防并发闸,
    // 旧实现只看 streaming, 工具循环窗口(System 程序化入口可直接调)可并发起新循环污染对话。
    if (isBusy.value || !userContent.trim()) return

    error.value = null
    abortController.value = new AbortController()

    // 添加用户消息 (含附件 → 多模态 content 数组; 否则 string payload → chunks)
    // 注: 无附件时走 string payload 让 chunks 携带文本 (contentTextOf 经 activeChunksOf 读取,
    //     兼容旧消息/工具回喂/分支测试 m.chunks[0].content 查找); 有附件时 content 字段存数组,
    //     chunks 留空, contentTextOf 经 Array.isArray 分支取 text 段。
    const attachments = [...pendingAttachments.value]
    const userContentNorm = userContent.trim()
    if (attachments.length === 0) {
      _addMessage('user', userContentNorm)
    } else {
      const userPayload = [
        { type: 'text', text: userContentNorm },
        ...attachments.map((a) => ({
          type: 'image_url',
          image_url: { url: a.base64DataUrl },
        })),
      ]
      _addMessage('user', null, { content: userPayload, _attachments: attachments })
    }
    clearAttachments()

    // 收集工作区上下文
    const context = await _collectContext()

    // 工具循环 (最多 MAX_TOOL_ROUNDS 轮)
    let toolRound = 0

    while (toolRound < MAX_TOOL_ROUNDS) {
      toolRound++

      // 构建 API 消息列表 (assistant content 去掉 tool_call 块; chunks 模型无 tool 角色)
      // 用 visibleMessages: regen 隐藏的尾随消息不应进 API 历史 (见 regenMessage)
      // buildApiHistory 带预算裁剪 — 长对话不再全量进上下文
      const systemMsg = buildSystemPrompt(context)
      const historyMsgs = buildApiHistory(visibleMessages.value)
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
      const historyMsgs = buildApiHistory(visibleSoFar)
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
    lastStats.value = null
    _streamStats = null
    // 清空即清持久化 (下次启动不再恢复旧会话)
    try { localStorage.removeItem(CHAT_HISTORY_KEY) } catch { /* noop */ }
  }

  return {
    messages, visibleMessages, streaming, currentStreamId, error,
    hasMessages,
    isBusy, lastStats,
    // 输入框草稿 (图谱"问 AI"预填)
    draft, setDraft,
    // write_file 审批门 (阶段3.1)
    pendingApproval, resolveApproval,
    // 启发式导学模式 (阶段4③)
    tutorMode, setTutorMode,
    // 对话
    sendMessage, stopStreaming, clearMessages,
    setVersion, regenMessage,
    // 附件 (Spec A 图片上传, 阶段PR-5)
    pendingAttachments, addAttachment, removeAttachment, clearAttachments,
  }
})
