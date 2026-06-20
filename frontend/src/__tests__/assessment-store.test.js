/**
 * assessment store 单元测试
 *
 * 覆盖: startAssessment 成功/失败/reset、AbortController 管理
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

// Mock API — 在 store import 之前
vi.mock('@/api/diagnostics', () => ({
  submitAssessment: vi.fn(),
}))

import { useAssessmentStore } from '@/stores/assessment'
import { submitAssessment } from '@/api/diagnostics'

describe('useAssessmentStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  describe('初始状态', () => {
    it('所有状态应为 null/false/空', () => {
      const store = useAssessmentStore()
      expect(store.sessionId).toBeNull()
      expect(store.loading).toBe(false)
      expect(store.error).toBeNull()
      expect(store.profile).toBeNull()
      expect(store.assessment).toBeNull()
      expect(store.reviewResults).toBeNull()
      expect(store.orchestrationLog).toEqual([])
    })

    it('hasResults 为 false', () => {
      const store = useAssessmentStore()
      expect(store.hasResults).toBe(false)
    })
  })

  describe('startAssessment 成功', () => {
    const mockResponse = {
      session_id: 'sess-001',
      profile: { profile_id: 'P1', theory_level: 3 },
      assessment: { questions: [], answers: [], per_node: {}, correct_count: 5, total_count: 5 },
      review_results: { passed: true, overall_score: 0.9, threshold: 0.85, dimensions: {} },
      orchestration_log: ['[log] done'],
    }

    it('应正确填充所有 state', async () => {
      submitAssessment.mockResolvedValueOnce(mockResponse)

      const store = useAssessmentStore()
      await store.startAssessment({
        targetDirection: 'Python 基础',
        mode: 'demo',
      })

      expect(store.sessionId).toBe('sess-001')
      expect(store.profile).toEqual(mockResponse.profile)
      expect(store.assessment).toEqual(mockResponse.assessment)
      expect(store.reviewResults).toEqual(mockResponse.review_results)
      expect(store.orchestrationLog).toEqual(['[log] done'])
      expect(store.loading).toBe(false)
      expect(store.error).toBeNull()
      expect(store.hasResults).toBe(true)
      expect(store.reviewPassed).toBe(true)
      expect(store.accuracy).toBe(1.0)
    })

    it('loading 应在请求期间为 true，完成后为 false', async () => {
      let resolveOut
      const promise = new Promise((r) => { resolveOut = r })
      submitAssessment.mockReturnValueOnce(promise)

      const store = useAssessmentStore()
      const startPromise = store.startAssessment({ targetDirection: 'test' })

      expect(store.loading).toBe(true)

      resolveOut(mockResponse)
      await startPromise

      expect(store.loading).toBe(false)
    })
  })

  describe('startAssessment 失败', () => {
    it('应设置 error 并保持 loading=false', async () => {
      submitAssessment.mockRejectedValueOnce(new Error('网络错误'))

      const store = useAssessmentStore()
      await store.startAssessment({ targetDirection: 'test' })

      expect(store.error).toBe('网络错误')
      expect(store.loading).toBe(false)
      expect(store.sessionId).toBeNull()
    })

    it('CanceledError 应静默处理', async () => {
      const cancelError = new Error('cancel')
      cancelError.name = 'CanceledError'
      submitAssessment.mockRejectedValueOnce(cancelError)

      const store = useAssessmentStore()
      await store.startAssessment({ targetDirection: 'test' })

      expect(store.error).toBeNull()
      expect(store.loading).toBe(false)
    })
  })

  describe('reset', () => {
    it('应清空所有状态', async () => {
      submitAssessment.mockResolvedValueOnce({
        session_id: 'sess-001',
        profile: { profile_id: 'P1', theory_level: 3 },
        assessment: { questions: [], answers: [], per_node: {}, correct_count: 0, total_count: 0 },
        review_results: { passed: false, overall_score: 0, dimensions: {} },
        orchestration_log: [],
        knowledge_graph: { learning_path: [{ node_id: 'PY-001' }] },
        generated_content: { resources: [{ kind: 'lecture' }] },
      })

      const store = useAssessmentStore()
      await store.startAssessment({ targetDirection: 'test' })
      store.reset()

      expect(store.sessionId).toBeNull()
      expect(store.loading).toBe(false)
      expect(store.error).toBeNull()
      expect(store.profile).toBeNull()
      expect(store.assessment).toBeNull()
      expect(store.reviewResults).toBeNull()
      expect(store.orchestrationLog).toEqual([])
      // BUG-030: reset 应一并清空 W3/W4 字段
      expect(store.knowledgeGraph).toBeNull()
      expect(store.generatedContent).toBeNull()
    })
  })

  // BUG-028: 后端 LLM 未配置时返回 200 + profile={}，
  // 旧实现下 hasResults=false / error=null 致用户静默回退表单。
  describe('BUG-028 — 空画像降级处理', () => {
    it('profile={} + retry_hint 应把 retry_hint 写入 error', async () => {
      submitAssessment.mockResolvedValueOnce({
        session_id: 'sess-degraded',
        profile: {},
        assessment: { questions: [], answers: [], per_node: {}, correct_count: 0, total_count: 0 },
        review_results: {
          passed: false,
          overall_score: 0,
          retry_hint: '后端 LLM 未配置，无法产出画像',
          dimensions: {},
        },
        orchestration_log: [],
      })

      const store = useAssessmentStore()
      await store.startAssessment({ targetDirection: 'test' })

      expect(store.error).toBe('后端 LLM 未配置，无法产出画像')
      expect(store.profile).toBeNull()       // 显式清空避免 hasResults 误判
      expect(store.hasResults).toBe(false)
      expect(store.loading).toBe(false)
    })

    it('profile={} 且无 retry_hint 应回退到默认提示', async () => {
      submitAssessment.mockResolvedValueOnce({
        session_id: 'sess-degraded',
        profile: {},
        assessment: null,
        review_results: { passed: false, overall_score: 0, dimensions: {} },
        orchestration_log: [],
      })

      const store = useAssessmentStore()
      await store.startAssessment({ targetDirection: 'test' })

      expect(store.error).toMatch(/未产出有效画像/)
      expect(store.profile).toBeNull()
    })

    it('profile=null 也应触发空画像分支（防御）', async () => {
      submitAssessment.mockResolvedValueOnce({
        session_id: 'sess-x',
        profile: null,
        assessment: null,
        review_results: { retry_hint: 'null profile', dimensions: {} },
        orchestration_log: [],
      })

      const store = useAssessmentStore()
      await store.startAssessment({ targetDirection: 'test' })

      expect(store.error).toBe('null profile')
      expect(store.hasResults).toBe(false)
    })
  })

  // BUG-030: store 应映射 knowledge_graph / generated_content，供 W3 图谱页与 W4 资源页消费
  describe('BUG-030 — knowledge_graph / generated_content 字段映射', () => {
    it('成功响应应填充 knowledgeGraph + generatedContent', async () => {
      submitAssessment.mockResolvedValueOnce({
        session_id: 'sess-001',
        profile: { profile_id: 'P1', theory_level: 3 },
        assessment: { questions: [], answers: [], per_node: {}, correct_count: 1, total_count: 1 },
        review_results: { passed: true, overall_score: 0.9, dimensions: {} },
        orchestration_log: [],
        knowledge_graph: {
          learning_path: [{ node_id: 'PY-001' }, { node_id: 'PY-002' }],
          path_node_ids: ['PY-001', 'PY-002'],
          total_nodes: 2,
        },
        generated_content: {
          resources: [{ content_type: 'lecture', target_node_id: 'PY-001' }],
          node_count: 1,
        },
      })

      const store = useAssessmentStore()
      await store.startAssessment({ targetDirection: 'test' })

      expect(store.knowledgeGraph?.learning_path).toHaveLength(2)
      expect(store.generatedContent?.resources).toHaveLength(1)
    })

    it('响应缺这两个字段时应为 null（不抛错）', async () => {
      submitAssessment.mockResolvedValueOnce({
        session_id: 'sess-002',
        profile: { profile_id: 'P1', theory_level: 3 },
        assessment: { questions: [], answers: [], per_node: {}, correct_count: 1, total_count: 1 },
        review_results: { passed: true, overall_score: 0.9, dimensions: {} },
        orchestration_log: [],
        // knowledge_graph / generated_content 未提供
      })

      const store = useAssessmentStore()
      await store.startAssessment({ targetDirection: 'test' })

      expect(store.knowledgeGraph).toBeNull()
      expect(store.generatedContent).toBeNull()
    })
  })

  describe('计算属性', () => {
    it('knownNodeIds / weakNodeIds', () => {
      const store = useAssessmentStore()
      store.profile = {
        profile_id: 'P1',
        known_topics: [{ node_id: 'PY-001', mastery: 0.9 }],
        weak_topics: [{ node_id: 'PY-002', mastery: 0.2 }],
      }
      expect(store.knownNodeIds).toEqual(['PY-001'])
      expect(store.weakNodeIds).toEqual(['PY-002'])
    })

    it('hasResults: 空对象应为 false', () => {
      const store = useAssessmentStore()
      store.profile = {}
      expect(store.hasResults).toBe(false)
    })

    it('hasResults: null 应为 false', () => {
      const store = useAssessmentStore()
      store.profile = null
      expect(store.hasResults).toBe(false)
    })
  })
})
