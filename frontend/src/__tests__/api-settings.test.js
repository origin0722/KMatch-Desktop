/**
 * ApiSettings.vue — 设置页「API 设置」栏目 挂载测试
 *
 * 验证: 分开/统一模式切换、统一卡片渲染、应用到全部写两端、测试连通性调 /api/agents/ping。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { nextTick } from 'vue'

const aiMock = vi.hoisted(() => ({
  provider: 'deepseek', apiKey: '', model: 'deepseek-v4-pro',
  getBaseUrl: () => 'https://api.deepseek.com/v1',
  providerMeta: () => ({ protocol: aiMock.provider === 'anthropic' ? 'anthropic' : 'openai' }),
  setProvider: vi.fn(), setApiKey: vi.fn(), setModel: vi.fn(),
}))
const agMock = vi.hoisted(() => ({
  state: { provider: 'deepseek', baseUrl: '', apiKey: '', model: 'deepseek-v4-pro', useOverrides: false },
  setUseOverrides: vi.fn(), setProvider: vi.fn(), setBaseUrl: vi.fn(), setApiKey: vi.fn(), setModel: vi.fn(),
}))
vi.mock('@/stores/aiSettings', () => ({
  PROVIDERS: [
    { id: 'deepseek', label: 'DeepSeek', baseUrl: 'https://api.deepseek.com/v1', protocol: 'openai' },
    { id: 'qwen', label: '通义千问', baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1', protocol: 'openai' },
  ],
  useAiSettingsStore: () => aiMock,
}))
vi.mock('@/stores/agentLlm', () => ({ useAgentLlmStore: () => agMock }))
const httpMock = vi.hoisted(() => ({ post: vi.fn() }))
vi.mock('@/api/index', () => ({ default: httpMock }))

const ApiSettings = (await import('@/ide/settings/ApiSettings.vue')).default

describe('ApiSettings.vue (API 设置栏目)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('默认分开模式: 渲染「AI 助手」与「出题/Agent」两行卡片', () => {
    const w = mount(ApiSettings)
    expect(w.findAll('.row-card').length).toBe(2)
    expect(w.text()).toContain('AI 助手')
    expect(w.text()).toContain('出题 / Agent 引擎')
  })

  it('切到统一模式: 渲染统一卡片与「应用到全部」，点击后写两端', async () => {
    const w = mount(ApiSettings)
    await w.find('input[type=checkbox]').setValue(true) // 统一
    await nextTick()
    expect(w.text()).toContain('统一配置')
    // 填 key
    const keyInput = w.findAll('.unified input[type=password]')[0]
    await keyInput.setValue('sk-unified')
    await nextTick()
    await w.findAll('.unified button').find((b) => b.text().includes('应用到全部')).trigger('click')
    await nextTick()
    expect(aiMock.setApiKey).toHaveBeenCalledWith('sk-unified')
    expect(agMock.setApiKey).toHaveBeenCalledWith('sk-unified')
    expect(agMock.setUseOverrides).toHaveBeenCalledWith(true)
  })

  it('测试连通性调用 /api/agents/ping 并显示成功', async () => {
    httpMock.post.mockResolvedValue({ data: { ok: true, content: 'pong-123' } })
    aiMock.apiKey = 'sk-chat' // mount 前设置 (普通属性不响应式, 避免按钮 :disabled 不刷新)
    const w = mount(ApiSettings)
    await nextTick()
    const testBtn = w.findAll('.row-card')[0].findAll('button').find((b) => b.text().includes('测试连通性'))
    expect(testBtn.attributes('disabled')).toBeUndefined()
    await testBtn.trigger('click')
    await flushPromises()
    expect(httpMock.post).toHaveBeenCalledWith('/api/agents/ping', {
      llm_overrides: { api_key: 'sk-chat', base_url: 'https://api.deepseek.com/v1', model: 'deepseek-v4-pro' },
      protocol: 'openai',
    })
    expect(w.text()).toContain('连接成功')
  })

  it('AI 助手行选 anthropic → 连通性带 protocol=anthropic', async () => {
    httpMock.post.mockResolvedValue({ data: { ok: true, content: 'hi' } })
    aiMock.provider = 'anthropic'
    aiMock.apiKey = 'sk-ant'
    const w = mount(ApiSettings)
    await nextTick()
    const btn = w.findAll('.row-card')[0].findAll('button').find((b) => b.text().includes('测试连通性'))
    await btn.trigger('click')
    await flushPromises()
    expect(httpMock.post).toHaveBeenCalledWith('/api/agents/ping', {
      llm_overrides: { api_key: 'sk-ant', base_url: 'https://api.deepseek.com/v1', model: 'deepseek-v4-pro' },
      protocol: 'anthropic',
    })
  })
})
