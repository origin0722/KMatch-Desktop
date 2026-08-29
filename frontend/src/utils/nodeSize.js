/**
 * CJK 感知节点尺寸估算 (借鉴 excalidraw-skill 的 CJK-aware sizing 设计规范)
 *
 * 中文全角字符宽 ≈ 1.0 × 字号, 拉丁/数字/半角 ≈ 0.55 × 字号。
 * 固定卡片宽的毛病: 长中文名被截断、短名留大片空白 — 宽度按标签最宽行动态算。
 * 纯函数, 供 KnowledgeGraph / ProjectGraphView / excalidrawExport 共用。
 */

/** 全角宽度区间: 中日韩统一表意文字 / 兼容表意 / 全角形式 / CJK 标点 / ⭐(U+2B50, 标签难度星) */
const CJK_RE = /[\u2E80-\u9FFF\uF900-\uFAFF\uFF00-\uFFEF\u3000-\u303F\u2B50]/

/** 单行文本显示宽度 (px @fontSize) */
export function textDisplayWidth(text, fontSize = 13) {
  let units = 0
  for (const ch of String(text ?? '')) units += CJK_RE.test(ch) ? 1 : 0.55
  return units * fontSize
}

/**
 * 多行标签的 CJK 感知卡片宽度: 取最宽行估算 + padding, clamp 到 [min, max]。
 * 多行文本 (如 "名称\n分类 · ⭐⭐") 逐行量宽取最大, 保证每行都放得下。
 */
export function cjkAwareWidth(text, { fontSize = 13, padding = 28, min = 120, max = 260 } = {}) {
  const lines = String(text ?? '').split('\n')
  const widest = lines.reduce((w, l) => Math.max(w, textDisplayWidth(l, fontSize)), 0)
  return Math.round(Math.min(max, Math.max(min, widest + padding)))
}
