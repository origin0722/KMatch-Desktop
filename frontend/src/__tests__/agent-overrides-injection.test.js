import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useAgentLlmStore } from '@/stores/agentLlm'

// 用 vi.hoisted 让 mock 工厂能引用 captured (vitest 限制: 工厂内不能引用外部变量, 除非 hoisted)
const { captured } = vi.hoisted(() => ({ captured: {} }))

// mock @/api/index 的 http, 拦截 post body 断言 llm_overrides 注入
// (比走 window.api.http adapter 稳: hasIpc 在模块加载期判定, 跨文件加载顺序不可控)
vi.mock('@/api/index', () => {
  const okBody = {
    session_id: 's', profile: {}, review_results: {}, assessment: {},
    knowledge_graph: {}, generated_content: {}, learning_report: {}, orchestration_log: [],
  }
  return {
    default: {
      post: vi.fn(async (url, body) => { captured.url = url; captured.body = body; return okBody }),
      get: vi.fn(async () => ({})),
    },
  }
})

describe('agent overrides injection into diagnostics API', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    captured.body = undefined
    captured.url = undefined
  })

  it('submitAssessment injects llm_overrides when agent overrides enabled', async () => {
    const agent = useAgentLlmStore()
    agent.setUseOverrides(true)
    agent.setApiKey('sk-agent')
    agent.setProvider('deepseek')
    agent.setModel('dm')

    const { submitAssessment } = await import('@/api/diagnostics')
    await submitAssessment({ targetDirection: 'x' })
    expect(captured.url).toBe('/api/diagnostics/assess')
    expect(captured.body.llm_overrides).toEqual(expect.objectContaining({ api_key: 'sk-agent', model: 'dm' }))
  })

  it('submitAssessment does NOT inject when agent overrides disabled', async () => {
    const agent = useAgentLlmStore()
    agent.setUseOverrides(false)

    const { submitAssessment } = await import('@/api/diagnostics')
    await submitAssessment({ targetDirection: 'x' })
    expect(captured.body.llm_overrides).toBeUndefined()
  })
})
