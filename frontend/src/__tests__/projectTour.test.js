import { describe, it, expect } from 'vitest'
import { buildTourStops, TOUR_ROLE_LABELS } from '@/utils/projectTour'

// 测试图: entry → a → b → leaf, 以及 entry → c (双入口分支)
const ENTITIES = [
  { id: 'e1', name: 'main', kind: 'function' },
  { id: 'e2', name: 'crawl', kind: 'function' },
  { id: 'e3', name: 'parse', kind: 'function' },
  { id: 'e4', name: 'save', kind: 'function' },
  { id: 'e5', name: 'cli', kind: 'function' },
  { id: 'c1', name: 'Crawler', kind: 'class' },
]
const CALLS = (s, t) => ({ source: s, target: t, type: 'CALLS' })
const RELS = [
  CALLS('e1', 'e2'),   // main → crawl
  CALLS('e2', 'e3'),   // crawl → parse
  CALLS('e3', 'e4'),   // parse → save
  CALLS('e5', 'e2'),   // cli → crawl
  { source: 'c1', target: 'e3', type: 'CONTAINS' },  // Crawler 包含 parse
  { source: 'c1', target: 'e4', type: 'CONTAINS' },
]

describe('buildTourStops', () => {
  it('入口优先, BFS 顺序沿调用方向', () => {
    const stops = buildTourStops(ENTITIES, RELS)
    const ids = stops.map((s) => s.id)
    // 入口 e1(main) 与 e5(cli) 在第 1 层最前 (按实体原序 e1 在 e5 前)
    expect(ids.indexOf('e1')).toBeLessThan(ids.indexOf('e2'))
    expect(ids.indexOf('e2')).toBeLessThan(ids.indexOf('e3'))
    expect(ids.indexOf('e3')).toBeLessThan(ids.indexOf('e4'))
    expect(ids[0]).toBe('e1')
  })

  it('layer 字段正确 (入口=1, 逐层+1)', () => {
    const stops = buildTourStops(ENTITIES, RELS)
    const layer = Object.fromEntries(stops.map((s) => [s.id, s.layer]))
    expect(layer.e1).toBe(1)
    expect(layer.e5).toBe(1)
    expect(layer.e2).toBe(2)   // main/cli → crawl
    expect(layer.e3).toBe(3)   // crawl → parse
    expect(layer.e4).toBe(4)   // parse → save
  })

  it('角色判定: entry/hub/bridge/leaf', () => {
    const stops = buildTourStops(ENTITIES, RELS)
    const role = Object.fromEntries(stops.map((s) => [s.id, s.role]))
    expect(role.e1).toBe('entry')
    expect(role.e5).toBe('entry')
    expect(role.e4).toBe('leaf')      // 出度 0
    // e2(crawl): 入度 2, 出度 1 → bridge
    expect(role.e2).toBe('bridge')
  })

  it('出度≥3 判定 hub', () => {
    const ents = [
      { id: 'm', name: 'main', kind: 'function' },
      { id: 'a', name: 'a', kind: 'function' },
      { id: 'b', name: 'b', kind: 'function' },
      { id: 'c', name: 'c', kind: 'function' },
    ]
    const rels = [CALLS('m', 'a'), CALLS('m', 'b'), CALLS('m', 'c')]
    const stops = buildTourStops(ents, rels)
    const m = stops.find((s) => s.id === 'm')
    expect(m.role).toBe('hub')
    expect(m.why).toContain('调用 3 个实体')
  })

  it('类实体 why 附带方法计数 (CONTAINS)', () => {
    const stops = buildTourStops(ENTITIES, RELS)
    const c1 = stops.find((s) => s.id === 'c1')
    expect(c1).toBeTruthy()
    expect(c1.why).toContain('包含 2 个方法')
  })

  it('neighborIds 含调用出边与入边邻居', () => {
    const stops = buildTourStops(ENTITIES, RELS)
    const e2 = stops.find((s) => s.id === 'e2')
    expect(e2.neighborIds.has('e1')).toBe(true)   // main → crawl
    expect(e2.neighborIds.has('e5')).toBe(true)   // cli → crawl
    expect(e2.neighborIds.has('e3')).toBe(true)   // crawl → parse
  })

  it('maxStops 截断', () => {
    const ents = Array.from({ length: 20 }, (_, i) => ({ id: `n${i}`, name: `n${i}`, kind: 'function' }))
    const rels = ents.slice(0, 19).map((e, i) => CALLS(e.id, `n${i + 1}`))
    const stops = buildTourStops(ents, rels, 5)
    expect(stops).toHaveLength(5)
  })

  it('空输入返回空', () => {
    expect(buildTourStops([], [])).toEqual([])
    expect(buildTourStops(null, null)).toEqual([])
  })

  it('无 CALLS 时入度全 0 → 实体本身即入口 (仍可生成单站)', () => {
    const stops = buildTourStops([{ id: 'a', name: 'x', kind: 'function' }], [])
    expect(stops).toHaveLength(1)
    expect(stops[0].role).toBe('entry')
  })

  it('全环图取最低入度兜底', () => {
    const ents = [
      { id: 'a', name: 'a', kind: 'function' },
      { id: 'b', name: 'b', kind: 'function' },
      { id: 'c', name: 'c', kind: 'function' },
    ]
    const rels = [CALLS('a', 'b'), CALLS('b', 'c'), CALLS('c', 'a')]  // 环
    const stops = buildTourStops(ents, rels)
    expect(stops.length).toBeGreaterThan(0)
    expect(stops[0].layer).toBe(1)
  })

  it('角色标签映射完整', () => {
    expect(TOUR_ROLE_LABELS.entry).toBe('入口点')
    expect(TOUR_ROLE_LABELS.hub).toBe('核心枢纽')
    expect(TOUR_ROLE_LABELS.bridge).toBe('桥梁')
    expect(TOUR_ROLE_LABELS.leaf).toBe('叶子')
  })
})
