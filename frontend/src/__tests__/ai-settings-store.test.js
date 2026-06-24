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
import { PROVIDERS } from '@/stores/aiSettings'
import { useCustomProvidersStore } from '@/stores/customProviders'

describe('PROVIDERS registry (Spec A)', () => {
  it('exposes 8 predefined + custom with required metadata', () => {
    const ids = PROVIDERS.map((p) => p.id)
    expect(ids).toEqual(['deepseek','openai','anthropic','moonshot','qwen','gemini','ollama','custom'])
    for (const p of PROVIDERS) {
      expect(typeof p.label).toBe('string')
      expect(['openai','anthropic']).toContain(p.protocol)
      expect(typeof p.iconKey).toBe('string')
      expect(Array.isArray(p.fallbackModels)).toBe(true)
    }
  })

  it('anthropic uses anthropic protocol; others openai', () => {
    expect(PROVIDERS.find((p) => p.id === 'anthropic').protocol).toBe('anthropic')
    expect(PROVIDERS.find((p) => p.id === 'gemini').protocol).toBe('openai')
  })
})

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
    expect(settings.modelReasoningSupport('custom', 'claude-opus-4-8')).toBe('native')

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

  // ---- C1.1: 厂商 & 模型配置 (从 chat.js 迁入, 统一 AI 配置单一源) ----
  it('loads provider/model defaults and exposes provider helpers', () => {
    const settings = useAiSettingsStore()

    expect(settings.provider).toBe('deepseek')
    expect(settings.model).toBe('deepseek-v4-pro')
    expect(settings.apiKey).toBe('')
    // DeepSeek 预置 Base URL
    expect(settings.getBaseUrl()).toBe('https://api.deepseek.com/v1')
    // 无 apiKey 时 fetchModels 走 fallback, 不触网
    expect(settings.models).toContain('deepseek-v4-pro')
  })

  it('persists provider/apiKey and restores them; custom:<uuid> baseUrl 来自 customProviders', async () => {
    const settings = useAiSettingsStore()
    const cps = useCustomProvidersStore()
    cps.add({ id: 'default', name: '自定义', baseUrl: 'https://my.proxy/v1', protocol: 'openai' })

    await settings.setApiKey('sk-test-123')
    await settings.setProvider('custom:default')
    // 切到 custom:default 时 apiKey 会取自 customProviders 该条目 (此时为空); 再写入用户 key
    await settings.setApiKey('sk-test-456')

    setActivePinia(createPinia())
    const restored = useAiSettingsStore()

    expect(restored.provider).toBe('custom:default')
    expect(restored.apiKey).toBe('sk-test-456')
    // custom:default getBaseUrl 取 customProviders.baseUrl
    expect(restored.getBaseUrl()).toBe('https://my.proxy/v1')
  })

  it('fetchModels 失败/离线时仍校正 model 到当前厂商 fallback (不残留跨厂商 model)', async () => {
    // window.api 未 mock → fetchModels 走 catch; custom 无 base → !base 分支
    const settings = useAiSettingsStore()
    settings.setProvider('openai') // 不 await: provider 已同步设
    // 模拟残留跨厂商 model
    settings.model = 'deepseek-v4-pro'
    await settings.fetchModels()
    // openai fallback 含 gpt-4o; model 应被校正为 openai 系, 不再是 deepseek-*
    expect(settings.models).toContain('gpt-4o')
    expect(settings.model).not.toMatch(/^deepseek/)
  })

  it('migrates provider config from legacy chat localStorage keys', () => {
    localStorage.setItem('kmatch-chat-provider', 'openai')
    localStorage.setItem('kmatch-chat-apikey', 'sk-legacy')

    const settings = useAiSettingsStore()

    expect(settings.provider).toBe('openai')
    expect(settings.apiKey).toBe('sk-legacy')
  })
})

