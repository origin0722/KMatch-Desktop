/**
 * useGraphData 组合式单测
 *
 * 核心回归: g6Nodes 按 node_id 去重 (保首个) — 后端 assemble_learning_path
 * 的 BFS 曾实测返回同节点多入口重复行 (2026-08-15 AI 域 42 行/9 唯一),
 * G6 graphlib 对重复节点 id 直接抛 "Node already exists" 整图渲染失败。
 * 覆盖: 重复节点去重、边只画两端均在节点集的、mastery 从画像交叉映射。
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { ref } from 'vue'
import { setActivePinia, createPinia } from 'pinia'

import { useGraphData } from '@/composables/useGraphData'
import { useAssessmentStore } from '@/stores/assessment'

function _node(nodeId, extra = {}) {
  return {
    node_id: nodeId,
    name: `节点${nodeId}`,
    summary: '',
    key_points: [],
    difficulty: 1,
    ...extra,
  }
}

describe('useGraphData', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('learning_path 含重复 node_id 时 g6Nodes 去重保首个', () => {
    const store = useAssessmentStore()
    store.knowledgeGraph = {
      learning_path: [
        _node('AI-001'),
        _node('AI-003', { name: '首个003' }),
        _node('AI-004'),
        _node('AI-003', { name: '重复003' }),
        _node('AI-010'),
        _node('AI-004'),
        _node('AI-010'),
      ],
    }

    const { g6Nodes, nodeCount } = useGraphData()
    const ids = g6Nodes.value.map((n) => n.id)

    expect(nodeCount.value).toBe(7) // rawNodes 保持原样
    expect(ids).toEqual(['AI-001', 'AI-003', 'AI-004', 'AI-010'])
    // 保首个: 重复项的 name 不得覆盖首个
    expect(g6Nodes.value.find((n) => n.id === 'AI-003').data.label).toBe('首个003')
  })

  it('无 node_id 的脏数据被过滤, 不再产出 undefined id 节点', () => {
    const store = useAssessmentStore()
    store.knowledgeGraph = { learning_path: [{ name: '脏数据' }, _node('AI-001')] }

    const { g6Nodes } = useGraphData()
    expect(g6Nodes.value.map((n) => n.id)).toEqual(['AI-001'])
  })

  it('边仅连接两端均在节点集中的前置 (BUG-045), 重复不产生重复边', () => {
    const store = useAssessmentStore()
    store.knowledgeGraph = { learning_path: [_node('AI-001'), _node('AI-002')] }

    const data = useGraphData()
    data.setPrereqMap({
      'AI-002': ['AI-001', 'AI-001'], // 重复前置
      'AI-003': ['AI-001'],           // AI-003 不在路径中 → 不画
    })

    const edges = data.g6Edges.value
    expect(edges).toHaveLength(1)
    expect(edges[0]).toMatchObject({ source: 'AI-001', target: 'AI-002' })
  })

  it('mastery 优先取画像 known_topics/weak_topics (BUG-051)', () => {
    const store = useAssessmentStore()
    store.knowledgeGraph = { learning_path: [_node('AI-001'), _node('AI-002')] }
    store.profile = {
      known_topics: [{ node_id: 'AI-001', mastery: 0.8 }],
      weak_topics: [{ node_id: 'AI-002', mastery: 0.2 }],
    }

    const { g6Nodes } = useGraphData()
    expect(g6Nodes.value.find((n) => n.id === 'AI-001').data.mastery).toBeCloseTo(0.8)
    expect(g6Nodes.value.find((n) => n.id === 'AI-002').data.mastery).toBeCloseTo(0.2)
  })

  it('sourceOverride 覆写显示源 (历史回看), 缺省仍读 live knowledgeGraph', () => {
    const store = useAssessmentStore()
    store.knowledgeGraph = { learning_path: [_node('LIVE-1')] }
    const snapshot = { learning_path: [_node('HIST-1')] }
    const override = ref(snapshot)

    const { rawNodes } = useGraphData(override)
    expect(rawNodes.value[0].node_id).toBe('HIST-1')
    // live 图谱未被覆盖 (可随时返回当前; 回退发生在 displayGraph 层, 覆写为空即显示空)
    expect(store.knowledgeGraph.learning_path[0].node_id).toBe('LIVE-1')

    override.value = null
    expect(rawNodes.value).toEqual([])
  })
})
