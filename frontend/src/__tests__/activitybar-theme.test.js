import fs from 'node:fs'
import path from 'node:path'
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ActivityBar from '@/ide/ActivityBar.vue'

function mountBar() {
  const pinia = createPinia()
  setActivePinia(pinia)
  return mount(ActivityBar, {
    global: {
      plugins: [pinia],
      stubs: {
        'el-icon': { template: '<span><slot /></span>' },
        Document: true,
        Share: true,
        Edit: true,
        Reading: true,
        Connection: true,
        DataAnalysis: true,
        ChatDotRound: true,
        Sunny: true,
        Moon: true,
      },
    },
  })
}

function readSource(relativePath) {
  return fs.readFileSync(path.resolve(__dirname, relativePath), 'utf8')
}

describe('ActivityBar theme contract', () => {
  it('renders the ActivityBar shell and items', () => {
    const wrapper = mountBar()
    expect(wrapper.find('.activity-bar').exists()).toBe(true)
    expect(wrapper.findAll('.activity-item').length).toBeGreaterThan(0)
  })

  it('defines activity shell token names for both light and dark themes', () => {
    const css = readSource('../styles/theme.css')
    const activityTokens = [
      '--km-activity-bg',
      '--km-activity-text',
      '--km-activity-hover',
      '--km-activity-active-bg',
      '--km-activity-active-text',
      '--km-activity-active',
    ]

    const lightTheme = css.match(/:root\s*\{[\s\S]*?\/\* ---- 状态栏 ---- \*\//)?.[0] ?? ''
    const darkTheme = css.match(/html\.dark\s*\{[\s\S]*?\/\* ---- 状态栏 ---- \*\//)?.[0] ?? ''

    for (const token of activityTokens) {
      expect(lightTheme).toContain(`${token}:`)
      expect(darkTheme).toContain(`${token}:`)
    }
  })

  it('uses activity token contract without dimming inactive icons by opacity', () => {
    const source = readSource('../ide/ActivityBar.vue')
    const activityTokens = [
      '--km-activity-bg',
      '--km-activity-text',
      '--km-activity-hover',
      '--km-activity-active-bg',
      '--km-activity-active-text',
      '--km-activity-active',
    ]

    for (const token of activityTokens) {
      expect(source).toContain(token)
    }

    expect(source).not.toContain('rgba(255,255,255,0.06)')
    expect(source).not.toContain('rgba(255,255,255,0.08)')
    expect(source).not.toMatch(/\.activity-item\s*\{[\s\S]*?opacity\s*:\s*(?:0?\.\d+|[2-9]|[1-9]\d+)/)
  })
})
