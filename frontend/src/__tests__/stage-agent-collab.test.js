/**
 * 场景：StageAgent 协同卡 #30 自动展开 (答题完成后默认展示 AI 协同)。
 *
 * 复现回归: showCollab 可能被滚动驱动提前点亮 (答题中滚动到底, 日志未就绪),
 * 若只在 showCollab 翻真时展开, 提交后日志到达 (hasLogs 翻真) 不会二次触发 → 卡住不展开。
 * 修复: watch 同时监听 [showCollab, hasLogs], 两者成立 (collabOn) 即展开。
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'

const { mockAssessment } = vi.hoisted(() => {
  const { reactive } = require('vue')
  return {
    mockAssessment: reactive({
      hasResults: false, loading: false, phase: 'idle', orchestrationLog: [],
      profile: null, feedbackStrategy: null,
    }),
  }
})
vi.mock('@/stores/assessment', () => ({ useAssessmentStore: () => mockAssessment }))

const StageAgent = (await import('@/components/session/StageAgent.vue')).default
const { useSessionStore } = await import('@/stores/session')

/** stage-body 用 v-show (不卸载), 直接看 display */
function bodyDisplay(w) {
  return w.find('.stage-body').element.style.display
}

describe('StageAgent #30 协同自动展开', () => {
  let pinia
  beforeEach(() => {
    pinia = createPinia()
    setActivePinia(pinia)
    mockAssessment.hasResults = false
    mockAssessment.loading = false
    mockAssessment.phase = 'idle'
    mockAssessment.orchestrationLog = []
    mockAssessment.feedbackStrategy = null
  })

  it('滚动提前点亮 → 提交后日志到达时仍自动展开', async () => {
    const session = useSessionStore()
    const w = mount(StageAgent, { global: { plugins: [pinia] } })
    // 答题中滚动到底: showCollab 点亮, 但 orchestrationLog 尚未就绪
    session.setShowCollab(true)
    await nextTick()
    expect(w.find('.collab-pill').exists()).toBe(false) // hasLogs=false → pill 不亮
    expect(bodyDisplay(w)).toBe('none')                 // 未展开
    // 提交完成: 日志到达 + phase=feedback
    mockAssessment.orchestrationLog = ['[10:00] 🔧 学情检测 开始']
    mockAssessment.phase = 'feedback'
    await nextTick()
    expect(w.find('.collab-pill').exists()).toBe(true)  // 协同已就绪
    expect(bodyDisplay(w)).not.toBe('none')             // 自动展开
    expect(w.find('.collab-tip').exists()).toBe(true)   // 下一步建议可见
  })

  it('showCollab 与日志都已就绪 → 立即自动展开', async () => {
    mockAssessment.orchestrationLog = ['[10:00] ✅ 学情检测 完成']
    mockAssessment.phase = 'feedback'
    const session = useSessionStore()
    const w = mount(StageAgent, { global: { plugins: [pinia] } })
    session.setShowCollab(true)
    await nextTick()
    expect(bodyDisplay(w)).not.toBe('none')
    expect(w.find('.collab-tip').exists()).toBe(true)
  })

  it('可手动收起 (收起后 body 隐藏, pill 仍亮)', async () => {
    mockAssessment.orchestrationLog = ['[10:00] ✅ 学情检测 完成']
    const session = useSessionStore()
    const w = mount(StageAgent, { global: { plugins: [pinia] } })
    session.setShowCollab(true)
    await nextTick()
    expect(bodyDisplay(w)).not.toBe('none')
    // 点击收起按钮
    await w.find('.collab-fold').trigger('click')
    expect(bodyDisplay(w)).toBe('none')
    expect(w.find('.collab-pill').exists()).toBe(true) // 收起后入口仍"就绪"
  })
})
