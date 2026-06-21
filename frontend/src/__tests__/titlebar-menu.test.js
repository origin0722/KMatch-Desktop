import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'

const mocks = vi.hoisted(() => ({
  info: vi.fn(),
  warning: vi.fn(),
  success: vi.fn(),
  alert: vi.fn(),
}))

vi.mock('element-plus', () => ({
  ElMessage: {
    info: mocks.info,
    warning: mocks.warning,
    success: mocks.success,
  },
  ElMessageBox: {
    alert: mocks.alert,
  },
}))

import TitlebarMenu from '@/ide/TitlebarMenu.vue'

function mountMenu() {
  return mount(TitlebarMenu, {
    global: {
      stubs: {
        'el-dropdown': {
          name: 'ElDropdown',
          inheritAttrs: false,
          template: '<div v-bind="$attrs"><slot /><slot name="dropdown" /></div>',
        },
        'el-dropdown-menu': { name: 'ElDropdownMenu', template: '<div><slot /></div>' },
        'el-dropdown-item': {
          name: 'ElDropdownItem',
          props: ['command', 'divided'],
          template: '<button type="button"><slot /></button>',
        },
      },
    },
  })
}

describe('TitlebarMenu', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('keeps top titlebar menus for app-level commands only', () => {
    const wrapper = mountMenu()
    const text = wrapper.text()

    expect(text).toContain('项目')
    expect(text).toContain('工具')
    expect(text).toContain('帮助')
    expect(text).not.toContain('学习')
    expect(text).not.toContain('AI 设置')
  })

  it('does not duplicate learning view navigation in titlebar dropdowns', () => {
    const wrapper = mountMenu()
    const text = wrapper.text()

    expect(text).not.toContain('知识图谱')
    expect(text).not.toContain('答题测评')
    expect(text).not.toContain('学习资源')
    expect(text).not.toContain('Agent 协同')
    expect(text).not.toContain('数据看板')
  })

  it('keeps a stable class contract for draggable titlebar and interactive controls', () => {
    const wrapper = mountMenu()

    expect(wrapper.classes()).toContain('titlebar-menu')
    expect(wrapper.find('.brand-block').exists()).toBe(true)
    const dropdowns = wrapper.findAll('.menu-dropdown')
    const triggers = wrapper.findAll('.menu-trigger')

    expect(dropdowns.length).toBeGreaterThan(0)
    expect(triggers.length).toBeGreaterThan(0)
    expect(dropdowns.every((dropdown) => dropdown.find('.menu-trigger').exists())).toBe(true)
  })
})
