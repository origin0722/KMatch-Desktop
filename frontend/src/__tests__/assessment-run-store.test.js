/**
 * assessment store — Phase 1 持久 run (复盘/续跑)
 *
 * 覆盖:
 *   - loadRun: fetchRun 回灌 orchestrationEvents/orchestrationLog + 填 lastRun/sessionId
 *   - loadRun 404 → null 且不清已有状态
 *   - startDemoStream 记录 lastRun 请求 meta, done 后填 sessionId
 *   - resumeRunDemo: 用 lastRun.request 一键重跑 (仅 demo); 非 demo/无 request → null
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('@/api/diagnostics', () => ({
  submitAssessment: vi.fn(),
  startAssessmentStream: vi.fn(),
  submitAnswers: vi.fn(),
  requestFeedback: vi.fn(),
  fetchRun: vi.fn(),
}))

import { useAssessmentStore } from '@/stores/assessment'
import { startAssessmentStream, fetchRun } from '@/api/diagnostics'

const SAMPLE_RUN = {
  session_id: 'sid-persisted-1',
  mode: 'demo',
  request: { target_direction: 'Python 进阶', scene: 'no_project', max_retries: 3 },
  summary: { path_nodes: 7, review_passed: true },
  orchestration_events: [
    { type: 'agent-start', agent: 'diagnostics', status: 'running', message: '学情检测: 开始', log: '[ts] 🔧 学情检测: 开始' },
    { type: 'agent-end', agent: 'diagnostics', status: 'done', message: '学情检测: 判分 8/10', log: '[ts] 🔧 学情检测: 判分 8/10' },
  ],
  orchestration_log: ['[ts] 🔧 学情检测: 开始', '[ts] 🔧 学情检测: 判分 8/10'],
}

describe('assessment store — Phase 1 持久 run', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('loadRun 回灌事件/日志并填充 lastRun + sessionId', async () => {
    fetchRun.mockResolvedValue(SAMPLE_RUN)
    const store = useAssessmentStore()
    const data = await store.loadRun('sid-persisted-1')
    expect(data).toEqual(SAMPLE_RUN)
    expect(fetchRun).toHaveBeenCalledWith('sid-persisted-1')
    expect(store.orchestrationEvents).toHaveLength(2)
    expect(store.orchestrationLog).toHaveLength(2)
    expect(store.sessionId).toBe('sid-persisted-1')
    expect(store.lastRun.mode).toBe('demo')
    expect(store.lastRun.request.target_direction).toBe('Python 进阶')
    expect(store.lastRun.summary.path_nodes).toBe(7)
  })

  it('loadRun 404 → 返回 null, 不清已有状态', async () => {
    fetchRun.mockRejectedValue({ response: { status: 404 } })
    const store = useAssessmentStore()
    store.orchestrationLog = ['[ts] 已有日志']
    const data = await store.loadRun('missing')
    expect(data).toBeNull()
    expect(store.orchestrationLog).toEqual(['[ts] 已有日志'])
    expect(store.lastRun).toBeNull()
  })

  it('loadRun 非 404 错误上抛', async () => {
    fetchRun.mockRejectedValue(new Error('网络错误'))
    const store = useAssessmentStore()
    await expect(store.loadRun('x')).rejects.toThrow('网络错误')
  })

  it('startDemoStream 记录 lastRun 请求 meta, done 后填 sessionId', async () => {
    const cbsCapture = {}
    startAssessmentStream.mockImplementation((payload, cbs) => {
      cbsCapture.cbs = cbs
      return Promise.resolve()
    })
    const store = useAssessmentStore()
    await store.startDemoStream({ targetDirection: '机器学习', scene: 'with_project' })
    expect(store.lastRun.mode).toBe('demo')
    expect(store.lastRun.request.target_direction).toBe('机器学习')
    expect(store.lastRun.request.scene).toBe('with_project')
    // 触发 done
    cbsCapture.cbs.onDone({
      session_id: 'sid-new',
      orchestration_events: SAMPLE_RUN.orchestration_events,
      orchestration_log: SAMPLE_RUN.orchestration_log,
      profile: {}, review_results: {}, assessment: {}, knowledge_graph: {},
      generated_content: {}, learning_report: {},
    })
    expect(store.lastRun.sessionId).toBe('sid-new')
    expect(store.sessionId).toBe('sid-new')
  })

  it('resumeRunDemo 用 lastRun.request 重跑 (仅 demo)', async () => {
    startAssessmentStream.mockResolvedValue()
    const store = useAssessmentStore()
    fetchRun.mockResolvedValue(SAMPLE_RUN)
    await store.loadRun('sid-persisted-1')
    await store.resumeRunDemo()
    expect(startAssessmentStream).toHaveBeenCalledTimes(1)
    const [payload] = startAssessmentStream.mock.calls[0]
    expect(payload.targetDirection).toBe('Python 进阶')
    expect(payload.scene).toBe('no_project')
  })

  it('resumeRunDemo 非 demo run → 返回 null 不重跑', async () => {
    startAssessmentStream.mockResolvedValue()
    const store = useAssessmentStore()
    const r = await store.resumeRunDemo() // 无 lastRun
    expect(r).toBeNull()
    expect(startAssessmentStream).not.toHaveBeenCalled()
  })
})
