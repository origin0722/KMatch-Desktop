import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import Assessment from '@/views/Assessment.vue'

vi.mock('@/stores/assessment', () => ({
  useAssessmentStore: () => ({
    hasResults: false,
    loading: false,
    phase: 'input',
    pendingQuestions: [],
    userAnswers: [],
    error: null,
    currentStep: null,
    profile: null,
    assessment: null,
    feedbackStrategy: null,
    feedbackContent: null,
    startAssessment: vi.fn(),
    submitAssessmentAnswers: vi.fn(),
    backToInput: vi.fn(),
    reset: vi.fn(),
    fetchFeedback: vi.fn(),
  }),
}))

vi.mock('@/components/ProfileRadar.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/AssessmentReport.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/components/MarkdownViewer.vue', () => ({ default: { props: ['content'], template: '<div>{{ content }}</div>' } }))

describe('Assessment redesign', () => {
  it('renders diagnostic console framing', () => {
    const wrapper = mount(Assessment, {
      global: {
        plugins: [createPinia()],
        directives: { loading: {} },
        stubs: ['el-card', 'el-form', 'el-form-item', 'el-input', 'el-button', 'el-select', 'el-option', 'el-tag', 'el-alert', 'el-radio-group', 'el-radio', 'el-descriptions', 'el-descriptions-item', 'el-divider', 'el-row', 'el-col', 'el-empty', 'el-icon', 'el-tooltip', 'el-timeline', 'el-timeline-item'],
      },
    })

    expect(wrapper.find('.diagnostic-console').exists()).toBe(true)
    expect(wrapper.text()).toContain('学情诊断控制台')
    expect(wrapper.text()).toContain('诊断阶段')
    expect(wrapper.text()).toContain('目标方向')
  })
})
