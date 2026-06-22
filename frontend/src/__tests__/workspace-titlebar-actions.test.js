/**
 * 场景：Workspace 壳布局——标题栏动作与侧栏/AI 面板可见性联动。
 *
 * Workspace.vue 是 IDE 壳，把 ActivityBar/MainArea/AssistantPanel/StatusBar/TitlebarMenu
 * 组合在一起。这里把重子组件 stub 掉，只验壳层逻辑：
 *  - 标题栏按钮能切换侧栏（sidebarVisible）与 AI 面板（aiPanelVisible）可见性；
 *  - 切换经 sidebar store（单一真相），而非组件局部状态。
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import Workspace from '@/views/Workspace.vue'
import { useSidebarStore } from '@/stores/sidebar'

vi.mock('@/ide/ActivityBar.vue', () => ({ default: { template: '<div />' } }))
vi.mock('@/ide/MainArea.vue', () => ({ default: { template: '<main />' } }))
vi.mock('@/ide/AssistantPanel.vue', () => ({ default: { template: '<aside />' } }))
vi.mock('@/ide/StatusBar.vue', () => ({ default: { template: '<footer />' } }))
vi.mock('@/ide/TitlebarMenu.vue', () => ({ default: { template: '<nav />' } }))

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

describe('Workspace titlebar actions', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders a gear button for AI settings instead of a titlebar AI settings menu', () => {
    const wrapper = mountWorkspace()
    const gear = wrapper.find('[data-test="ai-settings-gear"]')
    expect(gear.exists()).toBe(true)
    expect(gear.attributes('title')).toContain('AI 设置')
  })

  it('gear reveals the assistant panel as interim settings entry', async () => {
    const pinia = createPinia()
    const wrapper = mountWorkspace(pinia)
    const sidebar = useSidebarStore()
    sidebar.aiPanelVisible = false

    await wrapper.find('[data-test="ai-settings-gear"]').trigger('click')
    expect(sidebar.aiPanelVisible).toBe(true)
  })
})
