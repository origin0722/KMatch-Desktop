/**
 * KMatch 前端公共工具函数
 */

/**
 * 从 markdown 内容中提取标题（首行 # 或 ##）
 * @param {string} content
 * @returns {string}
 */
export function extractTitle(content) {
  if (!content) return ''
  const match = content.match(/^#{1,2}\s+(.+?)(?:\n|$)/m)
  return match ? match[1].trim() : ''
}

/**
 * 截断文本
 * @param {string} text
 * @param {number} maxLen
 * @returns {string}
 */
export function truncate(text, maxLen) {
  if (!text) return ''
  return text.length > maxLen ? text.slice(0, maxLen) + '…' : text
}

/**
 * 掌握程度 → 颜色（四段制，对齐 prompt ≥0.8 known）
 * hex 值镜像 styles/theme.css 的 --km-* token (canvas/G6 不能读 CSS 变量)
 * @param {number} mastery 0..1
 * @returns {string} hex 颜色
 */
export function masteryColor(mastery) {
  if (mastery >= 0.8) return '#34b37e'  // 已掌握 — km-success
  if (mastery >= 0.5) return '#f0a040'  // 学习中 — km-warning
  if (mastery > 0) return '#e05555'     // 未掌握 — km-danger
  return '#c8c6c4'                       // 未学习 — km-gray-400
}

/**
 * 难度 → Element Plus tag type
 * @param {number} d 1..5
 * @returns {'success'|'warning'|'danger'}
 */
export function difficultyTagType(d) {
  if (d <= 2) return 'success'
  if (d <= 3) return 'warning'
  return 'danger'
}

/**
 * 难度 → 图谱节点填充色 (阈值对齐 difficultyTagType)
 * hex 值镜像 styles/theme.css 的 --km-* token (canvas/G6 不能读 CSS 变量)
 * @param {number} d 1..5
 * @returns {string} hex 颜色
 */
export function difficultyColor(d) {
  if (d <= 2) return '#34b37e'  // 入门 — km-success
  if (d <= 3) return '#f0a040'  // 进阶 — km-warning
  return '#e05555'              // 高级 — km-danger
}

/**
 * content_type → 中文名
 * @param {string} type
 * @returns {string}
 */
export function contentTypeLabel(type) {
  return { lecture: '讲义', practice_guide: '实操指南', test: '测试题' }[type] || type
}
