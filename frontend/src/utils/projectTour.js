/**
 * 项目导读路径生成 (场景二 Step 4: 分层项目解读)
 *
 * 借鉴 Understand-Anything tour-builder: 按调用依赖顺序生成架构学习路径。
 * 纯前端图结构推导 (BFS 分层 + 角色解说), 零 LLM 成本; 深问由"让 AI 解释"承接。
 */

// 导读站点上限 (控时长: 40 实体的项目走 15 站已覆盖主干)
const MAX_STOPS = 15

/**
 * 生成导读站点序列。
 * @param {Array} entities projectGraph.graph.entities
 * @param {Array} relations projectGraph.graph.relations (CALLS/CONTAINS/INHERITS)
 * @param {number} [maxStops] 站点上限
 * @returns {Array<{id, entity, role, why, layer, neighborIds}>} 按入口→调用方向排序
 */
export function buildTourStops(entities, relations, maxStops = MAX_STOPS) {
  const ents = (entities || []).filter((e) => e && e.id != null)
  if (!ents.length) return []

  const idSet = new Set(ents.map((e) => String(e.id)))
  const rels = (relations || []).filter(
    (r) => r && idSet.has(String(r.source)) && idSet.has(String(r.target)),
  )

  // 只用 CALLS 边算入度/出度 (CONTAINS 用于类的方法计数, INHERITS 不参与排序)
  const callsIn = new Map()  // id -> 被调用次数
  const callsOut = new Map() // id -> 调用次数
  const adj = new Map()      // id -> Set(调用的目标 id)
  const containsCount = new Map() // id -> 包含的方法数 (类)
  for (const r of rels) {
    const s = String(r.source)
    const t = String(r.target)
    if (r.type === 'CALLS' || r.label === 'CALLS') {
      callsOut.set(s, (callsOut.get(s) || 0) + 1)
      callsIn.set(t, (callsIn.get(t) || 0) + 1)
      if (!adj.has(s)) adj.set(s, new Set())
      adj.get(s).add(t)
    } else if (r.type === 'CONTAINS' || r.label === 'CONTAINS') {
      containsCount.set(s, (containsCount.get(s) || 0) + 1)
    }
  }

  // 入口: 入度 0; 全环 (无入度 0) → 取最低入度兜底
  const inDeg = (id) => callsIn.get(id) || 0
  let entries = ents.filter((e) => inDeg(String(e.id)) === 0).map((e) => String(e.id))
  if (!entries.length) {
    const minIn = Math.min(...ents.map((e) => inDeg(String(e.id))))
    entries = ents.filter((e) => inDeg(String(e.id)) === minIn).map((e) => String(e.id))
  }

  // BFS 分层 (Kahn 式): 入口为第 1 层, 沿调用方向逐层下探; 同层保持实体原序 (稳定)
  const layerOf = new Map()
  const visited = new Set()
  let frontier = [...entries]
  let layer = 1
  for (const id of frontier) { layerOf.set(id, layer); visited.add(id) }
  const ordered = [...frontier]
  while (frontier.length) {
    const nextSet = new Set()
    for (const id of frontier) {
      for (const t of adj.get(id) || []) {
        if (!visited.has(t)) { visited.add(t); nextSet.add(t) }
      }
    }
    // 同层稳定排序: 按实体在原列表中的顺序
    const next = ents.map((e) => String(e.id)).filter((id) => nextSet.has(id))
    if (next.length) {
      layer += 1
      for (const id of next) layerOf.set(id, layer)
      ordered.push(...next)
    }
    frontier = next
  }
  // 未被任何调用链触及的孤立实体追加到末层之后 (保底可见)
  const orphans = ents.map((e) => String(e.id)).filter((id) => !layerOf.has(id))
  for (const id of orphans) layerOf.set(id, layer + 1)
  ordered.push(...orphans)

  const byId = new Map(ents.map((e) => [String(e.id), e]))
  const stops = ordered.slice(0, maxStops).map((id) => {
    const entity = byId.get(id)
    const out = callsOut.get(id) || 0
    const inn = callsIn.get(id) || 0
    const isEntry = inDeg(id) === 0
    // hub 优先于 entry: 高扇出的入口 (如 main 调 5 个模块) 本身就是主干枢纽
    const role = out >= 3 ? 'hub'
      : isEntry ? 'entry'
      : out === 0 ? 'leaf'
      : 'bridge'
    let why = ''
    if (role === 'hub') {
      why = isEntry
        ? `程序入口且调用 ${out} 个实体，从这里开始并掌握主干`
        : `调用 ${out} 个实体，读懂它就掌握了主干`
    } else if (role === 'entry') {
      why = '无任何调用者，程序从这里开始执行'
    } else if (role === 'leaf') {
      why = '不再调用其他实体，是这段逻辑的末端'
    } else {
      why = `被 ${inn} 处调用又调用 ${out} 个实体，承上启下`
    }
    if (entity?.kind === 'class') {
      const methods = containsCount.get(id) || 0
      why += `；包含 ${methods} 个方法`
    }
    const neighborIds = new Set([...(adj.get(id) || [])])
    for (const [s, ts] of adj) if (ts.has(id)) neighborIds.add(s)
    return { id, entity, role, why, layer: layerOf.get(id), neighborIds }
  })

  return stops
}

/** 角色 → 中文标签 (浮条展示用) */
export const TOUR_ROLE_LABELS = {
  entry: '入口点',
  hub: '核心枢纽',
  bridge: '桥梁',
  leaf: '叶子',
}
