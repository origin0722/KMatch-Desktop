import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { reactive } from 'vue'

const mocks = vi.hoisted(() => {
  const { reactive } = require('vue')
  return {
    projectGraph: reactive({
      graph: {
        projectId: 'project-1',
        entities: [{ id: 'main', name: 'main', kind: 'function', line_start: 1, line_end: 1 }],
        relations: [], stats: {}, sourcePath: '', written: true,
      },
      stale: false, parsing: false, parseError: null, analysis: null, analyzing: false,
      historyViewing: null,
      restorePersisted: vi.fn(), parseCurrentProject: vi.fn(), requestReveal: vi.fn(),
      openFromHistory: vi.fn(), backToCurrentProject: vi.fn(), analyze: vi.fn(),
    }),
    workspace: reactive({ activeFile: 'src/a.py', hasProject: true }),
    assessment: reactive({ profile: { target_direction: 'Python Web 后端' } }),
    graphHistory: reactive({
      items: [], learningViewing: null, learningSnapshot: null,
      viewLearning: vi.fn(), backToLiveLearning: vi.fn(),
    }),
    runProjectPipeline: vi.fn(),
    readFile: vi.fn(),
    prompt: vi.fn(),
    confirm: vi.fn(),
    warning: vi.fn(),
  }
})

mocks.graphHistory.remove = vi.fn((id) => {
  mocks.graphHistory.items = mocks.graphHistory.items.filter((item) => item.id !== id)
})

vi.mock('@antv/g6', () => ({
  Graph: class {
    on() {}
    render() {}
    destroy() {}
    resize() {}
    fitView() {}
    zoomTo() {}
    getZoom() { return 1 }
  },
}))
vi.mock('@/stores/projectGraph', () => ({ useProjectGraphStore: () => mocks.projectGraph }))
vi.mock('@/stores/workspace', () => ({ useWorkspaceStore: () => mocks.workspace }))
vi.mock('@/stores/assessment', () => ({ useAssessmentStore: () => mocks.assessment }))
vi.mock('@/stores/sidebar', () => ({ useSidebarStore: () => ({ setView: vi.fn() }) }))
vi.mock('@/stores/chat', () => ({ useChatStore: () => ({ setDraft: vi.fn() }) }))
vi.mock('@/stores/graphHistory', () => ({
  useGraphHistoryStore: () => mocks.graphHistory,
}))
vi.mock('@/stores/learningResources', () => ({ useLearningResourcesStore: () => ({ addResources: vi.fn() }) }))
vi.mock('@/stores/aiSettings', () => ({ useAiSettingsStore: () => ({ tavilyKey: '' }) }))
vi.mock('@/api/project', () => ({ runProjectPipeline: mocks.runProjectPipeline }))
vi.mock('@/utils/askAi', () => ({ buildEntityQuestion: vi.fn(() => '') }))
vi.mock('@/utils/nodeSize', () => ({ cjkAwareWidth: vi.fn(() => 160) }))
vi.mock('@/utils/excalidrawExport', () => ({ graphToExcalidraw: vi.fn(), downloadExcalidraw: vi.fn(), collectG6Positions: vi.fn(() => []) }))
vi.mock('@/utils/techStack', () => ({ detectTechStack: vi.fn(() => []) }))
vi.mock('@/utils/projectTour', () => ({ buildTourStops: vi.fn(() => []), TOUR_ROLE_LABELS: {} }))
vi.mock('@/api', () => ({ default: { get: vi.fn(), post: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { warning: mocks.warning, error: vi.fn(), success: vi.fn() },
  ElMessageBox: { prompt: mocks.prompt, confirm: mocks.confirm },
}))

const ProjectGraphView = (await import('@/views/ProjectGraphView.vue')).default

const ElButton = {
  inheritAttrs: false,
  template: '<button :data-test="$attrs[\'data-test\']" :disabled="$attrs.disabled" @click="$emit(\'click\', $event)"><slot /></button>',
}
const stubs = {
  ElAlert: true,
  ElCard: { template: '<div><slot /></div>' },
  ElDialog: { template: '<div><slot /><slot name="footer" /></div>' },
  ElDivider: true,
  ElEmpty: { template: '<div><slot /></div>' },
  ElIcon: { template: '<span><slot /></span>' },
  ElInput: true,
  ElPopover: { template: '<div><slot name="reference" /><slot /></div>' },
  ElSelect: true,
  ElOption: true,
  ElTag: { template: '<span><slot /></span>' },
  ElButton,
}

function mountView() {
  return mount(ProjectGraphView, { global: { stubs } })
}

describe('ProjectGraphView 当前文件质量检查', () => {
  beforeEach(() => {
    mocks.workspace.activeFile = 'src/a.py'
    mocks.assessment.profile = { target_direction: 'Python Web 后端' }
    mocks.projectGraph.graph = {
      projectId: 'project-1',
      entities: [{ id: 'main', name: 'main', kind: 'function', line_start: 1, line_end: 1 }],
      relations: [], stats: {}, sourcePath: '', written: true,
    }
    mocks.graphHistory.items = []
    mocks.readFile.mockResolvedValue('def ok(): pass')
    mocks.prompt.mockResolvedValue({ value: 'Python Web 后端' })
    mocks.runProjectPipeline.mockResolvedValue({ session_id: 'run-1' })
    vi.clearAllMocks()
    window.api = { fs: { readFile: mocks.readFile } }
  })

  it('将 Python 当前文件和画像方向交给质量检查', async () => {
    const wrapper = mountView()

    await wrapper.find('[data-test="run-pipeline"]').trigger('click')
    await flushPromises()

    expect(mocks.prompt).toHaveBeenCalledWith(
      expect.stringContaining('当前文件'),
      '当前文件质量检查',
      expect.objectContaining({ inputValue: 'Python Web 后端' }),
    )
    expect(mocks.runProjectPipeline).toHaveBeenCalledWith(expect.objectContaining({
      code: 'def ok(): pass', filename: 'a.py', targetDirection: 'Python Web 后端',
    }))
  })

  it('拒绝非 Python 当前文件且不会调用质量检查 API', async () => {
    mocks.workspace.activeFile = 'README.md'
    const wrapper = mountView()

    await wrapper.find('[data-test="run-pipeline"]').trigger('click')
    await flushPromises()

    expect(mocks.runProjectPipeline).not.toHaveBeenCalled()
    expect(mocks.warning).toHaveBeenCalledWith(expect.stringContaining('仅支持 Python 文件'))
  })

  it('移除项目历史只更新本地历史列表', async () => {
    mocks.projectGraph.graph = null
    mocks.graphHistory.items = [{ id: 'project:p1', type: 'project', projectId: 'p1', name: '旧项目', ts: Date.now() }]
    mocks.confirm.mockResolvedValue()
    const wrapper = mountView()
    const remove = wrapper.find('[data-test="history-delete-project:p1"]')

    expect(remove.exists()).toBe(true)
    await remove.trigger('click')
    await flushPromises()

    expect(mocks.confirm).toHaveBeenCalledWith(
      expect.stringContaining('不会删除当前图谱、项目源码或已累计的学习画像'),
      '移除历史快照',
    )
    expect(mocks.graphHistory.remove).toHaveBeenCalledWith('project:p1')
    expect(mocks.graphHistory.items).toEqual([])
  })
})
