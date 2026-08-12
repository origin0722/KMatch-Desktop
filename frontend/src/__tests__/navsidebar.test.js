/**
 * 场景：NavSidebar (阶段A Codex 左侧导航栏) 渲染与动作.
 *
 * 替代原 ActivityBar (48px 图标栏) -> 240px 带 label 导航栏.
 * 验证: 壳渲染 + 视图条目 + 底部 AI 助手开关/设置入口经 sidebar store 联动 (单一真相).
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import NavSidebar from '@/ide/NavSidebar.vue'
import { useSidebarStore } from '@/stores/sidebar'

vi.mock('@/ide/TitlebarMenu.vue', () => ({ default: { template: '<nav />' } }))

function mountNav() {
  const pinia = createPinia()
  setActivePinia(pinia)
  return mount(NavSidebar, {
    global: {
      plugins: [pinia],
      stubs: {
        'el-icon': { template: '<span><slot /></span>' },
        Document: true,
        ChatDotRound: true,
        Share: true,
        Connection: true,
        Reading: true,
        DataAnalysis: true,
        Setting: true,
        Sunny: true,
        Moon: true,
      },
    },
  })
}

describe('NavSidebar', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('renders the nav shell and view items', () => {
    const wrapper = mountNav()
    expect(wrapper.find('.nav-sidebar').exists()).toBe(true)
    // 6 视图条目 + 底部 3 工具入口 (AI/主题/设置)
    expect(wrapper.findAll('.nav-item').length).toBeGreaterThanOrEqual(6)
  })

  it('renders a settings entry (gear) that opens the settings view', async () => {
    const wrapper = mountNav()
    const gear = wrapper.find('[data-test="ai-settings-gear"]')
    expect(gear.exists()).toBe(true)
    expect(gear.attributes('title')).toContain('设置')

    await gear.trigger('click')
    expect(useSidebarStore().activeView).toBe('settings')
  })

  it('AI assistant toggle flips aiPanelVisible via sidebar store', async () => {
    const wrapper = mountNav()
    const toggle = wrapper.find('[data-test="ai-toggle-button"]')
    expect(toggle.exists()).toBe(true)
    const before = useSidebarStore().aiPanelVisible

    await toggle.trigger('click')
    expect(useSidebarStore().aiPanelVisible).toBe(!before)
  })

  it('clicking a view item switches activeView', async () => {
    const wrapper = mountNav()
    // 第一个视图条目 = code
    const firstItem = wrapper.find('.nav-items .nav-item')
    expect(firstItem.exists()).toBe(true)

    await firstItem.trigger('click')
    expect(useSidebarStore().activeView).toBe('code')
  })
})
