/**
 * diagnostics API 单元测试
 *
 * 覆盖: submitAssessment / submitAnswers / requestFeedback 的请求体形态
 * 不验证 Axios 网络层，只验证我们封装的字段映射 (camelCase → snake_case) 与路径
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock http 实例 — 在 import 之前
vi.mock('@/api/index', () => ({
  default: {
    post: vi.fn(),
    get: vi.fn(),
  },
}))

import http from '@/api/index'
import {
  submitAssessment,
  submitAnswers,
  requestFeedback,
} from '@/api/diagnostics'

describe('api/diagnostics', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('submitAssessment', () => {
    it('应把 camelCase 映射为后端 snake_case', () => {
      http.post.mockResolvedValueOnce({})
      submitAssessment({
        targetDirection: 'Python 基础',
        mode: 'demo',
        knownTopics: [{ node_id: 'PY-001', mastery: 0.8 }],
        scene: 'no_project',
        maxRetries: 4,
      })

      expect(http.post).toHaveBeenCalledWith(
        '/api/diagnostics/assess',
        {
          target_direction: 'Python 基础',
          mode: 'demo',
          known_topics: [{ node_id: 'PY-001', mastery: 0.8 }],
          scene: 'no_project',
          max_retries: 4,
        },
        undefined,
      )
    })

    it('signal 应包进 axios config', () => {
      const ac = new AbortController()
      http.post.mockResolvedValueOnce({})
      submitAssessment({ targetDirection: 'x' }, ac.signal)
      expect(http.post.mock.calls[0][2]).toEqual({ signal: ac.signal })
    })

    it('未传 signal 时第三参为 undefined（不构造 {signal:undefined}）', () => {
      http.post.mockResolvedValueOnce({})
      submitAssessment({ targetDirection: 'x' })
      expect(http.post.mock.calls[0][2]).toBeUndefined()
    })
  })

  describe('submitAnswers (W5)', () => {
    it('打到 /api/diagnostics/submit，session_id 与 answers 直传', () => {
      http.post.mockResolvedValueOnce({})
      submitAnswers({ sessionId: 'sess-001', answers: ['A', 'B', 'C'] })

      expect(http.post).toHaveBeenCalledWith(
        '/api/diagnostics/submit',
        { session_id: 'sess-001', answers: ['A', 'B', 'C'] },
        undefined,
      )
    })

    it('signal 透传', () => {
      const ac = new AbortController()
      http.post.mockResolvedValueOnce({})
      submitAnswers({ sessionId: 's', answers: [] }, ac.signal)
      expect(http.post.mock.calls[0][2]).toEqual({ signal: ac.signal })
    })
  })

  describe('requestFeedback (W5)', () => {
    it('打到 /api/diagnostics/feedback，三字段全部直传', () => {
      http.post.mockResolvedValueOnce({})
      const profile = { profile_id: 'P1', theory_level: 3 }
      requestFeedback({
        sessionId: 'sess-001',
        strategy: 'remediate',
        profile,
      })

      expect(http.post).toHaveBeenCalledWith(
        '/api/diagnostics/feedback',
        {
          session_id: 'sess-001',
          strategy: 'remediate',
          profile,
        },
        undefined,
      )
    })

    it('strategy 三档值都允许（仅类型层面）', () => {
      http.post.mockResolvedValue({})
      for (const strategy of ['advance', 'remediate', 'scaffold']) {
        requestFeedback({ sessionId: 's', strategy, profile: {} })
      }
      expect(http.post).toHaveBeenCalledTimes(3)
    })
  })
})
