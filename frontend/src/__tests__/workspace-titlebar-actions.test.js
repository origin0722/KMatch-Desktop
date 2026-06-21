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
