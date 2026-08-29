/**
 * 知识/项目图谱 → Excalidraw 确定性导出 (W3, 借鉴 excalidraw-skill)
 *
 * 该 skill 的精髓是「LLM 做判断、确定性代码做渲染」: 图谱拓扑数据已存在,
 * 转换全程确定性 — 零 LLM 成本、坐标零幻觉、离线可用。设计规范同样移植:
 * CJK 感知尺寸 (utils/nodeSize)、语义底色、折线箭头绑定 (拖动节点连线跟随)。
 *
 * 产物为标准 .excalidraw v2 场景 JSON: excalidraw.com / VS Code Excalidraw 插件
 * 可直接打开继续编辑 (手绘风格)。
 */
import { cjkAwareWidth, textDisplayWidth } from '@/utils/nodeSize'

const FONT_SIZE = 16
const LINE_HEIGHT = 1.25
const DEFAULT_OPTS = {
  nodeH: 64,
  padding: 32,
  minW: 140,
  maxW: 280,
  gapX: 100,
  gapY: 70,
  strokeColor: '#1e1e1e',
  textColor: '#1e1e1e',
}

/** 确定性伪随机 seed (同输入同输出, 便于测试回归; excalidraw 要求 int) */
function seedOf(i) {
  return (i * 7919 + 17) % 2147483647
}

/** 元素公共字段 (excalidraw v2 序列化契约) */
function baseElement(id, type, x, y, index) {
  return {
    id,
    type,
    x,
    y,
    angle: 0,
    strokeColor: '#1e1e1e',
    backgroundColor: 'transparent',
    fillStyle: 'solid',
    strokeWidth: 1,
    strokeStyle: 'solid',
    roughness: 1,
    opacity: 100,
    groupIds: [],
    frameId: null,
    roundness: null,
    seed: seedOf(index),
    version: 1,
    versionNonce: seedOf(index + 1),
    isDeleted: false,
    boundElements: null,
    updated: 1700000000000 + index,
    link: null,
    locked: false,
  }
}

/** 单节点卡片宽: CJK 感知估算 (或调用方 positions 已给 width 则不重复算) */
export function nodeCardWidth(label, opts = DEFAULT_OPTS) {
  return cjkAwareWidth(label, {
    fontSize: FONT_SIZE, padding: opts.padding, min: opts.minW, max: opts.maxW,
  })
}

/**
 * 缺省布局: 确定性分层 (BFS 深度分列, 无环假设不满足时兜底第 0 列)。
 * 无 G6 实例 (如 AI 工具直接从 store 导出) 时保证产物仍有可读布局。
 */
export function fallbackPositions(nodes, edges, opts = DEFAULT_OPTS) {
  const ids = nodes.map((n) => n.id)
  const idSet = new Set(ids)
  const depth = new Map()
  const adj = new Map(ids.map((id) => [id, []]))
  const indeg = new Map(ids.map((id) => [id, 0]))
  for (const e of edges) {
    if (!idSet.has(e.source) || !idSet.has(e.target) || e.source === e.target) continue
    adj.get(e.source).push(e.target)
    indeg.set(e.target, indeg.get(e.target) + 1)
  }
  const queue = ids.filter((id) => indeg.get(id) === 0)
  queue.forEach((id) => depth.set(id, 0))
  const visited = new Set(queue)
  while (queue.length) {
    const cur = queue.shift()
    for (const t of adj.get(cur)) {
      const d = (depth.get(cur) || 0) + 1
      if (!depth.has(t) || depth.get(t) < d) depth.set(t, d)
      if (!visited.has(t)) { visited.add(t); queue.push(t) }
    }
  }
  ids.forEach((id) => { if (!depth.has(id)) depth.set(id, 0) })

  const cols = new Map()
  for (const n of nodes) {
    const d = depth.get(n.id) || 0
    if (!cols.has(d)) cols.set(d, [])
    cols.get(d).push(n)
  }
  const pos = {}
  for (const [, col] of cols) {
    col.forEach((n, i) => {
      pos[n.id] = {
        x: (depth.get(n.id) || 0) * (opts.maxW + opts.gapX),
        y: i * (opts.nodeH + opts.gapY),
        width: n.width || nodeCardWidth(n.label, opts),
        height: opts.nodeH,
      }
    })
  }
  return pos
}

/**
 * 从 G6 实例读渲染后坐标 (中心点) → 左上角 + 尺寸。
 * sizeOf: (id) => {width, height}; 读取失败的节点不进结果 (走 fallback 布局)。
 */
export function collectG6Positions(graph, ids, sizeOf) {
  const out = {}
  if (!graph || typeof graph.getElementPosition !== 'function') return out
  for (const id of ids) {
    try {
      const p = graph.getElementPosition(id)
      const size = sizeOf(id)
      if (!p || !size) continue
      out[id] = { x: p.x - size.width / 2, y: p.y - size.height / 2, width: size.width, height: size.height }
    } catch { /* 单节点失败不阻断导出 */ }
  }
  return out
}

