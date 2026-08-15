/**
 * utils/format 颜色映射单测
 *
 * 难度着色 (图谱节点 fill): 阈值对齐 difficultyTagType (≤2 绿 / ≤3 橙 / >3 红),
 * 图例弹窗与节点 fill 共用此函数, 阈值漂移会导致图例与实际颜色不符。
 */
import { describe, it, expect } from 'vitest'
import { difficultyColor, difficultyTagType, masteryColor } from '@/utils/format'

describe('difficultyColor', () => {
  it('阈值对齐 difficultyTagType 三档', () => {
    const tiers = [1, 2, 3, 4, 5]
    tiers.forEach((d) => {
      expect(difficultyColor(d)).toBeTruthy()
    })
    // 同档同色, 跨档变色
    expect(difficultyColor(1)).toBe(difficultyColor(2))
    expect(difficultyColor(2)).not.toBe(difficultyColor(3))
    expect(difficultyColor(3)).toBe(difficultyColor(3))
    expect(difficultyColor(3)).not.toBe(difficultyColor(4))
    expect(difficultyColor(4)).toBe(difficultyColor(5))
  })

  it('颜色档位与 tag type 一一对应', () => {
    const map = { success: difficultyColor(1), warning: difficultyColor(3), danger: difficultyColor(5) }
    expect(new Set(Object.values(map)).size).toBe(3)
    expect(difficultyTagType(2)).toBe('success')
    expect(difficultyTagType(3)).toBe('warning')
    expect(difficultyTagType(4)).toBe('danger')
  })
})

describe('masteryColor (掌握度仍用于 Dashboard 等, 图谱改难度着色)', () => {
  it('四段制不变', () => {
    expect(masteryColor(0.9)).toBe('#34b37e')
    expect(masteryColor(0.6)).toBe('#f0a040')
    expect(masteryColor(0.1)).toBe('#e05555')
    expect(masteryColor(0)).toBe('#c8c6c4')
  })
})
