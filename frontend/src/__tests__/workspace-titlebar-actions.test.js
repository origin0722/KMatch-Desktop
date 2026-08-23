/**
 * 场景：Workspace 壳布局--组合 NavSidebar/MainArea/AssistantPanel/StatusBar.
 *
 * 阶段A Codex 化: 标题栏精简为拖拽条 + 工作区名, 品牌/菜单/工具入口(AI 开关/设置)移至 NavSidebar.
 * 这里 stub 重子组件, 只验壳层组合 (动作联动已下沉到 NavSidebar 自身测试, 见 navsidebar.test.js).
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import Workspace from '@/views/Workspace.vue'

vi.mock('@/ide/NavSidebar.vue', () => ({ default: { template: '<nav data-test="nav-sidebar" />' } }))
vi.mock('@/ide/MainArea.vue', () => ({ default: { template: '<main data-test="main-area" />' } }))
vi.mock('@/ide/AssistantPanel.vue', () => ({ default: { template: '<aside data-test="assistant-panel" />' } }))
vi.mock('@/ide/StatusBar.vue', () => ({ default: { template: '<footer data-test="status-bar" />' } }))
// issue-62: ReadyGate 是壳层前置门, 单测中挂载即放行 (就绪门自身逻辑见 ready-gate.test.js)
vi.mock('@/ide/ReadyGate.vue', () => ({
  default: {
    emits: ['ready', 'skip'],
    mounted() { this.$emit('ready') },
    template: '<div />',
  },
}))

vi.mock('@/stores/workspace', () => ({
  useWorkspaceStore: () => ({ hasProject: false, rootName: '', loadRecent: vi.fn() }),
}))

function mountWorkspace(pinia = createPinia()) {
  return mount(Workspace, {
    global: {
      plugins: [pinia],
      stubs: {
        'el-icon': { template: '<span><slot /></span>' },
        FolderOpened: true,
        // WIP 把 AssistantPanel 改 defineAsyncComponent 懒加载后, trivial vi.mock 与 test-utils
        // componentsTransformer 的 isTeleport 检查冲突; 用 stub 直接顶替, 不走 async mock 解析
        AssistantPanel: { template: '<aside data-test="assistant-panel" />' },
      },
    },
  })
}

describe('Workspace shell composition', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders NavSidebar and MainArea in the body', async () => {
    const wrapper = mountWorkspace()
    await flushPromises()
    expect(wrapper.find('[data-test="nav-sidebar"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="main-area"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="status-bar"]').exists()).toBe(true)
  })

  it('issue-85: 顶部黑色标题栏已移除 (无边框窗口)', async () => {
    const wrapper = mountWorkspace()
    await flushPromises()
    expect(wrapper.find('.ide-titlebar').exists()).toBe(false)
  })
})
