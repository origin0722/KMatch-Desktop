/**
 * 场景：Workspace 壳布局--组合 NavSidebar/MainArea/AssistantPanel/StatusBar.
 *
 * 阶段A Codex 化: 标题栏精简为拖拽条 + 工作区名, 品牌/菜单/工具入口(AI 开关/设置)移至 NavSidebar.
 * 这里 stub 重子组件, 只验壳层组合 (动作联动已下沉到 NavSidebar 自身测试, 见 navsidebar.test.js).
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import Workspace from '@/views/Workspace.vue'

vi.mock('@/ide/NavSidebar.vue', () => ({ default: { template: '<nav data-test="nav-sidebar" />' } }))
vi.mock('@/ide/MainArea.vue', () => ({ default: { template: '<main data-test="main-area" />' } }))
vi.mock('@/ide/AssistantPanel.vue', () => ({ default: { template: '<aside data-test="assistant-panel" />' } }))
vi.mock('@/ide/StatusBar.vue', () => ({ default: { template: '<footer data-test="status-bar" />' } }))

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
      },
    },
  })
}

describe('Workspace shell composition', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders NavSidebar and MainArea in the body', () => {
    const wrapper = mountWorkspace()
    expect(wrapper.find('[data-test="nav-sidebar"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="main-area"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="status-bar"]').exists()).toBe(true)
  })

  it('titlebar is a slim drag bar; AI settings gear moved to NavSidebar', () => {
    const wrapper = mountWorkspace()
    expect(wrapper.find('.ide-titlebar').exists()).toBe(true)
    // 标题栏已精简, gear 不在 Workspace 壳层 (在 NavSidebar 内)
    expect(wrapper.find('.ide-titlebar [data-test="ai-settings-gear"]').exists()).toBe(false)
  })
})
