import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import SettingCard from '@/ide/settings/SettingCard.vue'

describe('SettingCard', () => {
  it('renders title and info', () => {
    const w = mount(SettingCard, {
      props: { title: 'API Key', info: '用于鉴权' },
      slots: { default: '<input />' },
    })
    expect(w.text()).toContain('API Key')
    expect(w.text()).toContain('用于鉴权')
    expect(w.find('input').exists()).toBe(true)
  })

  it('hides info when not provided', () => {
    const w = mount(SettingCard, { props: { title: 'X' }, slots: { default: '<div class="c"/>' } })
    expect(w.find('.setting-info').exists()).toBe(false)
  })
})
