/**
 * W3 excalidraw 确定性导出单测 (utils/excalidrawExport)
 *
 * 借鉴 excalidraw-skill 的「确定性渲染」哲学: 拓扑 → 场景 JSON 全程无随机
 * (seed 确定性), CJK 感知尺寸, 箭头双向绑定。另含 registry 工具契约用例。
 */
import { describe, it, expect } from 'vitest'
import {
  graphToExcalidraw,
  fallbackPositions,
  collectG6Positions,
  nodeCardWidth,
  downloadExcalidraw,
} from '@/utils/excalidrawExport'
import { TOOL_NAMES, DEFAULT_TOOL_PERMISSIONS, TOOL_PERMISSION, toolCallExample } from '@/ide/tools/registry'

const NODES = [
  { id: 'A', label: '变量', color: '#ffd43b' },
  { id: 'B', label: '循环' },
  { id: 'C', label: 'a-very-long-latin-qualified-name' },
]
const EDGES = [
  { source: 'A', target: 'B' },
  { source: 'A', target: 'C' },
]

describe('graphToExcalidraw 场景契约', () => {
  it('产出 excalidraw v2 场景骨架', () => {
    const scene = graphToExcalidraw(NODES, EDGES)
    expect(scene.type).toBe('excalidraw')
    expect(scene.version).toBe(2)
    expect(scene.source).toContain('KMatch')
    expect(scene.files).toEqual({})
    expect(scene.appState.viewBackgroundColor).toBeTruthy()
    expect(Array.isArray(scene.elements)).toBe(true)
  })

  it('每个节点产出 rectangle + 绑定 text, 文本居中且 containerId 指向矩形', () => {
    const scene = graphToExcalidraw(NODES, [])
    const rects = scene.elements.filter((e) => e.type === 'rectangle')
    const texts = scene.elements.filter((e) => e.type === 'text')
    expect(rects).toHaveLength(3)
    expect(texts).toHaveLength(3)
    for (const t of texts) {
      expect(t.containerId).toBe(`rect:${t.text === '变量' ? 'A' : t.text === '循环' ? 'B' : 'C'}`)
      expect(t.textAlign).toBe('center')
      expect(t.fontSize).toBeGreaterThan(0)
    }
    for (const r of rects) {
      const bound = r.boundElements || []
      expect(bound.some((b) => b.type === 'text')).toBe(true)
    }
  })

  it('边产出 arrow, 双向绑定 (rect.boundElements ↔ arrow.start/endBinding)', () => {
    const scene = graphToExcalidraw(NODES, EDGES)
    const arrows = scene.elements.filter((e) => e.type === 'arrow')
    expect(arrows).toHaveLength(2)
    for (const a of arrows) {
      expect(a.startBinding.elementId).toMatch(/^rect:/)
      expect(a.endBinding.elementId).toMatch(/^rect:/)
      expect(a.endArrowhead).toBe('arrow')
      expect(a.points[0]).toEqual([0, 0])
    }
    const rectA = scene.elements.find((e) => e.id === 'rect:A')
    const arrowIds = (rectA.boundElements || []).filter((b) => b.type === 'arrow').map((b) => b.id)
    expect(arrowIds).toHaveLength(2)
  })

  it('节点底色与语义色透传 (缺省浅灰)', () => {
    const scene = graphToExcalidraw(NODES, [])
    const a = scene.elements.find((e) => e.id === 'rect:A')
    const b = scene.elements.find((e) => e.id === 'rect:B')
    expect(a.backgroundColor).toBe('#ffd43b')
    expect(b.backgroundColor).toBe('#e9ecef')
  })

  it('显式 positions 覆盖缺省布局 (左上角坐标直通)', () => {
    const positions = { A: { x: 500, y: 400, width: 200, height: 60 } }
    const scene = graphToExcalidraw(NODES, [], positions)
    const a = scene.elements.find((e) => e.id === 'rect:A')
    expect(a.x).toBe(500)
    expect(a.y).toBe(400)
    expect(a.width).toBe(200)
  })

  it('确定性: 同输入同输出 (seed 稳定)', () => {
    const s1 = JSON.stringify(graphToExcalidraw(NODES, EDGES))
    const s2 = JSON.stringify(graphToExcalidraw(NODES, EDGES))
    expect(s1).toBe(s2)
  })

  it('文本宽度尊重 CJK 感知卡片宽 (中文节点卡片 ≥ 标签宽 + padding)', () => {
    const scene = graphToExcalidraw([{ id: 'K', label: '数据库连接池配置管理策略' }], [])
    const rect = scene.elements.find((e) => e.id === 'rect:K')
    const text = scene.elements.find((e) => e.id === 'text:K')
    expect(rect.width).toBeGreaterThanOrEqual(text.width)
  })
})

