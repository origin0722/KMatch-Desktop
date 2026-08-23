/**
 * AssessmentReport 组件测试 (阶段13 T3)
 *
 * 挂载组件, 断言测评明细渲染:
 *   正确/总数与正确率、按知识点汇总 tag、题目明细 (类型标签 + 三态判分 ✓/✗/?)、
 *   错题展示正确答案、未作答展示（未作答）、空 assessment 兜底
 *
 * 注: el-collapse-item 折叠内容用 v-show (display:none), 仍在 DOM 中, text() 可读。
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import AssessmentReport from '@/components/AssessmentReport.vue'

const mountOpts = (assessment) => ({
  props: { assessment },
  global: { plugins: [ElementPlus], stubs: ['el-icon'] },
})

const MOCK_ASSESSMENT = {
  total_count: 3,
  correct_count: 2,
  questions: [
    { question: 'Python 是编译型语言吗？', type: 'judge', difficulty: 1, node_id: 'PY-001', options: ['对', '错'], answer: '错', explanation: 'Python 是解释型语言，逐行解释执行，不是编译型。' },
    { question: '哪个是列表方法？', type: 'choice', difficulty: 2, node_id: 'PY-002', options: ['A. append', 'B. push', 'C. add', 'D. insert'], answer: 'A. append', explanation: 'append 是 list 的方法，push/add 不是 Python 列表 API。' },
    { question: '写一个求和函数', type: 'code', difficulty: 3, node_id: 'PY-003' },
  ],
  answers: ['错', 'B. push', null],  // q0 对, q1 错, q2 未作答
  per_node: {
    'PY-001': [{ question_index: 0, correct: true }],
    'PY-002': [{ question_index: 1, correct: false }],
    'PY-003': [{ question_index: 2, correct: null }],  // 未评分
  },
}

describe('AssessmentReport', () => {
  it('汇总渲染正确/总数 + 正确率', () => {
    const w = mount(AssessmentReport, mountOpts(MOCK_ASSESSMENT))
    const text = w.text()
    expect(text).toContain('2 / 3')
    // 2/3 = 66.67% -> round 67
    expect(text).toContain('67%')
  })

  it('按知识点汇总渲染 per-node tag (含 nodeCorrect ===true 严格匹配)', () => {
    const w = mount(AssessmentReport, mountOpts(MOCK_ASSESSMENT))
    const text = w.text()
    expect(text).toContain('PY-001 - 1/1 正确')
    expect(text).toContain('PY-002 - 0/1 正确')
    // correct===null 不计入正确 -> 0/1 (BUG-029: 不能 filter(Boolean))
    expect(text).toContain('PY-003 - 0/1 正确')
  })

  it('题目明细渲染类型标签 + 三态判分符号 (✓/✗/?)', () => {
    const w = mount(AssessmentReport, mountOpts(MOCK_ASSESSMENT))
    const text = w.text()
    expect(text).toContain('判断题')
    expect(text).toContain('选择题')
    expect(text).toContain('代码题')
    expect(text).toContain('✓')  // q0 正确
    expect(text).toContain('✗')  // q1 错误
    expect(text).toContain('?')  // q2 未评分
  })

  it('错题展示正确答案, 未作答展示（未作答）', () => {
    const w = mount(AssessmentReport, mountOpts(MOCK_ASSESSMENT))
    const text = w.text()
    // q1 错 -> 显示正确答案
    expect(text).toContain('正确答案')
    expect(text).toContain('A. append')
    // q2 未作答
    expect(text).toContain('（未作答）')
  })

  it('答案解析: 对错题都展示 explanation (不是孤零零的答案)', () => {
    const w = mount(AssessmentReport, mountOpts(MOCK_ASSESSMENT))
    const text = w.text()
    expect(text).toContain('解析：')
    // q0 正确题也显示解析
    expect(text).toContain('Python 是解释型语言')
    // q1 错题显示解析
    expect(text).toContain('append 是 list 的方法')
    // 无 explanation 的题不渲染空解析行
    expect(text).not.toContain('解析：undefined')
  })

  it('空 assessment 不崩溃, 渲染 0 / 0', () => {
    const w = mount(AssessmentReport, mountOpts({}))
    const text = w.text()
    expect(text).toContain('0 / 0')
    expect(text).toContain('0%')
  })

  it('无 per_node 时不渲染按知识点汇总区', () => {
    const w = mount(AssessmentReport, mountOpts({ questions: [], total_count: 0, correct_count: 0 }))
    expect(w.text()).not.toContain('按知识点汇总')
  })
})
