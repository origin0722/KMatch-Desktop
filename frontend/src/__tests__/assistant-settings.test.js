import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import AssistantSettings from '@/ide/settings/AssistantSettings.vue'
import { useAiSettingsStore } from '@/stores/aiSettings'
import { useChatStore } from '@/stores/chat'

// ElMessageBox.confirm 在 jsdom 下挂起 (无真实点击), mock 成 resolve
// 仅覆写 confirm, 保留 default 插件 + 全部组件 + 其他命名导出
vi.mock('element-plus', async (importOriginal) => {
  const orig = await importOriginal()
  return {
    ...orig,
    ElMessageBox: { ...orig.ElMessageBox, confirm: vi.fn(() => Promise.resolve()) },
  }
})

describe('AssistantSettings', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    globalThis.window = globalThis.window || {}
    window.api = window.api || {}
    window.api.http = { request: vi.fn() }
  })

  const mountOpts = () => ({ global: { plugins: [ElementPlus], stubs: ['el-icon'] } })

  it('renders tool permission rows for all 12 tools', () => {
    const w = mount(AssistantSettings, mountOpts())
    expect(w.findAll('.tool-perm-row')).toHaveLength(12)
  })

  it('changing a tool permission calls setToolPermission', async () => {
    const ai = useAiSettingsStore()
    const w = mount(AssistantSettings, mountOpts())
    // 第一个工具 (read_file) 行的「禁用」分段按钮 → deny (#28 SegmentedControl)
    const firstRow = w.find('.tool-perm-row')
    const denyBtn = firstRow.findAll('button.seg-item').find((b) => b.text() === '禁用')
    expect(denyBtn).toBeTruthy()
    await denyBtn.trigger('click')
    expect(ai.permissionFor('read_file')).toBe('deny')
  })

  it('add memory button calls addMemory', async () => {
    const ai = useAiSettingsStore()
    const before = ai.memories.length
    const w = mount(AssistantSettings, mountOpts())
    await w.find('[data-test="add-memory"]').trigger('click')
    // addMemory with empty title/content returns null (不保存空记忆)
    expect(ai.memories.length).toBe(before)
  })

  it('clear history button calls chat.clearMessages', async () => {
    const chat = useChatStore()
    chat.messages = [{ role: 'user', id: '1', versions: [{ chunks: [] }], activeVersion: 0 }]
    const spy = vi.spyOn(chat, 'clearMessages')
    const w = mount(AssistantSettings, mountOpts())
    await w.find('[data-test="clear-history"]').trigger('click')
    await flushPromises() // 等 onClearHistory 内 await confirm(resolve) → clearMessages
    expect(spy).toHaveBeenCalled()
  })
})
