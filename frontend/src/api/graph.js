/**
 * 知识图谱查询 API
 *
 * 对齐 backend/app/api/graph.py — 10 条路由。
 * B 端第3周 G6 图谱渲染组件对接本模块。
 *
 * GET  /api/graph/node/{id}              按节点 ID 查询
 * GET  /api/graph/category/{category}     按分类查询
 * GET  /api/graph/difficulty              按难度区间查询 (?min_d=&max_d=)
 * GET  /api/graph/tags                    按标签查询 (?tags=a,b)
 * GET  /api/graph/prerequisites/{id}      查询节点前置依赖
 * GET  /api/graph/dependents/{id}         查询依赖该节点的后继
 * GET  /api/graph/search                  语义向量检索 (?q=&top_k=)
 * POST /api/graph/hybrid                  图遍历+向量混合检索
 * POST /api/graph/path                    组装个性化学习路径
 * PUT  /api/graph/status/{id}             更新节点掌握状态
 */
import http from './index'

// ---------------------------------------------------------------
// 查询类
// ---------------------------------------------------------------

/** 按节点 ID 查询 */
export function getNode(nodeId) {
  return http.get(`/api/graph/node/${nodeId}`)
}

/** 按分类查询节点列表 */
export function getByCategory(category) {
  return http.get(`/api/graph/category/${category}`)
}

/** 按难度区间查询 */
export function getByDifficulty(minD = 1, maxD = 5) {
  return http.get('/api/graph/difficulty', { params: { min_d: minD, max_d: maxD } })
}

/** 按标签查询（逗号分隔） */
export function getByTags(tags) {
  return http.get('/api/graph/tags', { params: { tags } })
}

/** 查询节点前置依赖 */
export function getPrerequisites(nodeId) {
  return http.get(`/api/graph/prerequisites/${nodeId}`)
}

/**
 * 批量查询节点前置依赖 (v1.3.3: 图谱视图消 N+1, 20 节点路径 20 RTT → 1)
 * @returns {Promise<Object>} {node_id: [前置节点]}
 */
export function getPrerequisitesBatch(nodeIds) {
  return http.post('/api/graph/prerequisites/batch', { node_ids: nodeIds })
}

/** 查询依赖该节点的后继 */
export function getDependents(nodeId) {
  return http.get(`/api/graph/dependents/${nodeId}`)
}

/** 语义向量检索 */
export function semanticSearch(q, topK = 5) {
  return http.get('/api/graph/search', { params: { q, top_k: topK } })
}

// ---------------------------------------------------------------
// 混合检索 / 路径组装
// ---------------------------------------------------------------

/**
 * 图遍历 + 向量混合检索
 * @param {Object} params
 * @param {string[]} params.knownIds - 已掌握节点 ID
 * @param {string[]} params.weakIds - 薄弱节点 ID
 * @param {number} [params.level=3] - 目标难度等级
 * @param {number} [params.topK=10]
 */
export function hybridRetrieve({ knownIds = [], weakIds = [], level = 3, topK = 10 } = {}) {
  return http.post('/api/graph/hybrid', {
    known_ids: knownIds,
    weak_ids: weakIds,
    level,
    top_k: topK,
  })
}

/**
 * 组装个性化学习路径
 * @param {Object} params
 * @param {string[]} params.knownIds - 已掌握节点 ID
 * @param {string[]} params.weakIds - 薄弱节点 ID
 * @param {number} [params.level=2] - 目标难度等级
 * @param {number} [params.maxNodes=20]
 */
export function assemblePath({ knownIds = [], weakIds = [], level = 2, maxNodes = 20 } = {}) {
  return http.post('/api/graph/path', {
    known_ids: knownIds,
    weak_ids: weakIds,
    level,
    max_nodes: maxNodes,
  })
}

// ---------------------------------------------------------------
// 状态管理
// ---------------------------------------------------------------

/** 更新节点掌握状态 */
export function updateNodeStatus(nodeId, status) {
  return http.put(`/api/graph/status/${nodeId}`, { status })
}
