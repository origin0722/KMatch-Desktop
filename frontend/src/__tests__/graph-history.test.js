/** graphHistory 图谱历史 store 单测 (项目图谱 / 学习图谱 分类缓存)。 */
import { describe, it, expect, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useGraphHistoryStore } from '@/stores/graphHistory'

describe('graphHistory store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
  })

  it('addProject / addLearning 分类入列并去重置顶', () => {
    const s = useGraphHistoryStore()
    s.addProject({ projectId: 'p1', name: 'demo' })
    s.addProject({ projectId: 'p2', name: 'crawler' })
    s.addLearning({ sessionId: 's1', name: 'Python 入门', snapshot: { learning_path: [{ node_id: 'PY-001' }] } })
    expect(s.items).toHaveLength(3)
    expect(s.items[0].type).toBe('learning') // 最新在前
    // 去重: 重复 addProject 只保留一条
    s.addProject({ projectId: 'p1', name: 'demo' })
    expect(s.items.filter((i) => i.id === 'project:p1')).toHaveLength(1)
    expect(s.items[0].id).toBe('project:p1')
  })

  it('addLearning 无 learning_path 不入列', () => {
    const s = useGraphHistoryStore()
    s.addLearning({ sessionId: 'x', snapshot: {} })
    expect(s.items).toHaveLength(0)
  })

  it('remove 删除条目并持久化', () => {
    const s = useGraphHistoryStore()
    s.addProject({ projectId: 'p1', name: 'demo' })
    s.remove('project:p1')
    expect(s.items).toHaveLength(0)
    // 新实例从 localStorage 恢复
    setActivePinia(createPinia())
    const s2 = useGraphHistoryStore()
    expect(s2.items).toHaveLength(0)
  })

  it('跨实例持久化 (上限 12)', () => {
    const s = useGraphHistoryStore()
    for (let i = 0; i < 15; i++) s.addLearning({ sessionId: `s${i}`, snapshot: { learning_path: [{ node_id: 'PY-001' }] } })
    expect(s.items).toHaveLength(12)
    setActivePinia(createPinia())
    expect(useGraphHistoryStore().items).toHaveLength(12)
  })
})
