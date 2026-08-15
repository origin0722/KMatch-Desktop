/**
 * useGraphData — 知识图谱数据适配层
 *
 * 将 store 中的 learning_path 节点列表转换为 G6 v5 渲染所需的
 * { nodes: [{id, data:{...}}], edges: [{id, source, target, data:{}}] } 格式。
 *
 * BUG-045 修复: prerequisites 是 Neo4j 关系非节点属性，后端不返回。
 *   改为由调用方通过 setPrereqMap() 注入外部获取的前置依赖映射。
 * BUG-051 修复: mastery 值从 profile.known_topics/weak_topics 交叉映射，
 *   不再仅依赖节点自身的 mastery_status。
 */
import { ref, computed } from 'vue'
import { useAssessmentStore } from '@/stores/assessment'
import { masteryColor, masterySize } from '@/utils/format'

export function useGraphData() {
  const store = useAssessmentStore()

  /** 原始节点列表（来自 graph_controller 组装的 learning_path） */
  const rawNodes = computed(() => store.knowledgeGraph?.learning_path || [])

  /** node_id → 完整节点对象的快速查找表 */
  const nodeMap = computed(() => {
    const map = {}
    for (const n of rawNodes.value) {
      map[n.node_id] = n
    }
    return map
  })

  // ---------------------------------------------------------------
  // BUG-051: 从 profile 构建 masteryMap（known_topics + weak_topics）
  // ---------------------------------------------------------------
  const masteryMap = computed(() => {
    const map = {}
    const profile = store.profile
    if (!profile) return map
    for (const t of profile.known_topics || []) {
      if (t?.node_id && t.mastery != null) map[t.node_id] = t.mastery
    }
    for (const t of profile.weak_topics || []) {
      if (t?.node_id && t.mastery != null) map[t.node_id] = t.mastery
    }
    return map
  })

  // ---------------------------------------------------------------
  // BUG-045: 外部注入的 prereqMap（由 KnowledgeGraph.vue 批量 API 获取后注入）
  // ---------------------------------------------------------------
  const prereqMap = ref({}) // { node_id: [prereq_node_id, ...] }

  /** 由调用方（KnowledgeGraph.vue）在批量获取前置依赖后调用 */
  function setPrereqMap(map) {
    prereqMap.value = map || {}
  }

  // ---------------------------------------------------------------
  // G6 v5 节点数组
  // ---------------------------------------------------------------
  // 按 node_id 去重 (保首个): G6 graphlib 对重复节点 id 直接抛 "Node already
  // exists" 整图渲染失败, 后端 BFS 曾实测返回同节点多入口重复行 (2026-08-15
  // AI 域 42 行/9 唯一, 已在 engine 侧 Cypher 二次聚合修复), 此处兜底防回归。
  const g6Nodes = computed(() => {
    const seen = new Set()
    return rawNodes.value
      .filter((n) => {
        if (!n.node_id || seen.has(n.node_id)) return false
        seen.add(n.node_id)
        return true
      })
      .map((n) => {
        // BUG-051: 优先画像 mastery，其次节点 mastery，再次 mastery_status 兜底
        const fromProfile = masteryMap.value[n.node_id]
        const m = fromProfile != null
          ? fromProfile
          : (n.mastery ?? (n.mastery_status === 'mastered' ? 1.0 : 0))
        return {
          id: n.node_id,
          data: {
            label: n.name || n.node_id,
            summary: n.summary || '',
            key_points: Array.isArray(n.key_points) ? n.key_points : [],
            mastery: m,
            nodeColor: masteryColor(m),
            nodeSize: masterySize(m),
            category: n.category || '',
            difficulty: n.difficulty || 1,
          },
        }
      })
  })

  // ---------------------------------------------------------------
  // G6 v5 边数组（从 prereqMap 重建——BUG-045）
  // ---------------------------------------------------------------
  const g6Edges = computed(() => {
    const edges = []
    const nodeIdSet = new Set(rawNodes.value.map((n) => n.node_id))
    const edgeSet = new Set() // source>target 去重, 防重复前置画叠边
    let idx = 0
    for (const n of rawNodes.value) {
      const prereqs = prereqMap.value[n.node_id] || []
      for (const p of prereqs) {
        // 仅当前置节点也在当前路径中时才画边（避免孤立连接线）
        if (!nodeIdSet.has(p) || edgeSet.has(`${p}>${n.node_id}`)) {
          continue
        }
        edgeSet.add(`${p}>${n.node_id}`)
        edges.push({
          id: `edge-${idx++}`,
          source: p,
          target: n.node_id,
          data: {},
        })
      }
    }
    return edges
  })

  /** 节点数量 */
  const nodeCount = computed(() => rawNodes.value.length)

  /** 边数量 */
  const edgeCount = computed(() => g6Edges.value.length)

  return { rawNodes, nodeMap, masteryMap, g6Nodes, g6Edges, nodeCount, edgeCount, prereqMap, setPrereqMap }
}
