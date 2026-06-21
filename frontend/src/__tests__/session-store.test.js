import { describe, it, expect, beforeEach, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

// mock assessment store (session.activeStage 派生自它)
vi.mock('@/stores/assessment', () => ({
  useAssessmentStore: () => ({
    hasResults: false,
    loading: false,
    phase: 'idle',
    orchestrationLog: [],
  }),
}))

const { useSessionStore } = await import('@/stores/session')

describe('session store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('activeStage=goal 当无结果无日志无 loading', () => {
    const s = useSessionStore()
    expect(s.activeStage).toBe('goal')
  })

  it('splitView 默认 null, setSplitView/closeSplit 控制', () => {
    const s = useSessionStore()
    expect(s.splitView).toBeNull()
    s.setSplitView('graph')
    expect(s.splitView).toBe('graph')
    s.closeSplit()
    expect(s.splitView).toBeNull()
  })

  it('setSplitView 拒绝非法视图名', () => {
    const s = useSessionStore()
    s.setSplitView('code')
    expect(s.splitView).toBeNull() // code 不在允许列表
  })
})
