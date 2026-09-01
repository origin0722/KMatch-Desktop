/**
 * 画像字段真实化 (v1.3.0) 单元测试
 *
 * 覆盖:
 *  - isDemographicsFilled 纯函数 (学习背景是否含任一已填字段, 决定是否上送)
 *  - submitAnswers 映射 time_per_week / preferred_pace / 扩展 demographics (0/空 → undefined)
 *  - 设置页「学习画像」API 路径: fetchProfile / updateProfile / deleteProfile
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/api/index', () => ({
  default: { post: vi.fn(), get: vi.fn(), put: vi.fn(), delete: vi.fn() },
}))

import http from '@/api/index'
import {
  submitAnswers,
  isDemographicsFilled,
  fetchProfile,
  updateProfile,
  deleteProfile,
} from '@/api/diagnostics'

describe('isDemographicsFilled (纯函数)', () => {
  it('全空 → false (不上送)', () => {
    expect(isDemographicsFilled(null)).toBe(false)
    expect(isDemographicsFilled({})).toBe(false)
    expect(isDemographicsFilled({ education: '', major: '', age_range: '', programming_experience_months: null, python_experience_months: null })).toBe(false)
  })

  it('任一字段非空 → true', () => {
    expect(isDemographicsFilled({ education: '本科' })).toBe(true)
    expect(isDemographicsFilled({ age_range: '26-35' })).toBe(true)
    expect(isDemographicsFilled({ programming_experience_months: 24 })).toBe(true)
    expect(isDemographicsFilled({ education: '', programming_experience_months: 0 })).toBe(false)
  })
})

describe('submitAnswers 画像字段真实化', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('时间/节奏无效 (0/空) → body 不带 time_per_week / preferred_pace (未提交新字段行为兼容)', () => {
    http.post.mockResolvedValueOnce({})
    submitAnswers({ sessionId: 's', answers: [] })
    expect(http.post).toHaveBeenCalledWith(
      '/api/diagnostics/submit',
      { session_id: 's', answers: [] },
      { timeout: 300_000 },
    )
  })

  it('有效时间/节奏 → body 带 time_per_week / preferred_pace', () => {
    http.post.mockResolvedValueOnce({})
    submitAnswers({ sessionId: 's', answers: [], timePerWeek: 12, preferredPace: 'fast' })
    expect(http.post.mock.calls[0][1]).toMatchObject({
      time_per_week: 12,
      preferred_pace: 'fast',
    })
  })

  it('扩展 demographics 含任一字段 → 上送', () => {
    http.post.mockResolvedValueOnce({})
    const demographics = { education: '本科', age_range: '18-25', programming_experience_months: 24 }
    submitAnswers({ sessionId: 's', answers: [], demographics })
    expect(http.post.mock.calls[0][1]).toMatchObject({ demographics })
  })

  it('扩展 demographics 全空 → 不上送 (undefined 键被忽略)', () => {
    http.post.mockResolvedValueOnce({})
    submitAnswers({ sessionId: 's', answers: [], demographics: { education: '', major: '', age_range: '', programming_experience_months: null, python_experience_months: null } })
    expect(http.post.mock.calls[0][1]).toEqual({ session_id: 's', answers: [] })
  })
})

describe('设置页「学习画像」API', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('fetchProfile 打到 GET /profile/{key}', async () => {
    http.get.mockResolvedValueOnce({ learner_key: 'learner-1', profile: { theory_level: 3 }, history: [] })
    const res = await fetchProfile('learner-1')
    expect(http.get).toHaveBeenCalledWith('/api/diagnostics/profile/learner-1')
    expect(res.profile.theory_level).toBe(3)
  })

  it('fetchProfile 对带特殊字符的 key 编码', async () => {
    http.get.mockResolvedValueOnce({})
    await fetchProfile('learner/abc')
    expect(http.get).toHaveBeenCalledWith('/api/diagnostics/profile/learner%2Fabc')
  })

  it('updateProfile 打到 PUT /profile/{key} 且 payload 直传', async () => {
    http.put.mockResolvedValueOnce({ preferred_pace: 'fast' })
    const res = await updateProfile('learner-1', { preferred_pace: 'fast', time_per_week: 10 })
    expect(http.put).toHaveBeenCalledWith('/api/diagnostics/profile/learner-1', { preferred_pace: 'fast', time_per_week: 10 })
    expect(res.preferred_pace).toBe('fast')
  })

  it('deleteProfile 打到 DELETE /profile/{key}', async () => {
    http.delete.mockResolvedValueOnce({ learner_key: 'learner-1', deleted: true })
    const res = await deleteProfile('learner-1')
    expect(http.delete).toHaveBeenCalledWith('/api/diagnostics/profile/learner-1')
    expect(res.deleted).toBe(true)
  })
})
