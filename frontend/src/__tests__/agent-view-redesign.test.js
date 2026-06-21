import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import AgentView from '@/views/AgentView.vue'

vi.mock('@/stores/assessment', () => ({
  useAssessmentStore: () => ({
    orchestrationLog: [
      '[10:00:01] 主控调度 Agent: 读取学习画像',
      '[10:00:04] 学情检测 Agent: 发现文件 IO 薄弱',
      '[10:00:08] 图谱管控 Agent: 推荐异常处理前置节点',
    ],
    assessment: { total_count: 4 },
    accuracy: 0.75,
    reviewResults: null,
    knowledgeGraph: { learning_path: [{ node_id: 'py_file_io' }], estimated_total_hours: 2 },
    generatedContent: { resources: [{ title: '文件 IO 练习' }] },
  }),
}))

vi.mock('@/stores/sidebar', () => ({
  useSidebarStore: () => ({ setView: vi.fn() }),
}))

vi.mock('@/composables/useAgentStatus', () => ({
  useAgentStatus: () => ({
    pipelineRunning: { value: false },
    agentNodes: { value: [
      { key: 'orchestrator', label: '主控调度', status: 'done', role: '规划协作', retryCount: 0 },
      { key: 'diagnostics', label: '学情检测', status: 'done', role: '识别薄弱点', retryCount: 0 },
      { key: 'graph_controller', label: '图谱管控', status: 'done', role: '生成路径', retryCount: 0 },
    ] },
  }),
}))

describe('AgentView redesign', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('renders an agent cockpit instead of a pipeline-only page', () => {
    const wrapper = mount(AgentView, { global: { stubs: ['el-button', 'el-empty', 'el-tag'] } })
    expect(wrapper.find('.agent-cockpit').exists()).toBe(true)
    expect(wrapper.text()).toContain('Agent 协同 cockpit')
    expect(wrapper.text()).toContain('主控调度')
    expect(wrapper.text()).toContain('协同对话流')
  })

  it('renders a local orchestration question input affordance', () => {
    const wrapper = mount(AgentView, { global: { stubs: ['el-button', 'el-empty', 'el-tag'] } })
    expect(wrapper.find('[data-test="agent-question-input"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="agent-question-button"]').exists()).toBe(true)
  })
})
