/**
 * OnboardingOverlay 单测 (P4 更新)
 *
 * P4 变更:
 * - Step 2 改双场景卡 (学新技能 / 有项目二开)
 * - finish emit done(skipped, scene) -> Workspace 按场景落地
 * - onboarded 标记改由 sidebar store 单点写 (本组件不再写, 测试不再断言)
 * - 学新技能 goal -> kmatch-onboard-direction 映射 (StageGoal 读取预填)
 */
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

  it('连续 Next 推进 0->1->2->3, finish 触发 done(false, scene)', async () => {
    const w = mount(OnboardingOverlay, { props: { visible: true }, global })
    const clickByText = (sub) => {
      const btn = w.findAll('button').find((b) => b.text().includes(sub))
      if (!btn) throw new Error(`button not found: ${sub}`)
      return btn.trigger('click')
    }
    await clickByText('继续'); await flushPromises()   // 0 -> 1
    expect(w.text()).toContain('连接你的 AI 助手')
    await clickByText('继续'); await flushPromises()   // 1 -> 2 (keyInput 空, 不调 setApiKey)
    expect(w.text()).toContain('你想怎么开始')
    expect(setApiKeyMock).not.toHaveBeenCalled()
    await clickByText('继续'); await flushPromises()   // 2 -> 3
    expect(w.text()).toContain('一切就绪')
    await clickByText('进入'); await flushPromises()   // finish
    expect(w.emitted('done')).toBeTruthy()
    // P4: done 携带 (skipped=false, scene='learn')
    expect(w.emitted('done')[0]).toEqual([false, 'learn'])
  })

  it('跳过引导触发 done(true, null)', async () => {
    const w = mount(OnboardingOverlay, { props: { visible: true }, global })
    const skip = w.findAll('button').find((b) => b.text().includes('跳过'))
    await skip.trigger('click')
    expect(w.emitted('done')).toBeTruthy()
    expect(w.emitted('done')[0]).toEqual([true, null])
  })

  it('P4: step 2 渲染双场景卡 (学新技能 / 有项目)', async () => {
    const w = mount(OnboardingOverlay, { props: { visible: true }, global })
    const clickByText = (sub) => w.findAll('button').find((b) => b.text().includes(sub)).trigger('click')
    await clickByText('继续'); await flushPromises()  // 0 -> 1
    await clickByText('继续'); await flushPromises()  // 1 -> 2
    expect(w.findAll('.ob-scene')).toHaveLength(2)
    expect(w.text()).toContain('学新技能')
    expect(w.text()).toContain('有项目二次开发')
  })

  it('P4: 选学新技能 + goal -> next 写入 kmatch-onboard-direction', async () => {
    const w = mount(OnboardingOverlay, { props: { visible: true }, global })
    const clickByText = (sub) => w.findAll('button').find((b) => b.text().includes(sub)).trigger('click')
    await clickByText('继续'); await flushPromises()  // 0 -> 1
    await clickByText('继续'); await flushPromises()  // 1 -> 2
    // 默认 scene=learn, goal=basic -> 点继续应写方向
    await clickByText('继续'); await flushPromises()  // 2 -> 3
    expect(localStorage.getItem('kmatch-onboard-direction')).toBe('Python 基础语法入门')
  })

  it('P4: 选有项目场景 -> next 清除方向, finish emit scene=project', async () => {
    localStorage.setItem('kmatch-onboard-direction', '旧方向')
    const w = mount(OnboardingOverlay, { props: { visible: true }, global })
    const clickByText = (sub) => w.findAll('button').find((b) => b.text().includes(sub)).trigger('click')
    await clickByText('继续'); await flushPromises()  // 0 -> 1
    await clickByText('继续'); await flushPromises()  // 1 -> 2
    // 点有项目场景
    const projectBtn = w.findAll('.ob-scene').find((b) => b.text().includes('有项目'))
    await projectBtn.trigger('click')
    await clickByText('继续'); await flushPromises()  // 2 -> 3
    expect(localStorage.getItem('kmatch-onboard-direction')).toBe(null) // 清除
    await clickByText('进入'); await flushPromises()  // finish
    expect(w.emitted('done')[0]).toEqual([false, 'project'])
  })

  it('P4: finish 清除 step 残留 (不再写 onboarded)', async () => {
    localStorage.setItem('kmatch-onboard-step', '2')
    const w = mount(OnboardingOverlay, { props: { visible: true }, global })
    // step 从 localStorage 恢复为 2
    const clickByText = (sub) => w.findAll('button').find((b) => b.text().includes(sub)).trigger('click')
    await clickByText('继续'); await flushPromises()  // 2 -> 3
    await clickByText('进入'); await flushPromises()  // finish
    expect(localStorage.getItem('kmatch-onboard-step')).toBe(null) // 清残留
    expect(localStorage.getItem('kmatch-onboarded')).toBe(null)   // 不再由组件写
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
