/**
 * AssessmentReport 组件计算属性单元测试
 *
 * 覆盖: perNodeEntries, questionList（新旧 per_node 结构）
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import AssessmentReport from '@/components/AssessmentReport.vue'

// Mock Element Plus 图标
vi.mock('@element-plus/icons-vue', () => ({}))

describe('AssessmentReport', () => {
  const makeProps = (overrides = {}) => ({
    assessment: {
      questions: [],
      answers: [],
      per_node: {},
      correct_count: 0,
      total_count: 0,
      ...overrides,
    },
  })

  describe('per_node 旧格式兼容', () => {
    it('perNodeEntries 应正确拆分旧格式 {node_id: [true, false]}', () => {
      const wrapper = mount(AssessmentReport, {
        props: makeProps({
          per_node: {
            'PY-001': [true, false],
            'PY-002': [true],
          },
        }),
      })

      // per_node 旧格式 ([true, false]) — questionGrades 无法从布尔值中读 question_index
      // 所以 questionList 中 grade.correct 均为 null
      const vm = wrapper.vm
      expect(vm.perNodeEntries).toHaveLength(2)
      expect(vm.perNodeEntries[0][0]).toBe('PY-001')
    })
  })

  describe('per_node 新格式', () => {
    it('questionList 应通过 question_index 正确匹配判分', () => {
      const wrapper = mount(AssessmentReport, {
        props: makeProps({
          questions: [
            { question: 'Q1?', node_id: 'PY-001', type: 'choice', difficulty: 1, options: ['A', 'B'] },
            { question: 'Q2?', node_id: 'PY-001', type: 'judge', difficulty: 2, options: ['对', '错'] },
            { question: 'Q3?', node_id: 'PY-002', type: 'code', difficulty: 3, options: [] },
          ],
          answers: ['A', '错', 'print(1)'],
          per_node: {
            'PY-001': [
              { question_index: 0, correct: true },
              { question_index: 1, correct: false },
            ],
            'PY-002': [
              { question_index: 2, correct: true },
            ],
          },
          correct_count: 2,
          total_count: 3,
        }),
      })

      const vm = wrapper.vm
      const list = vm.questionList

      expect(list).toHaveLength(3)

      // Q1: index=0 → PY-001, correct=true
      expect(list[0].grade.correct).toBe(true)
      expect(list[0].index).toBe(0)

      // Q2: index=1 → PY-001, correct=false
      expect(list[1].grade.correct).toBe(false)

      // Q3: index=2 → PY-002, correct=true
      expect(list[2].grade.correct).toBe(true)
    })

    it('questionList 应在无匹配时返回 correct=null', () => {
      const wrapper = mount(AssessmentReport, {
        props: makeProps({
          questions: [
            { question: 'Q?', node_id: 'PY-003', type: 'choice', difficulty: 1, options: [] },
          ],
          answers: ['X'],
          per_node: { 'PY-001': [{ question_index: 99, correct: true }] },
        }),
      })

      const vm = wrapper.vm
      // question_index 99 不匹配 idx=0 的题目 → correct=null
      expect(vm.questionList[0].grade.correct).toBeNull()
    })
  })

  describe('计算属性', () => {
    it('totalCount / correctCount / accuracy', () => {
      const wrapper = mount(AssessmentReport, {
        props: makeProps({ correct_count: 3, total_count: 5 }),
      })
      const vm = wrapper.vm
      expect(vm.totalCount).toBe(5)
      expect(vm.correctCount).toBe(3)
      expect(vm.accuracy).toBe(0.6)
    })

    it('accuracy 在 totalCount=0 时返回 0', () => {
      const wrapper = mount(AssessmentReport, {
        props: makeProps({ correct_count: 0, total_count: 0 }),
      })
      expect(wrapper.vm.accuracy).toBe(0)
    })
  })

  describe('nodeCorrect — per_node 新结构语义', () => {
    // 回归测试：W1-2 审查报告 #1 修复
    // 旧实现 filter(Boolean) 在新结构下永远返回总长度（每个 grade 对象都 truthy），
    // 必须按 g.correct === true 过滤。
    it('应只统计 correct=true 的 grade，不应把 correct=false 的对象计入', () => {
      const wrapper = mount(AssessmentReport, {
        props: makeProps({
          per_node: {
            'PY-001': [
              { question_index: 0, correct: true },
              { question_index: 1, correct: false },
              { question_index: 2, correct: false },
            ],
          },
        }),
      })
      // 期望: 1/3，旧实现会错误返回 3/3
      expect(wrapper.vm.nodeCorrect(wrapper.vm.perNodeEntries[0][1])).toBe(1)
    })

    it('全错时 nodeCorrect 应为 0、nodeTagType 为 danger', () => {
      const wrapper = mount(AssessmentReport, {
        props: makeProps({
          per_node: {
            'PY-002': [
              { question_index: 0, correct: false },
              { question_index: 1, correct: false },
            ],
          },
        }),
      })
      const results = wrapper.vm.perNodeEntries[0][1]
      expect(wrapper.vm.nodeCorrect(results)).toBe(0)
      expect(wrapper.vm.nodeTagType(results)).toBe('danger')
    })

    it('全对时 nodeTagType 为 success、部分对为 warning', () => {
      const wrapper = mount(AssessmentReport, {
        props: makeProps({
          per_node: {
            'PY-A': [{ question_index: 0, correct: true }, { question_index: 1, correct: true }],
            'PY-B': [{ question_index: 2, correct: true }, { question_index: 3, correct: false }],
          },
        }),
      })
      const a = wrapper.vm.perNodeEntries[0][1]
      const b = wrapper.vm.perNodeEntries[1][1]
      expect(wrapper.vm.nodeTagType(a)).toBe('success')
      expect(wrapper.vm.nodeTagType(b)).toBe('warning')
    })

    it('空数组应返回 info / 0', () => {
      const wrapper = mount(AssessmentReport, {
        props: makeProps({ per_node: {} }),
      })
      expect(wrapper.vm.nodeCorrect([])).toBe(0)
      expect(wrapper.vm.nodeTagType([])).toBe('info')
      expect(wrapper.vm.nodeCorrect(undefined)).toBe(0)
    })
  })
})
