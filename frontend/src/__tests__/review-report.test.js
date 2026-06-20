/**
 * ReviewReport 组件单元测试
 *
 * 覆盖: dimensionList 阈值判定、threshold 字段读取
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ReviewReport from '@/components/ReviewReport.vue'

// Mock Element Plus 图标
vi.mock('@element-plus/icons-vue', () => ({
  CircleCheckFilled: { template: '<span />' },
}))

describe('ReviewReport', () => {
  const makeProps = (overrides = {}) => ({
    reviewResults: {
      passed: false,
      overall_score: 0.5,
      dimensions: {},
      ...overrides,
    },
  })

  describe('threshold 字段', () => {
    it('应使用后端传入的 threshold', () => {
      const wrapper = mount(ReviewReport, {
        props: makeProps({ threshold: 0.8 }),
      })
      expect(wrapper.vm.threshold).toBe('80')
    })

    it('threshold 缺失时回落 85%', () => {
      const wrapper = mount(ReviewReport, {
        props: makeProps({ threshold: undefined }),
      })
      expect(wrapper.vm.threshold).toBe('85')
    })

    it('threshold 为 null 时回落 85%', () => {
      const wrapper = mount(ReviewReport, {
        props: makeProps({ threshold: null }),
      })
      expect(wrapper.vm.threshold).toBe('85')
    })
  })

  describe('scoreColor', () => {
    it('>= threshold 为绿色', () => {
      const wrapper = mount(ReviewReport, {
        props: makeProps({ overall_score: 0.9, threshold: 0.85 }),
      })
      expect(wrapper.vm.scoreColor).toBe('#52c41a')
    })

    it('>= 0.6 且 < threshold 为橙色', () => {
      const wrapper = mount(ReviewReport, {
        props: makeProps({ overall_score: 0.7, threshold: 0.85 }),
      })
      expect(wrapper.vm.scoreColor).toBe('#faad14')
    })

    it('< 0.6 为红色', () => {
      const wrapper = mount(ReviewReport, {
        props: makeProps({ overall_score: 0.3, threshold: 0.85 }),
      })
      expect(wrapper.vm.scoreColor).toBe('#f56c6c')
    })
  })

  describe('dimensionList', () => {
    it('应生成四个维度并按 order 排序', () => {
      const wrapper = mount(ReviewReport, {
        props: makeProps({
          passed: true,
          overall_score: 0.85,
          dimensions: {
            factual_accuracy: { score: 0.9, issues: [] },
            hallucination: { score: 0.85, issues: [] },
            logic_consistency: { score: 0.8, issues: [] },
            teaching_appropriateness: { score: 0.75, issues: [] },
          },
        }),
      })

      const list = wrapper.vm.dimensionList
      expect(list).toHaveLength(4)
      // 顺序: factual_accuracy(1) → hallucination(2) → logic_consistency(3) → teaching_appropriateness(4)
      expect(list[0].key).toBe('factual_accuracy')
      expect(list[1].key).toBe('hallucination')
      expect(list[2].key).toBe('logic_consistency')
      expect(list[3].key).toBe('teaching_appropriateness')
    })

    it('缺失维度应填充默认 score=0', () => {
      const wrapper = mount(ReviewReport, {
        props: makeProps({
          dimensions: { factual_accuracy: { score: 0.9, issues: [] } },
        }),
      })

      const list = wrapper.vm.dimensionList
      // hallucination 缺失 → score=0
      const halluc = list.find((d) => d.key === 'hallucination')
      expect(halluc.score).toBe(0)
    })

    it('含 issues 的维度应保留 issues', () => {
      const issues = [{ severity: 'high', problem: '概念错误' }]
      const wrapper = mount(ReviewReport, {
        props: makeProps({
          dimensions: {
            factual_accuracy: { score: 0.5, issues },
            hallucination: { score: 1.0, issues: [] },
            logic_consistency: { score: 1.0, issues: [] },
            teaching_appropriateness: { score: 1.0, issues: [] },
          },
        }),
      })

      const dim = wrapper.vm.dimensionList.find((d) => d.key === 'factual_accuracy')
      expect(dim.issues).toHaveLength(1)
      expect(dim.issues[0].problem).toBe('概念错误')
      expect(dim.scoreClass).toBe('score-bad')
    })

    it('全高分维度应为 score-good', () => {
      const wrapper = mount(ReviewReport, {
        props: makeProps({
          overall_score: 0.95,
          dimensions: {
            factual_accuracy: { score: 0.95, issues: [] },
            hallucination: { score: 0.9, issues: [] },
            logic_consistency: { score: 0.9, issues: [] },
            teaching_appropriateness: { score: 0.9, issues: [] },
          },
        }),
      })

      const list = wrapper.vm.dimensionList
      expect(list.every((d) => d.scoreClass === 'score-good')).toBe(true)
    })
  })

  describe('passed / retryHint', () => {
    it('passed=false 且 retryHint 非空时显示打回提示', () => {
      const wrapper = mount(ReviewReport, {
        props: makeProps({
          passed: false,
          retry_hint: '请修正知识点 PY-001 的描述',
        }),
      })
      expect(wrapper.vm.passed).toBe(false)
      expect(wrapper.vm.retryHint).toBe('请修正知识点 PY-001 的描述')
    })
  })
})
