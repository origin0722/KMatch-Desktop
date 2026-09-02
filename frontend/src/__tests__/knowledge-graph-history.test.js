import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const mocks = vi.hoisted(() => {
  const { reactive } = require('vue')
  const history = reactive({
    items: [], learningViewing: null, learningSnapshot: null,
    viewLearning: vi.fn(), backToLiveLearning: vi.fn(),
  })
  return {
    assessment: reactive({ knowledgeGraph: null, profile: null }),
    history,
    remove: vi.fn((id) => {
      history.items = history.items.filter((item) => item.id !== id)
      if (history.learningViewing?.id === id) {
        history.learningViewing = null
        history.learningSnapshot = null
      }
    }),
    confirm: vi.fn(),
  }
})

vi.mock('@antv/g6', () => ({ Graph: class { destroy() {} on() {} render() {} resize() {} } }))
vi.mock('@/stores/assessment', () => ({ useAssessmentStore: () => mocks.assessment }))
vi.mock('@/stores/graphHistory', () => ({ useGraphHistoryStore: () => ({ ...mocks.history, remove: mocks.remove }) }))
vi.mock('@/stores/sidebar', () => ({ useSidebarStore: () => ({ persona: 'intermediate', setView: vi.fn() }) }))
vi.mock('@/stores/chat', () => ({ useChatStore: () => ({ setDraft: vi.fn() }) }))
vi.mock('@/utils/format', () => ({ masteryColor: vi.fn(() => '#000'), difficultyColor: vi.fn(() => '#000') }))
vi.mock('@/utils/nodeSize', () => ({ cjkAwareWidth: vi.fn(() => 160) }))
vi.mock('@/utils/excalidrawExport', () => ({ graphToExcalidraw: vi.fn(), downloadExcalidraw: vi.fn(), collectG6Positions: vi.fn(() => []) }))
vi.mock('@/api/graph', () => ({ semanticSearch: vi.fn(), getByCategory: vi.fn(), getByDifficulty: vi.fn(), getNode: vi.fn(), getPrerequisites: vi.fn() }))
vi.mock('@/utils/askAi', () => ({ buildNodeQuestion: vi.fn(() => ''), graphGuidePrompt: vi.fn(() => '') }))
vi.mock('element-plus', () => ({ ElMessage: { error: vi.fn(), warning: vi.fn() }, ElMessageBox: { confirm: mocks.confirm } }))

const KnowledgeGraph = (await import('@/views/KnowledgeGraph.vue')).default

const ElButton = {
  inheritAttrs: false,
  template: '<button :data-test="$attrs[\'data-test\']" :disabled="$attrs.disabled" @click="$emit(\'click\', $event)"><slot /></button>',
}
const stubs = {
  ElAlert: true,
  ElButton,
  ElCard: { template: '<div><slot /></div>' },
  ElDialog: { template: '<div><slot /><slot name="footer" /></div>' },
  ElDivider: true,
  ElEmpty: { template: '<div><slot /></div>' },
  ElIcon: { template: '<span><slot /></span>' },
  ElInput: true,
  ElOption: true,
  ElPopover: { template: '<div><slot name="reference" /><slot /></div>' },
  ElProgress: true,
  ElSelect: true,
  ElTag: { template: '<span><slot /></span>' },
  PathFinderModal: true,
}

describe('KnowledgeGraph 历史快照移除', () => {
  beforeEach(() => {
    mocks.assessment.knowledgeGraph = null
    mocks.history.items = [{
      id: 'learning:s1', type: 'learning', sessionId: 's1', name: 'Python 入门',
      snapshot: { learning_path: [{ node_id: 'PY-001' }] }, ts: Date.now(),
    }]
    mocks.history.learningViewing = null
    mocks.history.learningSnapshot = null
    mocks.confirm.mockResolvedValue()
    vi.clearAllMocks()
  })

  it('移除学习快照只更新本地历史并退出该快照的回看态', async () => {
    const wrapper = mount(KnowledgeGraph, { global: { stubs } })
    const remove = wrapper.find('[data-test="history-delete-learning:s1"]')

    expect(remove.exists()).toBe(true)
    await remove.trigger('click')
    await flushPromises()

    expect(mocks.confirm).toHaveBeenCalledWith(
      expect.stringContaining('不会删除当前图谱、项目源码或已累计的学习画像'),
      '移除历史快照',
    )
    expect(mocks.remove).toHaveBeenCalledWith('learning:s1')
    expect(mocks.history.items).toEqual([])
    expect(mocks.history.learningViewing).toBe(null)
  })
})
