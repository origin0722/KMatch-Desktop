/**
 * splitScaffoldLevels 单元测试 (阶段13 T1)
 *
 * content_generator prompt 约定 5 级渐进提示, 本函数负责拆分。
 * 覆盖: 标准 5 级 / 多种分隔格式 (## 第N级, **第N级**, 第N级：, Level N, 第N次) /
 *       拆出 <2 级降级 (返回 []) / 按 idx 排序 / 最多 5 级 / 空输入 / 行内提及不误拆
 */
import { describe, it, expect } from 'vitest'
import { splitScaffoldLevels } from '@/utils/scaffold'

describe('splitScaffoldLevels', () => {
  const FIVE_LEVEL = [
    '## 第1级 功能描述',
    '写一个函数求阶乘',
    '## 第2级 算法思路',
    '递归或循环',
    '### 第3级 伪代码框架',
    'def fact(n): ...',
    '## 第4级 关键代码片段',
    'return n * fact(n-1)',
    '## 第5级 完整参考代码',
    'def fact(n): return 1 if n<=1 else n*fact(n-1)',
  ].join('\n')

  it('标准 5 级 markdown 拆出 5 段', () => {
    const levels = splitScaffoldLevels(FIVE_LEVEL)
    expect(levels).toHaveLength(5)
    expect(levels[0]).toContain('求阶乘')
    expect(levels[4]).toContain('完整参考代码')
  })

  it('每段含分隔标题本身 (不丢行)', () => {
    const levels = splitScaffoldLevels(FIVE_LEVEL)
    expect(levels[0]).toMatch(/第1级/)
    expect(levels[2]).toMatch(/第3级/)
  })

  it('**第N级** 加粗格式也能识别', () => {
    const content = '**第1级 描述**\na\n**第2级 思路**\nb'
    const levels = splitScaffoldLevels(content)
    expect(levels).toHaveLength(2)
    expect(levels[0]).toMatch(/第1级/)
  })

  it('无 # 前缀的 "第N级：..." 也能识别 (prompt 未强制标题)', () => {
    const content = '第1级：功能描述\n输入 n 输出 n!\n第2级：算法思路\n用递归'
    const levels = splitScaffoldLevels(content)
    expect(levels).toHaveLength(2)
    expect(levels[0]).toContain('功能描述')
    expect(levels[1]).toContain('算法思路')
  })

  it('Level N 格式也能识别', () => {
    const content = '## Level 1 desc\na\n## Level 2 思路\nb'
    const levels = splitScaffoldLevels(content)
    expect(levels).toHaveLength(2)
    expect(levels[0]).toMatch(/Level 1/)
  })

  it('第N次 格式也能识别', () => {
    const content = '## 第1次尝试\na\n## 第2次尝试\nb'
    expect(splitScaffoldLevels(content)).toHaveLength(2)
  })

  it('拆出 <2 级返回空数组 (触发降级)', () => {
    expect(splitScaffoldLevels('## 第1级 只有一级\n内容')).toEqual([])
  })

  it('无任何级别标记返回空数组', () => {
    expect(splitScaffoldLevels('普通 markdown\n无分级标记')).toEqual([])
  })

  it('空 / null / undefined 输入返回空数组', () => {
    expect(splitScaffoldLevels('')).toEqual([])
    expect(splitScaffoldLevels(null)).toEqual([])
    expect(splitScaffoldLevels(undefined)).toEqual([])
  })

  it('乱序级别按 idx 排序', () => {
    const content = '## 第3级 伪代码\nc\n## 第1级 描述\na\n## 第2级 思路\nb'
    const levels = splitScaffoldLevels(content)
    expect(levels).toHaveLength(3)
    expect(levels[0]).toMatch(/第1级/)
    expect(levels[1]).toMatch(/第2级/)
    expect(levels[2]).toMatch(/第3级/)
  })

  it('超过 5 级只取前 5', () => {
    const parts = []
    for (let i = 1; i <= 7; i++) parts.push(`## 第${i}级 标题${i}`, `内容${i}`)
    expect(splitScaffoldLevels(parts.join('\n'))).toHaveLength(5)
  })

  it('容忍级别数字间空格 (第 1 级)', () => {
    const content = '## 第 1 级 描述\na\n## 第 2 级 思路\nb'
    expect(splitScaffoldLevels(content)).toHaveLength(2)
  })

  it('行内提及 "第N级" 不误拆 (仅行首匹配)', () => {
    const content = '本指南分5级递进。\n在第1级中我们讨论基础, 第2级讨论进阶。'
    // 两行都不以 "第N级" 开头 -> 无法分级 -> 降级
    expect(splitScaffoldLevels(content)).toEqual([])
  })
})
