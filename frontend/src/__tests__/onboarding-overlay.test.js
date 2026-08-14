import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import OnboardingOverlay from '@/components/OnboardingOverlay.vue'

// mock aiSettings store (隔离真实 store 的 fetchModels/视觉探测副作用)
const setApiKeyMock = vi.fn().mockResolvedValue(undefined)
vi.mock('@/stores/aiSettings', () => ({
  useAiSettingsStore: () => ({
    apiKey: '',
    provider: 'deepseek',
    providerMeta: () => ({ label: 'DeepSeek' }),
    setApiKey: setApiKeyMock,
  }),
  PROVIDERS: [{ id: 'deepseek', label: 'DeepSeek' }],
}))

// stub Element Plus 组件并转发 $attrs (让 @click 能触达)
const global = {
  stubs: {
    'el-button': { template: '<button v-bind="$attrs"><slot /></button>' },
    'el-input': {
      props: ['modelValue'],
      emits: ['update:modelValue'],
      template: `<input :value="modelValue" @input="$emit('update:modelValue', $event.target.value)" v-bind="$attrs" />`,
    },
  },
}

beforeEach(() => {
  localStorage.clear()
  setApiKeyMock.mockClear()
})

describe('OnboardingOverlay', () => {
  it('step 0: 渲染品牌 + 欢迎标题 + 4 个进度点', () => {
    const w = mount(OnboardingOverlay, { props: { visible: true }, global })
    expect(w.text()).toContain('KMatch·知链')
    expect(w.text()).toContain('欢迎来到')
    expect(w.findAll('.ob-dot')).toHaveLength(4)
  })

  it('连续 Next 推进 0->1->2->3, finish 触发 done 并标记 onboarded', async () => {
    const w = mount(OnboardingOverlay, { props: { visible: true }, global })
    const clickByText = (sub) => {
      const btn = w.findAll('button').find((b) => b.text().includes(sub))
      if (!btn) throw new Error(`button not found: ${sub}`)
      return btn.trigger('click')
    }
    await clickByText('继续'); await flushPromises()   // 0 -> 1
    expect(w.text()).toContain('连接你的 AI 助手')
    await clickByText('继续'); await flushPromises()   // 1 -> 2 (keyInput 空, 不调 setApiKey)
    expect(w.text()).toContain('你想学什么')
    expect(setApiKeyMock).not.toHaveBeenCalled()
    await clickByText('继续'); await flushPromises()   // 2 -> 3
    expect(w.text()).toContain('一切就绪')
    await clickByText('进入'); await flushPromises()   // finish
    expect(w.emitted('done')).toBeTruthy()
    expect(w.emitted('done')[0]).toEqual([false]) // T5: 走完引导带 skipped=false
    expect(localStorage.getItem('kmatch-onboarded')).toBe('1')
  })

  it('跳过引导直接触发 done 并标记 onboarded', async () => {
    const w = mount(OnboardingOverlay, { props: { visible: true }, global })
    const skip = w.findAll('button').find((b) => b.text().includes('跳过'))
    await skip.trigger('click')
    expect(w.emitted('done')).toBeTruthy()
    expect(w.emitted('done')[0]).toEqual([true]) // T5: 跳过带 skipped=true
    expect(localStorage.getItem('kmatch-onboarded')).toBe('1')
  })

  it('T5: Key 输入过短时出现软提示 (不阻断)', async () => {
    const w = mount(OnboardingOverlay, { props: { visible: true }, global })
    const clickByText = (sub) => w.findAll('button').find((b) => b.text().includes(sub)).trigger('click')
    await clickByText('继续') // 0 -> 1
    await w.find('input').setValue('sk-short')
    expect(w.text()).toContain('看起来偏短')
  })

  it('visible=false 时不渲染', () => {
    const w = mount(OnboardingOverlay, { props: { visible: false }, global })
    expect(w.find('.ob-overlay').exists()).toBe(false)
  })
})
