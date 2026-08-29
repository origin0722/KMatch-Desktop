/**
 * assessment store 单元测试
 *
 * S9 更新: startAssessment 改为 interactive 出题阶段 (不再直接返回完整 profile)。
 *   - interactive: assess → questions → phase='answering' → submit → phase='feedback'
 *   - demo: startDemoStream → 完整结果 (_applyResult 填充 profile/kg/gen/learningReport)
 *
 * 覆盖: interactive 出题/空题降级、demo 完整结果映射、reset、AbortController、计算属性
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

// Mock API — 在 store import之前
vi.mock('@/api/diagnostics', () => ({
  submitAssessment: vi.fn(),
  startAssessmentStream: vi.fn(),
  submitAnswers: vi.fn(),
  requestFeedback: vi.fn(),
  fetchRun: vi.fn(),
}))

import { useAssessmentStore } from '@/stores/assessment'
import { submitAssessment, startAssessmentStream, submitAnswers, requestFeedback, fetchRun } from '@/api/diagnostics'

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
      expect(store.phase).toBe('idle')
    })

    it('hasResults 为 false', () => {
      const store = useAssessmentStore()
      expect(store.hasResults).toBe(false)
    })
  })

  // ============================================================
  // interactive 出题阶段 (S9)
  // ============================================================
  describe('startAssessment (interactive 出题)', () => {
    it('应进入答题阶段, 缓存题目 + 初始化空答案', async () => {
      submitAssessment.mockResolvedValueOnce({
        session_id: 'sess-001',
        assessment: {
          questions: [
            { type: 'choice', question: 'Q1', options: ['A. x', 'B. y'] },
            { type: 'fill', question: 'Q2' },
          ],
          answers: [],
          per_node: {},
          correct_count: 0,
          total_count: 2,
        },
      })

      const store = useAssessmentStore()
      await store.startAssessment({ targetDirection: 'Python 基础' })

      expect(store.sessionId).toBe('sess-001')
      expect(store.phase).toBe('answering')
      expect(store.pendingQuestions).toHaveLength(2)
      expect(store.userAnswers).toEqual(['', ''])
      expect(store.loading).toBe(false)
      expect(store.error).toBeNull()
      // interactive 出题阶段不应有 profile (避免 hasResults 误判)
      expect(store.profile).toBeNull()
      expect(store.hasResults).toBe(false)
    })

    it('loading 应在请求期间为 true，完成后为 false', async () => {
      let resolveOut
      const promise = new Promise((r) => { resolveOut = r })
      submitAssessment.mockReturnValueOnce(promise)

      const store = useAssessmentStore()
      const startPromise = store.startAssessment({ targetDirection: 'test' })

      expect(store.loading).toBe(true)

      resolveOut({ session_id: 's', assessment: { questions: [{ type: 'choice', question: 'q', options: [] }] } })
      await startPromise

      expect(store.loading).toBe(false)
    })

    it('空题目 → 出题失败错误', async () => {
      submitAssessment.mockResolvedValueOnce({
        session_id: 'sess-empty',
        assessment: { questions: [], answers: [], per_node: {}, correct_count: 0, total_count: 0 },
      })

      const store = useAssessmentStore()
      await store.startAssessment({ targetDirection: 'test' })

      expect(store.error).toMatch(/未获得测评题目/)
      expect(store.phase).toBe('idle')
      expect(store.pendingQuestions).toEqual([])
    })

    it('请求失败应设置 error', async () => {
      submitAssessment.mockRejectedValueOnce(new Error('网络错误'))

      const store = useAssessmentStore()
      await store.startAssessment({ targetDirection: 'test' })

      expect(store.error).toBe('网络错误')
      expect(store.loading).toBe(false)
      expect(store.phase).toBe('idle')
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

  // ============================================================
  // interactive 第二步: submitAssessmentAnswers (S9)
  // ============================================================
  describe('submitAssessmentAnswers (判分+反馈策略)', () => {
    it('应填充 profile + assessment + feedbackStrategy, 进入反馈阶段', async () => {
      // 先出题进入 answering
      submitAssessment.mockResolvedValueOnce({
        session_id: 'sess-q',
        assessment: { questions: [{ type: 'choice', question: 'q', options: [] }], total_count: 1 },
      })
      submitAnswers.mockResolvedValueOnce({
        session_id: 'sess-q',
        profile: { profile_id: 'P1', theory_level: 3 },
        assessment: { correct_count: 1, total_count: 1, per_node: {} },
        review_results: { passed: true, dimensions: {} },
        feedback: { strategy: 'advance' },
      })

      const store = useAssessmentStore()
      await store.startAssessment({ targetDirection: 'test' })
      await store.submitAssessmentAnswers()

      expect(store.phase).toBe('feedback')
      expect(store.profile).toEqual({ profile_id: 'P1', theory_level: 3 })
      expect(store.feedbackStrategy).toBe('advance')
      expect(store.accuracy).toBe(1.0)
    })
  })

  // ============================================================
  // interactive 第三步: fetchFeedback (动态反馈再生, S9)
  // ============================================================
  describe('fetchFeedback (动态反馈再生)', () => {
    it('应填充 feedbackContent', async () => {
      submitAssessment.mockResolvedValueOnce({
        session_id: 's',
        assessment: { questions: [{ type: 'choice', question: 'q', options: [] }] },
      })
      submitAnswers.mockResolvedValueOnce({
        session_id: 's', profile: { profile_id: 'P' }, assessment: { correct_count: 0, total_count: 1 },
        review_results: {}, feedback: { strategy: 'scaffold' },
      })
      requestFeedback.mockResolvedValueOnce({
        session_id: 's', strategy: 'scaffold', resources: [{ content_type: 'lecture', content: '# x' }], node_count: 1,
      })

      const store = useAssessmentStore()
      await store.startAssessment({ targetDirection: 't' })
      await store.submitAssessmentAnswers()
      await store.fetchFeedback()

      expect(store.feedbackContent?.resources).toHaveLength(1)
      expect(store.feedbackContent?.strategy).toBe('scaffold')
    })

    // #30 后续: 反馈产物不再只在答题卡原位置展示, 知识点 → generatedContent (学习资源讲义 tab),
    // 网址 → learningResources (联网资源 tab), 并自动打开右侧学习资源分屏
    it('反馈产物应落入「学习资源」(知识点 + 网址) 并自动打开分屏', async () => {
      submitAssessment.mockResolvedValueOnce({
        session_id: 's',
        assessment: { questions: [{ type: 'choice', question: 'q', options: [] }] },
      })
      submitAnswers.mockResolvedValueOnce({
        session_id: 's', profile: { profile_id: 'P' }, assessment: { correct_count: 0, total_count: 1 },
        review_results: {}, feedback: { strategy: 'remediate' },
      })
      requestFeedback.mockResolvedValueOnce({
        session_id: 's', strategy: 'remediate', node_count: 2,
        resources: [
          { content_type: 'lecture', content: '# 降维讲义' },
          { content_type: 'web_link', title: '教程', url: 'https://a.b/c', content: '摘要' },
        ],
      })

      const store = useAssessmentStore()
      await store.startAssessment({ targetDirection: 't' })
      await store.submitAssessmentAnswers()
      await store.fetchFeedback()

      // 知识点 → generatedContent (学习资源 讲义/实操/测试 tab)
      expect(store.generatedContent?.resources).toHaveLength(1)
      expect(store.generatedContent?.resources[0].content_type).toBe('lecture')
      expect(store.generatedContent?.node_count).toBe(2)
      // 网址 → learningResources (联网资源 tab)
      const { useLearningResourcesStore } = await import('@/stores/learningResources')
      const lr = useLearningResourcesStore()
      expect(lr.webResources).toHaveLength(1)
      expect(lr.webResources[0].url).toBe('https://a.b/c')
      // 自动打开学习资源分屏
      const { useSessionStore } = await import('@/stores/session')
      expect(useSessionStore().splitView).toBe('learning')
    })

    // W1 失败透明化: generation_failures 随产物合并落库 (内容为空但有失败时也写入)
    it('generation_failures 应合并进 generatedContent (空产物也落库)', async () => {
      submitAssessment.mockResolvedValueOnce({
        session_id: 's',
        assessment: { questions: [{ type: 'choice', question: 'q', options: [] }] },
      })
      submitAnswers.mockResolvedValueOnce({
        session_id: 's', profile: { profile_id: 'P' }, assessment: { correct_count: 0, total_count: 1 },
        review_results: {}, feedback: { strategy: 'scaffold' },
      })
      requestFeedback.mockResolvedValueOnce({
        session_id: 's', strategy: 'scaffold', node_count: 1, resources: [],
        generation_failures: [{ node_id: 'PY-005', content_type: 'lecture', reason: 'LLM 调用失败（网络/限流/响应格式）' }],
      })

      const store = useAssessmentStore()
      await store.startAssessment({ targetDirection: 't' })
      await store.submitAssessmentAnswers()
      await store.fetchFeedback()

      expect(store.generatedContent?.resources).toHaveLength(0)
      expect(store.generatedContent?.generation_failures).toHaveLength(1)
      expect(store.generatedContent?.generation_failures[0].node_id).toBe('PY-005')
    })

    it('无资源时不打开学习资源分屏', async () => {
      submitAssessment.mockResolvedValueOnce({
        session_id: 's',
        assessment: { questions: [{ type: 'choice', question: 'q', options: [] }] },
      })
      submitAnswers.mockResolvedValueOnce({
        session_id: 's', profile: { profile_id: 'P' }, assessment: { correct_count: 0, total_count: 1 },
        review_results: {}, feedback: { strategy: 'advance' },
      })
      requestFeedback.mockResolvedValueOnce({
        session_id: 's', strategy: 'advance', resources: [], node_count: 0,
      })

      const store = useAssessmentStore()
      await store.startAssessment({ targetDirection: 't' })
      await store.submitAssessmentAnswers()
      await store.fetchFeedback()

      const { useSessionStore } = await import('@/stores/session')
      expect(useSessionStore().splitView).toBeNull()
    })

    // W5 三维测评: submit 载荷携带 VARK 问卷答案 + 实操证据
    it('submitAnswers 载荷应携带 learning_style_quiz 与 practical_evidence', async () => {
      submitAssessment.mockResolvedValueOnce({
        session_id: 's',
        assessment: { questions: [{ type: 'choice', question: 'q', options: [] }] },
      })
      submitAnswers.mockResolvedValueOnce({
        session_id: 's', profile: { profile_id: 'P' }, assessment: { correct_count: 1, total_count: 1 },
        review_results: {}, feedback: { strategy: 'advance' },
      })
      const { useProjectGraphStore } = await import('@/stores/projectGraph')
      useProjectGraphStore().setLastTestReport({ passed: 9, total: 10 })

      const store = useAssessmentStore()
      await store.startAssessment({ targetDirection: 't' })
      store.styleQuiz = ['v', 'v', 'r', 'k', 'a']
      await store.submitAssessmentAnswers()

      const payload = submitAnswers.mock.calls[0][0]
      expect(payload.learningStyleQuiz).toEqual(['v', 'v', 'r', 'k', 'a'])
      expect(payload.practicalEvidence).toEqual({ tests_passed: 9, tests_total: 10 })
    })

    it('无问卷/无证据时 submitAnswers 载荷为空数组与 null (后端按占位处理)', async () => {
      submitAssessment.mockResolvedValueOnce({
        session_id: 's',
        assessment: { questions: [{ type: 'choice', question: 'q', options: [] }] },
      })
      submitAnswers.mockResolvedValueOnce({
        session_id: 's', profile: { profile_id: 'P' }, assessment: { correct_count: 0, total_count: 1 },
        review_results: {}, feedback: { strategy: 'scaffold' },
      })
      const store = useAssessmentStore()
      await store.startAssessment({ targetDirection: 't' })
      await store.submitAssessmentAnswers()

      const payload = submitAnswers.mock.calls[0][0]
      expect(payload.learningStyleQuiz).toEqual([])
      expect(payload.practicalEvidence).toBeNull()
    })

    it('submit 失败 → 记录 error、phase 保持 answering、loading 复位 (判分卡死自愈)', async () => {
      submitAssessment.mockResolvedValueOnce({
        session_id: 's', assessment: { questions: [{ type: 'choice', question: 'q', options: [] }] },
      })
      submitAnswers.mockRejectedValueOnce({
        response: { data: { detail: '判分失败: LLM 调用失败: 401' } },
      })
      const store = useAssessmentStore()
      await store.startAssessment({ targetDirection: 't' })
      await store.submitAssessmentAnswers()
      expect(store.error).toContain('判分失败')
      expect(store.phase).toBe('answering')   // 不切阶段, 题目与错误条可见, 可重试
      expect(store.loading).toBe(false)
    })
  })

  // ============================================================
  // demo 完整结果 (startDemoStream → _applyResult, S8 含 learningReport)
  // ============================================================
  describe('startDemoStream (demo 完整结果)', () => {
    const mockResult = {
      session_id: 'sess-demo',
      profile: { profile_id: 'P1', theory_level: 3 },
      assessment: { questions: [], correct_count: 5, total_count: 5 },
      review_results: { passed: true, overall_score: 0.9, dimensions: {} },
      orchestration_log: ['[log] done'],
      knowledge_graph: { learning_path: [{ node_id: 'PY-001' }, { node_id: 'PY-002' }] },
      generated_content: { resources: [{ content_type: 'lecture', target_node_id: 'PY-001' }], node_count: 1 },
      learning_report: {
        // 契约键对齐后端 compute_quality_metrics (issue-03): *_{hallucination,adaptation,coverage}_rate 各为 {rate,...}
        quality_metrics: { hallucination_rate: { rate: 0.02 }, adaptation_rate: { rate: 0.9 }, coverage_rate: { rate: 0.95 }, all_passed: true },
      },
    }

    it('应映射所有字段 (含 learningReport, S8)', async () => {
      startAssessmentStream.mockImplementationOnce((_req, cbs) => {
        cbs.onDone(mockResult)
      })

      const store = useAssessmentStore()
      await store.startDemoStream({ targetDirection: 'test' })

      expect(store.sessionId).toBe('sess-demo')
      expect(store.profile).toEqual(mockResult.profile)
      expect(store.knowledgeGraph?.learning_path).toHaveLength(2)
      expect(store.generatedContent?.resources).toHaveLength(1)
      expect(store.learningReport?.quality_metrics.hallucination_rate.rate).toBe(0.02)
      expect(store.hasResults).toBe(true)
      expect(store.reviewPassed).toBe(true)
    })

    it('SSE 错误应设置 error', async () => {
      startAssessmentStream.mockImplementationOnce((_req, cbs) => {
        cbs.onError('后端连接失败')
      })

      const store = useAssessmentStore()
      await store.startDemoStream({ targetDirection: 'test' })

      expect(store.error).toBe('后端连接失败')
      expect(store.loading).toBe(false)
    })
  })

  describe('reset', () => {
    it('应清空所有状态 (含 interactive 阶段 + learningReport)', async () => {
      submitAssessment.mockResolvedValueOnce({
        session_id: 's',
        assessment: { questions: [{ type: 'choice', question: 'q', options: [] }] },
      })

      const store = useAssessmentStore()
      await store.startAssessment({ targetDirection: 'test' })
      store.learningReport = { some: 'report' }
      store.reset()

      expect(store.sessionId).toBeNull()
      expect(store.loading).toBe(false)
      expect(store.error).toBeNull()
      expect(store.profile).toBeNull()
      expect(store.assessment).toBeNull()
      expect(store.reviewResults).toBeNull()
      expect(store.orchestrationLog).toEqual([])
      expect(store.knowledgeGraph).toBeNull()
      expect(store.generatedContent).toBeNull()
      expect(store.learningReport).toBeNull()
      expect(store.phase).toBe('idle')
      expect(store.pendingQuestions).toEqual([])
      // issue-65: 重置时目标方向一并清空
      expect(store.pendingTargetDirection).toBe('')
    })
  })

  describe('pendingTargetDirection (issue-65: 目标跨视图持久化)', () => {
    it('startAssessment 记录目标; 切视图后仍在 (模拟不 reset 场景)', async () => {
      submitAssessment.mockResolvedValueOnce({
        session_id: 's2',
        assessment: { questions: [{ type: 'choice', question: 'q', options: [] }] },
      })
      const store = useAssessmentStore()
      await store.startAssessment({ targetDirection: '我的自定义领域' })
      expect(store.pendingTargetDirection).toBe('我的自定义领域')
      // 不 reset (用户只是切走再回来), 目标保留
      expect(store.pendingTargetDirection).toBe('我的自定义领域')
    })

    it('startAssessment 失败时目标仍保留 (stage 可显示重试目标)', async () => {
      submitAssessment.mockRejectedValueOnce(new Error('boom'))
      const store = useAssessmentStore()
      await store.startAssessment({ targetDirection: '机器学习入门' })
      expect(store.pendingTargetDirection).toBe('机器学习入门')
      expect(store.phase).toBe('idle')
      expect(store.error).toBeTruthy()
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
