/**
 * apiSettings — 统一 API 配置协调层 单测
 *
 * 覆盖: 预设模型清单 / 模式切换持久化 / applyUnified 落到 aiSettings+agentLlm /
 *       testConnectivity 走 /api/agents/ping。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

const aiMock = vi.hoisted(() => ({
  setProvider: vi.fn().mockResolvedValue(undefined),
  setApiKey: vi.fn(),
  setModel: vi.fn(),
}))
const agMock = vi.hoisted(() => ({
  setUseOverrides: vi.fn(),
  setProvider: vi.fn(),
  setBaseUrl: vi.fn(),
  setApiKey: vi.fn(),
  setModel: vi.fn(),
}))
vi.mock('@/stores/aiSettings', () => ({
  PROVIDERS: [
    { id: 'deepseek', label: 'DeepSeek', baseUrl: 'https://api.deepseek.com/v1', protocol: 'openai' },
    { id: 'qwen', label: '通义千问', baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1', protocol: 'openai' },
  ],
  useAiSettingsStore: () => aiMock,
}))
vi.mock('@/stores/agentLlm', () => ({ useAgentLlmStore: () => agMock }))
vi.mock('@/api/index', () => ({ default: { post: vi.fn() } }))

import http from '@/api/index'
import { useApiSettingsStore, presetModelsFor, allPresetModels } from '@/stores/apiSettings'

describe('apiSettings (统一 API 设置)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('预设模型清单按厂商 + 全量合并', () => {
    expect(presetModelsFor('deepseek')).toContain('deepseek-v4-pro')
    expect(presetModelsFor('deepseek')).toContain('deepseek-v4-flash')
    expect(allPresetModels()).toContain('qwen3.5-plus')
    expect(presetModelsFor('nonexistent')).toEqual([])
  })

  it('模式默认 separate; setMode 持久化', () => {
    const s = useApiSettingsStore()
    expect(s.mode).toBe('separate')
    s.setMode('unified')
    expect(useApiSettingsStore().mode).toBe('unified')
    expect(JSON.parse(localStorage.getItem('kmatch-api-settings')).mode).toBe('unified')
  })

  it('applyUnified 把一份 unified 配置写到两端 (ai + agent)', async () => {
    const s = useApiSettingsStore()
    s.setMode('unified')
    s.setUnified({ provider: 'qwen', apiKey: 'sk-qwen', model: 'qwen3.5-plus' })
    await s.applyUnified()
    expect(aiMock.setProvider).toHaveBeenCalledWith('qwen')
    expect(aiMock.setApiKey).toHaveBeenCalledWith('sk-qwen')
    expect(aiMock.setModel).toHaveBeenCalledWith('qwen3.5-plus')
    expect(agMock.setUseOverrides).toHaveBeenCalledWith(true)
    expect(agMock.setProvider).toHaveBeenCalledWith('qwen')
    expect(agMock.setApiKey).toHaveBeenCalledWith('sk-qwen')
    expect(agMock.setModel).toHaveBeenCalledWith('qwen3.5-plus')
    // qwen 厂商自动带出默认 baseUrl
    expect(agMock.setBaseUrl).toHaveBeenCalledWith('https://dashscope.aliyuncs.com/compatible-mode/v1')
  })

  it('setUnified 选厂商自动带默认 baseUrl', () => {
    const s = useApiSettingsStore()
    s.setUnified({ provider: 'qwen', apiKey: 'k', model: 'm' })
    expect(s.unified.baseUrl).toBe('https://dashscope.aliyuncs.com/compatible-mode/v1')
  })

  it('testConnectivity 走到 /api/agents/ping (支持 protocol)', async () => {
    http.post.mockResolvedValue({ ok: true, content: 'pong' })   // 拦截器已解包, mock 直接给 body
    const s = useApiSettingsStore()
    const r = await s.testConnectivity({ apiKey: 'k', baseUrl: 'https://api.deepseek.com/v1', model: 'deepseek-v4-pro' })
    expect(http.post).toHaveBeenCalledWith('/api/agents/ping', {
      llm_overrides: { api_key: 'k', base_url: 'https://api.deepseek.com/v1', model: 'deepseek-v4-pro' },
      protocol: 'openai',
    })
    expect(r.ok).toBe(true)
    // anthropic 协议透传
    await s.testConnectivity({ apiKey: 'k', baseUrl: 'https://api.anthropic.com', model: 'claude-x', protocol: 'anthropic' })
    expect(http.post).toHaveBeenLastCalledWith('/api/agents/ping', {
      llm_overrides: { api_key: 'k', base_url: 'https://api.anthropic.com', model: 'claude-x' },
      protocol: 'anthropic',
    })
  })

  it('testConnectivity 失败返回真实 error (回归: 不再因解构 undefined 显示"未知错误")', async () => {
    http.post.mockResolvedValue({ ok: false, error: '401 Authorization Error: invalid api key' })
    const s = useApiSettingsStore()
    const r = await s.testConnectivity({ apiKey: 'bad', baseUrl: 'https://api.deepseek.com/v1', model: 'deepseek-v4-pro' })
    expect(r.ok).toBe(false)
    expect(r.error).toContain('401')  // 前端 onTest 会展示该真实原因
  })
})
