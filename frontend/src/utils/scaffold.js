/**
 * 阶梯式实操指南分级拆分 (阶段13 T1, 借鉴源仓 KMatch)
 *
 * content_generator prompt (backend/app/agents/content_generator.py) 约定 5 级渐进提示:
 *   第1级 功能描述+预期输入输出 / 第2级 算法思路 / 第3级 伪代码框架
 *   第4级 关键代码片段(含空白) / 第5级 完整参考代码+注释
 *
 * prompt 只要求 "markdown 格式正文", 未强制 ## 标题, 故 LLM 可能输出
 * `## 第1级` / `**第1级**` / `第1级：` 等多种形态。本函数识别行首 (可选 # 或 * 前缀)
 * 的 "第N级" / "Level N" / "第N次" 作为分隔点, 拆成最多 5 级。
 *
 * 拆出 <2 级返回空数组 -> 调用方 (ScaffoldGuide.vue) 降级为整体 MarkdownViewer,
 * 保持原行为不回归。
 *
 * @param {string} content - practice_guide 资源的 markdown 原文
 * @returns {string[]} 各级内容 (含分隔行, 已 trim), 空数组表示无法分级
 */
const LEVEL_RE = /^(?:#{0,3}|\*{1,2})?\s*(?:第\s*([1-5])\s*级|Level\s*([1-5])|第\s*([1-5])\s*次)/

export function splitScaffoldLevels(content) {
  if (!content) return []

  const lines = content.split('\n')
  const buckets = []
  let current = null
  let buf = []

  for (const line of lines) {
    const m = line.match(LEVEL_RE)
    if (m) {
      if (current !== null) buckets.push({ idx: current, text: buf.join('\n') })
      current = Number(m[1] || m[2] || m[3]) - 1
      buf = [line]
    } else {
      buf.push(line)
    }
  }
  if (current !== null) buckets.push({ idx: current, text: buf.join('\n') })

  // 仅当拆出 >=2 级才返回分级内容; 否则返回空数组触发降级
  if (buckets.length < 2) return []
  // 按 idx 排序, 最多 5 级
  buckets.sort((a, b) => a.idx - b.idx)
  return buckets.slice(0, 5).map((b) => b.text.trim())
}

/** 5 级标题 (对齐 content_generator prompt) */
export const SCAFFOLD_LEVEL_TITLES = [
  '功能描述与预期输入输出',
  '算法思路提示',
  '伪代码框架',
  '关键代码片段（含空白）',
  '完整参考代码 + 注释',
]
