/**
 * postSseJson IPC 传输层回归 (v1.3.4 热修)
 *
 * 缺陷: 提交/反馈载荷携带 Vue 深层响应式代理 (styleQuiz/demographics/profile 的 .value),
 * ipcRenderer.invoke 走结构化克隆不能拷贝 Proxy → "An object could not be cloned.",
 * 桌面端提交答题全挂。修复: postSseJson 入口 JSON round-trip 转纯对象。
 * 本测试用真实 reactive() + structuredClone 钉住该边界 (mock IPC 捕获实际过桥的 body)。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { reactive } from 'vue'
import { postSseJson } from '@/api/diagnostics'

describe('postSseJson — IPC 载荷可结构化克隆 (v1.3.4 热修回归)', () => {
  let captured
  let cleanup

  beforeEach(() => {
    captured = null
    let reqId = null
    // 模拟 Electron IPC SSE 通道: 捕获过桥 body 与 reqId; 数据 done 经 onChunk 的 SSE block
    // 派发 (对齐真实流: 块数据走 chunk, 传输层 onDone 仅收尾清理)
    const http = {
      stream: vi.fn(async (_url, body, rid) => { captured = body; reqId = rid }),
      onChunk: vi.fn((cb) => {
        setTimeout(() => cb(reqId, 'event: done\ndata: {"ok":true}'), 0)
        return () => {}
      }),
      onDone: vi.fn(() => () => {}),
      onError: vi.fn(() => () => {}),
    }
    window.api = { http }
    cleanup = () => { delete window.api }
  })
  afterEach(() => cleanup?.())

  it('响应式代理载荷经 round-trip 后可过 structuredClone (提交答题场景)', async () => {
    const styleQuiz = reactive(['A', 'B'])            // ref([]).value 即此形状
    const demographics = reactive({ education: '本科' })
    const body = {
      session_id: 's1',
      answers: ['A', 'B'],
      learning_style_quiz: styleQuiz,
      demographics,
    }
    await postSseJson('/api/diagnostics/submit/stream', body)

    expect(captured).toBeDefined()
    // 关键断言: 过桥对象必须可结构化克隆 (IPC 硬约束; 修复前此处抛 DataCloneError)
    const cloned = structuredClone(captured)
    expect(cloned.learning_style_quiz).toEqual(['A', 'B'])
    expect(cloned.demographics.education).toBe('本科')
    expect(cloned.session_id).toBe('s1')
  })

  it('数据内容经 round-trip 无损 (代理剥离不改变业务字段)', async () => {
    const profile = reactive({ theory_level: 2, weak_topics: [{ node_id: 'PY-001' }] })
    const body = { session_id: 's2', strategy: 'remediate', profile, tavily_key: undefined }
    const done = postSseJson('/api/diagnostics/feedback/stream', body)
    // body 引用未变 (调用方无感), 仅传输层转纯
    expect(body.profile.theory_level).toBe(2)
    await done
    expect(captured.profile).toEqual({ theory_level: 2, weak_topics: [{ node_id: 'PY-001' }] })
    expect(captured.strategy).toBe('remediate')
  })

  it('undefined/null body 容错', async () => {
    await postSseJson('/api/learning/report/stream', undefined)
    expect(captured).toEqual({})
  })
})
