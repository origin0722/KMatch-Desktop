/**
 * DataQualitySettings 单测 (数据与质量段: 语义检索/异源裁判/存储状态)
 *
 * 核心回归: @/api 响应拦截器已解包 (http.get/post 直接返回 body),
 * 组件曾用 `const { data } = await http...` 解构 → data undefined →
 * 保存后报 "Cannot read properties of undefined (reading 'embedding_applied')"。
 * mock 按真实契约返回「解包后的 body」。
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'

const httpGet = vi.fn()
const httpPost = vi.fn()
vi.mock('@/api', () => ({
  default: {
    get: (...args) => httpGet(...args),
    post: (...args) => httpPost(...args),
  },
}))

import DataQualitySettings from '@/ide/settings/DataQualitySettings.vue'

// 与后端 GET /api/settings/backend 的响应 body 同形 (拦截器解包后的形态)
const SETTINGS_BODY = {
  embedding: {
    configured: true, key_tail: '0640', base_url: 'https://dashscope.example/v1',
    model: 'text-embedding-v2', source: 'runtime',
  },
  judge: { enabled: false, source: 'unset', same_source: true, base_url: '', model: '', key_tail: '' },
  store: { kind: 'embedded', semantic_ready: true },
  data: { local_dir: 'C:/Users/x/appdata/local' },
}

describe('DataQualitySettings', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  const mountCard = () => mount(DataQualitySettings, {
    global: { plugins: [ElementPlus], stubs: ['el-icon'] },
  })

  it('load 按解包 body 正确填充: 状态就绪 / 来源本页配置 / 存储模式', async () => {
    httpGet.mockResolvedValue(SETTINGS_BODY)
    const w = mountCard()
    await flushPromises()
    expect(w.find('[data-test="emb-status"]').text()).toContain('就绪')
    expect(w.text()).toContain('本页配置')
    expect(w.find('[data-test="store-kind"]').text()).toContain('本地嵌入存储')
    expect(w.text()).toContain('C:/Users/x/appdata/local')
  })

  it('load body 缺段时不抛错 (防御 undefined)', async () => {
    httpGet.mockResolvedValue({ embedding: null, judge: null, store: null, data: null })
    const w = mountCard()
    await flushPromises()
    expect(w.find('[data-test="emb-status"]').text()).toContain('未配置')
  })

  it('saveEmbedding 读 embedding_applied 不解构 body (回归 TypeError), 探活失败透明展示', async () => {
    httpGet.mockResolvedValue(SETTINGS_BODY)
    httpPost.mockResolvedValue({ saved: true, embedding_applied: { ok: false, reason: '探活失败: 401' } })
    const w = mountCard()
    await flushPromises()
    await w.find('[data-test="emb-save"]').trigger('click')
    await flushPromises()
    expect(httpPost).toHaveBeenCalledWith('/api/settings/backend', expect.objectContaining({ embedding: expect.anything() }))
    expect(w.text()).toContain('已保存，但生效失败: 探活失败: 401')
  })

  it('saveEmbedding 探活成功 → 就绪提示', async () => {
    httpGet.mockResolvedValue(SETTINGS_BODY)
    httpPost.mockResolvedValue({ saved: true, embedding_applied: { ok: true, semantic_ready: true } })
    const w = mountCard()
    await flushPromises()
    await w.find('[data-test="emb-save"]').trigger('click')
    await flushPromises()
    expect(w.text()).toContain('已保存并生效')
  })

  it('saveEmbedding 后端返回空 body 时不抛错 (降级"已保存")', async () => {
    httpGet.mockResolvedValue(SETTINGS_BODY)
    httpPost.mockResolvedValue(null)
    const w = mountCard()
    await flushPromises()
    await w.find('[data-test="emb-save"]').trigger('click')
    await flushPromises()
    expect(w.text()).toContain('已保存')
  })
})
