/**
 * 场景：学情画像 / 知识图谱类型契约 helper (C3)。
 *
 * buildSystemPrompt 经这些 helper 读取 assessment 的 profile/knowledgeGraph,
 * 字段名集中一处。守卫: 缺失字段安全降级, 薄弱知识点取 name→node_id, 学时保留 1 位小数。
 */
import { describe, expect, it } from 'vitest'
import {
  hasProfile,
  profileTheoryLevel,
  profilePracticeLevel,
  profileWeakTopicNames,
  learningPathLength,
  learningEstimatedHours,
} from '@/ide/chat/types'

describe('chat/types — 学情画像类型契约 (C3)', () => {
  it('hasProfile: 仅对象为真', () => {
    expect(hasProfile({})).toBe(true)
    expect(hasProfile(null)).toBe(false)
    expect(hasProfile(undefined)).toBe(false)
    expect(hasProfile('x')).toBe(false)
  })

  it('profileTheoryLevel / profilePracticeLevel: 取值或 null', () => {
    const p = { theory_level: 3, practice_level: 4 }
    expect(profileTheoryLevel(p)).toBe(3)
    expect(profilePracticeLevel(p)).toBe(4)
    expect(profileTheoryLevel({})).toBeNull()
    expect(profileTheoryLevel(null)).toBeNull()
  })

  it('profileWeakTopicNames: 取 name, 缺则 node_id, 最多 limit 个', () => {
    const p = { weak_topics: [
      { name: '循环', node_id: 'n1' },
      { node_id: 'n2' },          // 无 name 取 node_id
      { name: '函数' },
      { name: '类', node_id: 'n4' },
    ] }
    expect(profileWeakTopicNames(p, 5)).toEqual(['循环', 'n2', '函数', '类'])
    expect(profileWeakTopicNames(p, 2)).toEqual(['循环', 'n2'])
    expect(profileWeakTopicNames({}, 5)).toEqual([])
    expect(profileWeakTopicNames(null)).toEqual([])
  })

  it('learningPathLength: learning_path 长度或 0', () => {
    expect(learningPathLength({ learning_path: [1, 2, 3] })).toBe(3)
    expect(learningPathLength({})).toBe(0)
    expect(learningPathLength(null)).toBe(0)
  })

  it('learningEstimatedHours: 保留 1 位小数, 缺失返回 null', () => {
    expect(learningEstimatedHours({ estimated_total_hours: 3.456 })).toBe(3.5)
    expect(learningEstimatedHours({ estimated_total_hours: 2 })).toBe(2)
    expect(learningEstimatedHours({})).toBeNull()
    expect(learningEstimatedHours(null)).toBeNull()
  })
})