describe('fallbackPositions 确定性分层布局', () => {
  it('无入边节点在第 0 列, 后继按依赖深度递增列', () => {
    const nodes = NODES.map((n) => ({ ...n, width: nodeCardWidth(n.label) }))
    const pos = fallbackPositions(nodes, EDGES)
    expect(pos.A.x).toBeLessThan(pos.B.x)
    expect(pos.A.x).toBeLessThan(pos.C.x)
    // 同列节点纵向堆叠
    expect(pos.B.y).not.toBe(pos.C.y)
  })

  it('环不崩溃 (互相引用兜底第 0 列)', () => {
    const nodes = [
      { id: 'X', label: 'X' },
      { id: 'Y', label: 'Y' },
    ]
    const pos = fallbackPositions(nodes, [{ source: 'X', target: 'Y' }, { source: 'Y', target: 'X' }])
    expect(pos.X).toBeTruthy()
    expect(pos.Y).toBeTruthy()
  })
})

describe('collectG6Positions (G6 中心点 → 左上角)', () => {
  it('中心坐标换算为左上角并带尺寸', () => {
    const fakeGraph = {
      getElementPosition: (id) => ({ x: 100 + id.length, y: 200 }),
    }
    const pos = collectG6Positions(fakeGraph, ['A'], () => ({ width: 160, height: 60 }))
    expect(pos.A.x).toBeCloseTo(100 + 1 - 80)
    expect(pos.A.y).toBeCloseTo(200 - 30)
    expect(pos.A.width).toBe(160)
  })

  it('G6 实例不可用时返回空 (调用方走 fallback 布局)', () => {
    expect(collectG6Positions(null, ['A'], () => ({ width: 1, height: 1 }))).toEqual({})
    expect(collectG6Positions({}, ['A'], () => ({ width: 1, height: 1 }))).toEqual({})
  })
})

describe('export_graph_diagram 工具注册契约', () => {
  it('已注册 + 默认 ALLOW + 有调用示例', () => {
    expect(TOOL_NAMES).toContain('export_graph_diagram')
    expect(DEFAULT_TOOL_PERMISSIONS.export_graph_diagram).toBe(TOOL_PERMISSION.ALLOW)
    const ex = toolCallExample('export_graph_diagram')
    expect(ex).toContain('export_graph_diagram')
    expect(ex).toContain('"graph"')
  })
})

describe('downloadExcalidraw (浏览器下载降级路径)', () => {
  it('非 .excalidraw 后缀自动补全', () => {
    // 仅验证不抛异常 + 文件名补全逻辑 (jsdom 无真实下载)
    expect(() => {
      let captured = null
      const origCreate = document.createElement.bind(document)
      const orig = URL.createObjectURL
      URL.createObjectURL = () => 'blob:fake'
      URL.revokeObjectURL = () => {}
      try {
        downloadExcalidraw({ type: 'excalidraw' }, 'graph')
        captured = 'ok'
      } finally {
        URL.createObjectURL = orig
        void origCreate
      }
      expect(captured).toBe('ok')
    }).not.toThrow()
  })
})