/**
 * 图谱 → Excalidraw 场景。
 * @param {Array} nodes  [{ id, label, color? }]  color: 节点底色 (缺省浅灰)
 * @param {Array} edges  [{ source, target }]
 * @param {Object} positions { [id]: {x,y,width,height} } 左上角坐标; 缺省用内置分层布局
 * @param {Object} options { nodeH/padding/minW/maxW/gapX/gapY/strokeColor/textColor }
 * @returns {Object} excalidraw v2 scene (JSON.stringify 后即为 .excalidraw 文件内容)
 */
export function graphToExcalidraw(nodes, edges, positions = {}, options = {}) {
  const opts = { ...DEFAULT_OPTS, ...options }
  const rects = []
  const texts = []
  const arrows = []
  const boundByNode = new Map() // nodeId -> [{id, type}]
  let idx = 0

  // 无坐标的节点走确定性 fallback (合并调用方给的坐标)
  const fb = fallbackPositions(nodes, edges, opts)
  const pos = { ...fb, ...Object.fromEntries(Object.entries(positions).filter(([, v]) => v)) }

  // ① 矩形节点 + 绑定文本
  for (const n of nodes) {
    const p = pos[n.id] || {
      x: 0, y: rects.length * (opts.nodeH + opts.gapY),
      width: nodeCardWidth(n.label, opts), height: opts.nodeH,
    }
    const rectId = `rect:${n.id}`
    const textId = `text:${n.id}`
    rects.push({
      ...baseElement(rectId, 'rectangle', Math.round(p.x), Math.round(p.y), idx++),
      width: Math.round(p.width),
      height: Math.round(p.height),
      strokeColor: opts.strokeColor,
      backgroundColor: n.color || '#e9ecef',
      roundness: { type: 3 },
    })
    const lines = String(n.label ?? n.id).split('\n')
    const tw = Math.max(...lines.map((l) => textDisplayWidth(l, FONT_SIZE)))
    const th = lines.length * FONT_SIZE * LINE_HEIGHT
    texts.push({
      ...baseElement(textId, 'text', Math.round(p.x + p.width / 2 - tw / 2), Math.round(p.y + p.height / 2 - th / 2), idx++),
      width: Math.round(tw),
      height: Math.round(th),
      text: lines.join('\n'),
      fontSize: FONT_SIZE,
      fontFamily: 1,
      textAlign: 'center',
      verticalAlign: 'middle',
      containerId: rectId,
      lineHeight: LINE_HEIGHT,
      baseline: FONT_SIZE,
      strokeColor: opts.textColor,
    })
    boundByNode.set(n.id, [{ id: textId, type: 'text' }])
  }

  // ② 折线箭头 (绑定两端, 拖动跟随): 纵向为主走 底→顶, 横向为主走 右→左
  let eIdx = 0
  for (const e of edges) {
    const sp = pos[e.source]
    const tp = pos[e.target]
    if (!sp || !tp) continue
    const scx = sp.x + sp.width / 2
    const scy = sp.y + sp.height / 2
    const tcx = tp.x + tp.width / 2
    const tcy = tp.y + tp.height / 2
    let sx, sy, ex, ey
    if (Math.abs(tcy - scy) >= Math.abs(tcx - scx)) {
      sx = scx; sy = sp.y + sp.height      // 源底部
      ex = tcx; ey = tp.y - 4              // 目标顶部 (gap 4)
    } else {
      sx = sp.x + sp.width; sy = scy       // 源右侧
      ex = tp.x - 4; ey = tcy              // 目标左侧
    }
    const dx = ex - sx
    const dy = ey - sy
    // 两段折线: 先沿主轴走完差距, 再走副轴 (视觉上就是规整的直角连线)
    const points = Math.abs(dy) >= Math.abs(dx)
      ? [[0, 0], [0, dy], [dx, dy]]
      : [[0, 0], [dx, 0], [dx, dy]]
    const arrowId = `arrow:${eIdx}`
    arrows.push({
      ...baseElement(arrowId, 'arrow', Math.round(sx), Math.round(sy), idx++),
      width: Math.abs(Math.round(dx)),
      height: Math.abs(Math.round(dy)),
      points,
      startBinding: { elementId: `rect:${e.source}`, focus: 0, gap: 4 },
      endBinding: { elementId: `rect:${e.target}`, focus: 0, gap: 4 },
      startArrowhead: null,
      endArrowhead: 'arrow',
      lastCommittedPoint: null,
      roundness: { type: 2 },
    })
    const sb = boundByNode.get(e.source)
    if (sb) sb.push({ id: arrowId, type: 'arrow' })
    const tb = boundByNode.get(e.target)
    if (tb) tb.push({ id: arrowId, type: 'arrow' })
    eIdx++
  }

  // ③ 回填 boundElements (矩形须列出其绑定的 text/arrow, excalidraw 才会联动移动)
  for (const r of rects) r.boundElements = boundByNode.get(r.id.slice(5)) || null

  return {
    type: 'excalidraw',
    version: 2,
    source: 'KMatch·知链',
    elements: [...rects, ...texts, ...arrows],
    appState: { viewBackgroundColor: '#ffffff', gridSize: null },
    files: {},
  }
}

/** 触发浏览器下载 (Electron 与普通浏览器通用) */
export function downloadExcalidraw(scene, filename = 'graph.excalidraw') {
  const blob = new Blob([JSON.stringify(scene)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename.endsWith('.excalidraw') ? filename : `${filename}.excalidraw`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
