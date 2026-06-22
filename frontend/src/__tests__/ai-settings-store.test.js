/**
 * 场景：aiSettings store——AI 助手持久化设置。
 *
 * aiSettings 持有代理、工具权限（allow/ask/deny × 6 工具）、记忆条目、推理模式（auto/fast/deep），
 * 统一序列化为一个 JSON blob 存 localStorage['kmatch-ai-settings']。
 * 这里验证：持久化往返、各字段默认值、reasoningMode 驱动后端 thinking 字段的映射、
 * 工具权限决策（permissionFor）。每个测试前清空 localStorage 保证隔离。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAiSettingsStore } from '@/stores/aiSettings'

function resetStorage() {
  localStorage.clear()
}

describe('aiSettings store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    resetStorage()
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-06-21T08:00:00.000Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('loads safe defaults', () => {
    const settings = useAiSettingsStore()

    expect(settings.proxy.enabled).toBe(false)
    expect(settings.proxy.type).toBe('http')
    expect(settings.proxy.url).toBe('')
    expect(settings.proxy.scope).toBe('all')

    expect(settings.toolPermissions.read_file).toBe('allow')
    expect(settings.toolPermissions.list_directory).toBe('allow')
    expect(settings.toolPermissions.write_file).toBe('ask')
    expect(settings.toolPermissions.generate_project_graph).toBe('allow')
    expect(settings.toolPermissions.code_review).toBe('allow')
    expect(settings.toolPermissions.code_test).toBe('allow')

    expect(settings.reasoningMode).toBe('auto')
    expect(settings.enabledMemories).toEqual([])
  })

  it('persists proxy, permissions, and reasoning mode', () => {
    const settings = useAiSettingsStore()

    settings.setProxy({ enabled: true, type: 'socks', url: 'socks://127.0.0.1:7890', scope: 'currentProvider' })
    settings.setToolPermission('code_test', 'deny')
    settings.setReasoningMode('deep')

    setActivePinia(createPinia())
    const restored = useAiSettingsStore()

    expect(restored.proxy).toEqual({ enabled: true, type: 'socks', url: 'socks://127.0.0.1:7890', scope: 'currentProvider' })
    expect(restored.toolPermissions.code_test).toBe('deny')
    expect(restored.reasoningMode).toBe('deep')
  })

  it('adds, updates, disables, and removes memory cards', () => {
    const settings = useAiSettingsStore()

    const created = settings.addMemory({
      type: 'preference',
      title: '回答风格',
      content: '用户喜欢中文解释，先讲思路再给代码。',
      source: 'manual',
    })

    expect(created.id).toMatch(/^mem_/)
    expect(created).toMatchObject({
      type: 'preference',
      title: '回答风格',
      content: '用户喜欢中文解释，先讲思路再给代码。',
      source: 'manual',
      enabled: true,
      createdAt: '2026-06-21T08:00:00.000Z',
      updatedAt: '2026-06-21T08:00:00.000Z',
    })
    expect(settings.enabledMemories).toHaveLength(1)
    expect(settings.formatEnabledMemories()).toContain('回答风格')

    settings.updateMemory(created.id, { enabled: false })
    expect(settings.enabledMemories).toHaveLength(0)

    settings.removeMemory(created.id)
    expect(settings.memories).toHaveLength(0)
  })

  it('returns model reasoning support and instructions', () => {
    const settings = useAiSettingsStore()

    expect(settings.modelReasoningSupport('deepseek', 'deepseek-reasoner')).toBe('native')
    expect(settings.modelReasoningSupport('deepseek', 'deepseek-v4-pro')).toBe('native')
    expect(settings.modelReasoningSupport('deepseek', 'deepseek-v3')).toBe('prompt-only')
    expect(settings.modelReasoningSupport('custom', 'claude-opus-4-8')).toBe('native-when-supported-by-backend')

    settings.setReasoningMode('deep')
    expect(settings.reasoningInstruction('deepseek', 'deepseek-v4-pro')).toContain('当前模型支持 reasoning')

    settings.setReasoningMode('fast')
    expect(settings.reasoningInstruction('deepseek', 'deepseek-reasoner')).toContain('思考模式: 快速')
  })

  it('ignores invalid tool permission changes', () => {
    const settings = useAiSettingsStore()
    settings.setToolPermission('code_test', 'deny')
    settings.setToolPermission('code_test', 'invalid')
    settings.setToolPermission('missing_tool', 'allow')

    expect(settings.toolPermissions.code_test).toBe('deny')
    expect(settings.permissionFor('missing_tool')).toBe('deny')
  })

  it('ignores corrupted persisted permission values and denies unknown tools', () => {
    localStorage.setItem('kmatch-ai-settings', JSON.stringify({
      toolPermissions: {
        write_file: 'yes',
        unknown_tool: 'allow',
        code_test: 'deny',
      },
    }))

    const settings = useAiSettingsStore()

    expect(settings.toolPermissions.write_file).toBe('ask')
    expect(settings.toolPermissions.code_test).toBe('deny')
    expect(settings.toolPermissions.unknown_tool).toBeUndefined()
    expect(settings.permissionFor('unknown_tool')).toBe('deny')
  })

  it('does not crash when persisted memory title and content are numeric', () => {
    localStorage.setItem('kmatch-ai-settings', JSON.stringify({
      memories: [{
        id: 'mem_numeric',
        type: 'project',
        title: 123,
        content: 456,
        source: 'manual',
      }],
    }))

    const settings = useAiSettingsStore()

    expect(settings.memories[0]).toMatchObject({
      id: 'mem_numeric',
      title: '123',
      content: '456',
      enabled: true,
    })
    expect(settings.enabledMemories).toHaveLength(1)
  })

  it('formats at most ten enabled memories and truncates long content', () => {
    const settings = useAiSettingsStore()
    for (let i = 0; i < 12; i++) {
      settings.addMemory({ title: `记忆${i}`, content: 'x'.repeat(260), type: 'project' })
    }

    const block = settings.formatEnabledMemories(10, 20)

    expect(block.match(/\[project\]/g)).toHaveLength(10)
    expect(block).toContain('xxxxxxxxxxxxxxxxxxxx…')
    expect(block).not.toContain('记忆10')
  })
})
