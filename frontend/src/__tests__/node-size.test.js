/**
 * W2 CJK 感知节点尺寸估算单测 (utils/nodeSize)
 *
 * 借鉴 excalidraw-skill 的 CJK-aware sizing 规范: 中文全角 ≈ 1×字号, 拉丁 ≈ 0.55×字号。
 * 供 KnowledgeGraph / ProjectGraphView / excalidrawExport 共用, 是布局防重叠的基石。
 */
import { describe, it, expect } from 'vitest'
import { textDisplayWidth, cjkAwareWidth } from '@/utils/nodeSize'

describe('textDisplayWidth (单行显示宽度)', () => {
  it('中文全角字符按 1×字号计', () => {
    expect(textDisplayWidth('循环', 13)).toBeCloseTo(26)
  })

  it('拉丁字符按 0.55×字号计', () => {
    expect(textDisplayWidth('for', 13)).toBeCloseTo(3 * 13 * 0.55)
  })

  it('中英混排累计', () => {
    // 2 中文 + 3 拉丁 @13px
    expect(textDisplayWidth('循环for', 13)).toBeCloseTo(2 * 13 + 3 * 13 * 0.55)
  })

  it('空文本返回 0', () => {
    expect(textDisplayWidth('')).toBe(0)
    expect(textDisplayWidth(null)).toBe(0)
  })
})

describe('cjkAwareWidth (CJK 感知卡片宽度)', () => {
  const OPTS = { fontSize: 13, padding: 28, min: 120, max: 260 }

  it('短标签不小于 min', () => {
    expect(cjkAwareWidth('if', OPTS)).toBe(120)
  })

  it('长标签不超过 max', () => {
    const long = '这是一个非常非常非常非常非常长的中文知识点名称标签'
    expect(cjkAwareWidth(long, OPTS)).toBe(260)
  })

  it('中等中文标签宽度 = 文本宽 + padding', () => {
    // '列表推导式' 5 字 @13 = 65 + 28 = 93 → clamp 到 min 120
    expect(cjkAwareWidth('列表推导式', OPTS)).toBe(120)
    // '异步上下文管理器协议深入' 12 字 @13 = 156 + 28 = 184
    expect(cjkAwareWidth('异步上下文管理器协议深入', OPTS)).toBe(184)
  })

  it('多行标签取最宽行 (名称行比分类行宽)', () => {
    const label = '装饰器与闭包原理\n基础语法 · ⭐⭐'
    // 最宽行 '装饰器与闭包原理' 8 字 @13 = 104 + 28 = 132
    expect(cjkAwareWidth(label, OPTS)).toBe(132)
  })

  it('中文名比等长拉丁名需要更宽的卡片 (CJK 感知的本职)', () => {
    const cjk = cjkAwareWidth('数据库连接池配置管理', OPTS)
    const latin = cjkAwareWidth('dbpoolconfigmgmt', OPTS)
    expect(cjk).toBeGreaterThan(latin)
  })

  it('自定义区间生效 (ProjectGraphView: fontSize 12.5 / min 120 / max 240)', () => {
    const opts = { fontSize: 12.5, padding: 26, min: 120, max: 240 }
    expect(cjkAwareWidth('main', opts)).toBe(120)
    expect(cjkAwareWidth('app.services.user_service.handle_request', opts)).toBe(240)
  })
})