describe('provider value-set: custom:<uuid> (Spec A)', () => {
  beforeEach(() => { setActivePinia(createPinia()); localStorage.clear() })

  it('migrates legacy customBaseUrl + provider="custom" to customProviders[id=default]', () => {
    localStorage.setItem('kmatch-ai-settings', JSON.stringify({
      providerConfig: { provider: 'custom', apiKey: 'sk-X', customBaseUrl: 'http://x/v1', model: 'm' },
    }))
    const s = useAiSettingsStore()
    const cps = useCustomProvidersStore()
    expect(s.provider).toBe('custom:default')
    expect(cps.list).toHaveLength(1)
    expect(cps.get('default').baseUrl).toBe('http://x/v1')
    expect(cps.get('default').apiKey).toBe('sk-X')
  })

  it('providerMeta() reads from customProviders when provider startsWith custom:', () => {
    const cps = useCustomProvidersStore()
    cps.add({ id: 'default', name: 'X', baseUrl: 'http://y/v1', apiKey: 'k', protocol: 'openai' })
    const s = useAiSettingsStore()
    s.provider = 'custom:default'   // 直接改 ref, 不走 setProvider 避免 fetchModels
    const meta = s.providerMeta()
    expect(meta.baseUrl).toBe('http://y/v1')
    expect(meta.protocol).toBe('openai')
    expect(meta.label).toBe('X')
  })

  it('getBaseUrl returns custom entry baseUrl', () => {
    const cps = useCustomProvidersStore()
    cps.add({ id: 'default', name: 'X', baseUrl: 'http://z/v1' })
    const s = useAiSettingsStore()
    s.provider = 'custom:default'
    expect(s.getBaseUrl()).toBe('http://z/v1')
  })

  it('falls back to PROVIDERS[0] when custom:<uuid> entry missing', () => {
    const s = useAiSettingsStore()
    s.provider = 'custom:ghost'
    expect(s.providerMeta().id).toBe('deepseek')
  })

  it('after migration, providerMeta still resolves cleanly (caller can map back to custom for UI)', () => {
    const cps = useCustomProvidersStore()
    cps.add({ id: 'default', name: '自定义', baseUrl: 'http://x/v1', apiKey: 'k' })
    const s = useAiSettingsStore()
    s.provider = 'custom:default'
    // Caller (AssistantPanel) maps custom:* back to 'custom' for the dropdown; both must resolve cleanly
    expect(s.providerMeta().baseUrl).toBe('http://x/v1')
    expect(s.providerMeta().iconKey).toBe('custom')
  })
})

describe('modelReasoningSupport 委托 capabilityOf（Spec A 收敛为两态）', () => {
  beforeEach(() => { setActivePinia(createPinia()); localStorage.clear() })

  it('返回 native | prompt-only 两态', () => {
    const s = useAiSettingsStore()
    expect(s.modelReasoningSupport('anthropic', 'claude-fable-5')).toBe('native')
    expect(s.modelReasoningSupport('anthropic', 'claude-opus-4-8')).toBe('native')
    expect(s.modelReasoningSupport('openai', 'gpt-4o')).toBe('prompt-only')
    expect(s.modelReasoningSupport('openai', 'o1')).toBe('native')
    expect(s.modelReasoningSupport('foo', 'bar')).toBe('prompt-only')   // 旧 'unknown' 收敛
  })
})

describe('reasoningMode auto-downgrade (Spec A)', () => {
  beforeEach(() => { setActivePinia(createPinia()); localStorage.clear() })

  it('deep 模式下切到 prompt-only 模型 -> 自动降级为 auto', async () => {
    const s = useAiSettingsStore()
    s.provider = 'anthropic'
    s.model = 'claude-fable-5'
    s.setReasoningMode('deep')
    expect(s.reasoningMode).toBe('deep')

    s.provider = 'openai'
    s.model = 'gpt-4o'        // prompt-only 模型
    await new Promise(r => setTimeout(r, 0))   // watch flush
    expect(s.reasoningMode).toBe('auto')
  })

  it('fast 不被降级', async () => {
    const s = useAiSettingsStore()
    s.setReasoningMode('fast')
    s.provider = 'openai'
    s.model = 'gpt-4o'
    await new Promise(r => setTimeout(r, 0))
    expect(s.reasoningMode).toBe('fast')
  })
})
