/**
 * diagnostics API 单元测试
 *
 * 覆盖: submitAssessment / submitAnswers / requestFeedback 的请求体形态
 * 不验证 Axios 网络层，只验证我们封装的字段映射 (camelCase → snake_case) 与路径
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

// Mock http 实例 — 在 import 之前
vi.mock('@/api/index', () => ({
  default: {
    post: vi.fn(),
    get: vi.fn(),
    put: vi.fn(),
  },
}))

import http from '@/api/index'
import {
  submitAssessment,
  submitAnswers,
  requestFeedback,
  fetchRun,
  fetchRuns,
  fetchWorkflows,
  fetchWorkflowEvaluate,
  saveWorkflowDraft,
  commitWorkflow,
  fetchWorkflowRevisions,
  restoreWorkflowRevision,
} from '@/api/diagnostics'

describe('api/diagnostics', () => {
  beforeEach(() => {
    // Spec B: diagnostics API 经 withOverrides -> useAgentLlmStore(), 需活跃 Pinia
    setActivePinia(createPinia())
    localStorage.clear()
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

    it('interactive 模式放宽 timeout 至 300s (动态建域) 且透传 tavily_key', () => {
      http.post.mockResolvedValueOnce({})
      submitAssessment({ targetDirection: 'Java 入门', mode: 'interactive', tavilyKey: 'tvly-x' })
      expect(http.post.mock.calls[0][2]).toEqual({ timeout: 300_000 })
      expect(http.post.mock.calls[0][1]).toMatchObject({
        mode: 'interactive',
        tavily_key: 'tvly-x',
      })
    })

    it('demo 模式不放宽 timeout (SSE 流式另有通道)', () => {
      http.post.mockResolvedValueOnce({})
      submitAssessment({ targetDirection: 'x', mode: 'demo' })
      expect(http.post.mock.calls[0][2]).toBeUndefined()
    })
  })

  describe('submitAnswers (W5)', () => {
    it('打到 /api/diagnostics/submit，session_id 与 answers 直传 + 判分超时放宽 300s', () => {
      http.post.mockResolvedValueOnce({})
      submitAnswers({ sessionId: 'sess-001', answers: ['A', 'B', 'C'] })

      expect(http.post).toHaveBeenCalledWith(
        '/api/diagnostics/submit',
        { session_id: 'sess-001', answers: ['A', 'B', 'C'] },
        { timeout: 300_000 },
      )
    })

    it('signal 透传 (与 timeout 一并传入)', () => {
      const ac = new AbortController()
      http.post.mockResolvedValueOnce({})
      submitAnswers({ sessionId: 's', answers: [] }, ac.signal)
      expect(http.post.mock.calls[0][2]).toEqual({ timeout: 300_000, signal: ac.signal })
    })

    it('传 learnerKey → body 带 learner_key (画像跨次进化)', () => {
      http.post.mockResolvedValueOnce({})
      submitAnswers({ sessionId: 's', answers: [], learnerKey: 'learner-abc' })
      // withOverrides 未开时 body 原样透传
      expect(http.post).toHaveBeenCalledWith(
        '/api/diagnostics/submit',
        { session_id: 's', answers: [], learner_key: 'learner-abc' },
        { timeout: 300_000 },
      )
    })
  })

  describe('requestFeedback (W5)', () => {
    it('打到 /api/diagnostics/feedback，三字段直传 + 默认反馈快模型 (deepseek-v4-flash)', () => {
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
          // 反馈快模型: 独立配置关时部分覆写仅 model, key/baseUrl 走后端 .env
          llm_overrides: { model: 'deepseek-v4-flash' },
        },
        // #30 反馈: timeout 330s (须大于后端 300s 硬上限; 后端再生 270s 截止有界收集, 防整单取消)
        { signal: undefined, timeout: 330_000 },
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

  describe('Phase 1/2 run 与 workflow API', () => {
    it('fetchRun 打到 /api/diagnostics/runs/{sid} 且 path 编码', async () => {
      http.get.mockResolvedValueOnce({ session_id: 'sid-1' })   // 拦截器已解包, mock 直接给 body
      const run = await fetchRun('sid-1')
      expect(http.get).toHaveBeenCalledWith('/api/diagnostics/runs/sid-1')
      expect(run.session_id).toBe('sid-1')
    })

    it('fetchRun 对带斜杠的 sid 做 encodeURIComponent', async () => {
      http.get.mockResolvedValueOnce({})
      await fetchRun('a/b')
      expect(http.get).toHaveBeenCalledWith('/api/diagnostics/runs/a%2Fb')
    })

    it('fetchRuns 带 limit 参数', async () => {
      http.get.mockResolvedValueOnce({ count: 2, runs: [] })
      const res = await fetchRuns(5)
      expect(http.get).toHaveBeenCalledWith('/api/diagnostics/runs', { params: { limit: 5 } })
      expect(res.count).toBe(2)
    })

    it('fetchWorkflows 打到 /api/diagnostics/workflows', async () => {
      http.get.mockResolvedValueOnce({ workflows: [{ id: 'scene1-loop' }] })
      const res = await fetchWorkflows()
      expect(http.get).toHaveBeenCalledWith('/api/diagnostics/workflows')
      expect(res.workflows[0].id).toBe('scene1-loop')
    })

    it('fetchWorkflowEvaluate 打到 /workflows/evaluate (Phase 4 确定性求值)', async () => {
      http.post.mockResolvedValueOnce({ ok: true, decisions: [{ id: 'strategy', label: '反馈策略', chosen: 'advance' }] })
      const res = await fetchWorkflowEvaluate('scene1-loop', { correct_ratio: 0.9 })
      expect(http.post).toHaveBeenCalledWith('/api/diagnostics/workflows/evaluate', {
        workflow_id: 'scene1-loop',
        context: { correct_ratio: 0.9 },
      })
      expect(res.decisions[0].chosen).toBe('advance')
    })

    it('Phase 3b 事务: 草稿/提交/版本/回滚路径与 body 形态', async () => {
      const def = { format: 'kmatch.workflow', version: 1, id: 'my-flow', stages: [] }
      http.put.mockResolvedValueOnce({ ok: true, valid: true, warnings: [] })
      await saveWorkflowDraft('my-flow', def)
      expect(http.put).toHaveBeenCalledWith('/api/diagnostics/workflows/my-flow/draft', { definition: def })

      http.post.mockResolvedValueOnce({ id: 'my-flow', revision: 'R1' })
      await commitWorkflow('my-flow', def, { note: 'n', reviewedBy: 'me' })
      expect(http.post).toHaveBeenCalledWith('/api/diagnostics/workflows/my-flow/commit', {
        definition: def, note: 'n', reviewed_by: 'me',
      })

      http.get.mockResolvedValueOnce({ workflow_id: 'my-flow', revisions: [] })
      await fetchWorkflowRevisions('my-flow')
      expect(http.get).toHaveBeenCalledWith('/api/diagnostics/workflows/my-flow/revisions')

      http.post.mockResolvedValueOnce({ id: 'my-flow', restored: 'R1' })
      await restoreWorkflowRevision('my-flow', 'R1')
      expect(http.post).toHaveBeenCalledWith('/api/diagnostics/workflows/my-flow/restore', { revision: 'R1' })
    })
  })
})
