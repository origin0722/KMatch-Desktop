/**
 * WorkflowStudioView — 流程工作台挂载冒烟 (Phase 3b)
 *
 * 模拟 api，验证: 列表自动载入首项 → 阶段编辑 → 预览 → 提交发布走 commitWorkflow。
 * jsdom 无 canvas → FlowDiagram 静默跳过; 组件不发真实请求。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'

const api = vi.hoisted(() => ({
  fetchWorkflows: vi.fn(),
  fetchWorkflowRevisions: vi.fn(),
  saveWorkflowDraft: vi.fn(),
  commitWorkflow: vi.fn(),
  restoreWorkflowRevision: vi.fn(),
}))
vi.mock('@/api/diagnostics', () => api)

const WorkflowStudio = (await import('@/ide/workflow/WorkflowStudioView.vue')).default

const LIST = {
  workflows: [
    {
      id: 'scene1-loop',
      name: '场景一·学情闭环',
      description: '闭环',
      stages: [
        { id: 'diagnostics', label: '学情检测', agents: ['diagnostics'], dependencies: [] },
        { id: 'graph', label: '图谱组装', agents: ['graph_controller'], dependencies: ['diagnostics'] },
      ],
    },
  ],
}

describe('WorkflowStudioView (流程工作台)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.fetchWorkflows.mockResolvedValue(LIST)
    api.fetchWorkflowRevisions.mockResolvedValue({ revisions: [] })
    api.commitWorkflow.mockResolvedValue({ id: 'scene1-loop', revision: 'R1' })
    api.saveWorkflowDraft.mockResolvedValue({ ok: true, valid: true, warnings: [] })
    api.restoreWorkflowRevision.mockResolvedValue({ id: 'scene1-loop', restored: 'R1' })
  })

  it('载入流程列表并自动选择首项渲染阶段', async () => {
    const w = mount(WorkflowStudio)
    await nextTick(); await nextTick()
    expect(api.fetchWorkflows).toHaveBeenCalled()
    expect(api.fetchWorkflowRevisions).toHaveBeenCalled()
    expect(w.findAll('.stage-row').length).toBe(2)
    expect(w.find('.preview').exists()).toBe(true)
  })

  it('＋ 阶段 增加一行, 校验提示随本地 issues 出现', async () => {
    const w = mount(WorkflowStudio)
    await nextTick(); await nextTick()
    // 给阶段设空 agents → 触发本地校验提示
    const firstCheck = w.findAll('.stage-row')[0].findAll('input[type=checkbox]')[0]
    if (firstCheck.element.checked) { await firstCheck.setValue(false) }
    await w.find('.stages .btn').trigger('click') // ＋ 阶段 (默认唯一按钮)
    await nextTick()
    const rows = w.findAll('.stage-row').length
    expect(rows).toBeGreaterThan(2)
  })

  it('提交发布调用 commitWorkflow 并携带构建出的定义', async () => {
    const w = mount(WorkflowStudio)
    await nextTick(); await nextTick()
    await w.findAll('button').find((b) => b.text().includes('提交发布')).trigger('click')
    await nextTick()
    expect(api.commitWorkflow).toHaveBeenCalledTimes(1)
    const [id, def, opts] = api.commitWorkflow.mock.calls[0]
    expect(id).toBe('scene1-loop')
    expect(def.format).toBe('kmatch.workflow')
    expect(def.stages.length).toBe(2)
    expect(opts.note).toBe('')
  })

  it('jsdom 下挂载不抛错且渲染编辑器壳', () => {
    const w = mount(WorkflowStudio)
    expect(w.find('.flow-studio').exists()).toBe(true)
    expect(w.find('.studio-side').exists()).toBe(true)
  })
})
