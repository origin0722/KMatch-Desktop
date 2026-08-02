/**
 * ReviewReport 组件测试 (阶段13 T2)
 *
 * 挂载组件, 断言四维度审核报告渲染:
 *   通过/打回结论、综合得分、四维度按权重顺序、issue 与无问题、打回原因 alert、缺省值兜底
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import ReviewReport from '@/components/ReviewReport.vue'

const mountOpts = (reviewResults) => ({
  props: { reviewResults },
  global: { plugins: [ElementPlus], stubs: ['el-icon'] },
})

const MOCK_REVIEW = {
  passed: true,
  overall_score: 0.9,
  threshold: 0.85,
  dimensions: {
    factual_accuracy: { score: 0.95, issues: [] },
    hallucination: { score: 0.9, issues: [] },
    logic_consistency: { score: 0.85, issues: [{ severity: 'medium', problem: '某处逻辑跳跃' }] },
    teaching_appropriateness: { score: 0.8, issues: [] },
  },
}

describe('ReviewReport', () => {
  it('通过时渲染审核通过 + 综合得分 + 四维度标签 + 4 张卡片', () => {
    const w = mount(ReviewReport, mountOpts(MOCK_REVIEW))
    const text = w.text()
    expect(text).toContain('审核通过')
    expect(text).toContain('综合得分')
    expect(text).toContain('事实准确性')
    expect(text).toContain('幻觉检测')
    expect(text).toContain('逻辑一致性')
    expect(text).toContain('教学适当性')
    expect(w.findAll('.dim-card')).toHaveLength(4)
  })

  it('四维度按权重顺序排列 (事实->幻觉->逻辑->教学)', () => {
    const w = mount(ReviewReport, mountOpts(MOCK_REVIEW))
    const text = w.text()
    const i1 = text.indexOf('事实准确性')
    const i2 = text.indexOf('幻觉检测')
    const i3 = text.indexOf('逻辑一致性')
    const i4 = text.indexOf('教学适当性')
    expect(i1).toBeLessThan(i2)
    expect(i2).toBeLessThan(i3)
    expect(i3).toBeLessThan(i4)
  })

  it('有问题维度渲染 issue 文本, 无问题维度渲染无问题', () => {
    const w = mount(ReviewReport, mountOpts(MOCK_REVIEW))
    const text = w.text()
    expect(text).toContain('某处逻辑跳跃')
    expect(text).toContain('无问题')
  })

  it('打回时渲染审核不通过 + 打回原因 alert + retry_hint', () => {
    const failed = { ...MOCK_REVIEW, passed: false, retry_hint: '事实错误需修正' }
    const w = mount(ReviewReport, mountOpts(failed))
    const text = w.text()
    expect(text).toContain('审核不通过')
    expect(text).toContain('打回原因')
    expect(text).toContain('事实错误需修正')
  })

  it('缺省 threshold 显示 85%, 缺省 dimensions 仍渲染 4 维度 (0 分)', () => {
    const minimal = { passed: false, overall_score: 0.4 }
    const w = mount(ReviewReport, mountOpts(minimal))
    expect(w.text()).toContain('（阈值 85%）')
    expect(w.findAll('.dim-card')).toHaveLength(4)
  })

  it('severity=high 的 issue 渲染高标签', () => {
    const review = {
      passed: false,
      overall_score: 0.3,
      dimensions: {
        factual_accuracy: { score: 0.2, issues: [{ severity: 'high', problem: '严重事实错误' }] },
        hallucination: { score: 0.5, issues: [] },
        logic_consistency: { score: 0.5, issues: [] },
        teaching_appropriateness: { score: 0.5, issues: [] },
      },
    }
    const w = mount(ReviewReport, mountOpts(review))
    expect(w.text()).toContain('严重事实错误')
    expect(w.text()).toContain('高')
  })
})
