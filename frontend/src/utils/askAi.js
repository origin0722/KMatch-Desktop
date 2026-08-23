/**
 * "问 AI"问题构造 (P1: 图谱/项目图谱详情 → AI 助手预填通路)
 *
 * 纯函数: 组件收集上下文后调 buildXxx 生成预填文本, 经 chat.setDraft 带入
 * 助手输入框 (用户可编辑后发送, 不自动发送)。
 */

/** issue-70: 知识图谱专业导读预填 (对话式导航, AI 依 get_learning_path/search_knowledge 工具回答)。 */
export const GRAPH_GUIDE_PROMPT =
  '请以对话形式带我导读当前知识图谱：先结合我的学情画像说明学习路径的起点，'
  + '然后逐个知识点讲解「它是什么、为什么要学、怎么检验我是否掌握」，'
  + '每讲完一个知识点就停下来问我是否继续或有什么疑问，'
  + '如果我想深入某个点，就先用知识图谱工具查证再展开，不要凭记忆编造。'

/** issue-70: 图谱详情面板"图谱导读"按钮预填 (与空态 chip 同源)。 */
export const graphGuidePrompt = () => GRAPH_GUIDE_PROMPT

/**
 * 知识点节点 → 苏格拉底式提问预填
 * @param {Object} node 选中节点 {node_id, name, difficulty, mastery, summary, key_points}
 * @param {Array} prereqNames 前置依赖可读名列表
 * @returns {string}
 */
export function buildNodeQuestion(node, prereqNames = []) {
  const n = node || {}
  const masteryPct = Math.round((n.mastery ?? 0) * 100)
  const kps = (n.key_points || []).slice(0, 4).map((k) => `- ${k}`).join('\n')
  const lines = [
    `我在学习图谱里遇到了知识点「${n.name || n.node_id || '未知知识点'}」（难度 ${'⭐'.repeat(n.difficulty ?? 1)}，我当前掌握度 ${masteryPct}%），还是不太理解。`,
  ]
  if (kps) lines.push(`它要求掌握：\n${kps}`)
  if (prereqNames.length) lines.push(`前置知识：${prereqNames.slice(0, 6).join('、')}`)
  if (n.summary) lines.push(`概要：${String(n.summary).slice(0, 120)}`)
  lines.push('请循序渐进地帮我理解它：先问我目前卡在哪，再用提示引导我自己想通，不要直接灌输答案。')
  return lines.join('\n\n')
}

/**
 * 项目代码实体 → 架构解读提问预填
 * @param {Object} entity 选中实体 {name, kind, qualified_name, line_start, line_end}
 * @param {Object} ctx {sourcePath, callsOut: [name], callsIn: [name]}
 * @returns {string}
 */
export function buildEntityQuestion(entity, { sourcePath = '', callsOut = [], callsIn = [] } = {}) {
  const e = entity || {}
  const where = `${sourcePath || '当前项目'}${e.line_start != null ? ` 第 ${e.line_start}-${e.line_end} 行` : ''}`
  const lines = [
    `项目图谱里的 ${e.kind || '实体'}「${e.qualified_name || e.name || '未知'}」（${where}）我不太理解。`,
  ]
  if (callsOut.length) lines.push(`它调用了：${callsOut.slice(0, 8).join('、')}`)
  if (callsIn.length) lines.push(`被这些地方调用：${callsIn.slice(0, 8).join('、')}`)
  lines.push('请结合调用关系解释它在整个项目里承担什么职责、是怎么工作的；如果合适，给我一个小的阅读路径。')
  return lines.join('\n\n')
}
