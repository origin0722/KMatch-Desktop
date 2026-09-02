/**
 * projectGraph store P2 单测: 项目自动解析 + 重启恢复
 *
 * mock @/api/project 的三个异步函数 (readProjectPyFiles/parseProjectFiles/getProjectGraph),
 * 保留 normalizeGraphResponse 真实现 (验证后端响应 -> store 格式转换)。
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('@/api/project', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    readProjectPyFiles: vi.fn(),
    parseProjectFiles: vi.fn(),
    getProjectGraph: vi.fn(),
    analyzeProject: vi.fn(),
  }
})

import { useProjectGraphStore } from '@/stores/projectGraph'
import { useWorkspaceStore } from '@/stores/workspace'
import { readProjectPyFiles, parseProjectFiles, getProjectGraph, normalizeGraphResponse, analyzeProject } from '@/api/project'

const FAKE_RESPONSE = {
  project_id: 'files-abc123',
  nodes: [
    { id: 'n1', label: 'foo', group: 'function', properties: { qualified_name: 'mod.foo', line_start: 1, line_end: 5 } },
    { id: 'n2', label: 'Bar', group: 'class', properties: { qualified_name: 'mod.Bar', line_start: 10, line_end: 20 } },
  ],
  edges: [{ source: 'n1', target: 'n2' }],
  stats: { function: 1, class: 1 },
  written_to_neo4j: true,
}

describe('normalizeGraphResponse (纯函数)', () => {
  it('终审回归: 边关系归一补 type 字段 (后端契约是 label, 边过滤/样式/chat 裁剪读 type)', () => {
    const r = normalizeGraphResponse({
      project_id: 'p', stats: {},
      nodes: [{ id: 'n1', label: 'a', group: 'function', properties: {} }],
      edges: [
        { source: 'n1', target: 'n2', label: 'CALLS' },
        { source: 'n2', target: 'n3', label: 'CONTAINS' },
      ],
    })
    expect(r.relations[0].type).toBe('CALLS')
    expect(r.relations[1].type).toBe('CONTAINS')
    expect(r.relations[0].label).toBe('CALLS') // 原字段保留
  })

  it('G6 nodes -> entities 扁平化, 字段名驼峰化', () => {
    const r = normalizeGraphResponse(FAKE_RESPONSE, '/proj')
    expect(r.projectId).toBe('files-abc123')
    expect(r.entities).toHaveLength(2)
    expect(r.entities[0]).toMatchObject({ id: 'n1', name: 'foo', kind: 'function', qualified_name: 'mod.foo', line_start: 1, line_end: 5 })
    expect(r.relations).toEqual([{ source: 'n1', target: 'n2' }])
    expect(r.written).toBe(true)
    expect(r.sourcePath).toBe('/proj')
  })

  it('空响应不抛错', () => {
    const r = normalizeGraphResponse(null)
    expect(r.entities).toEqual([])
    expect(r.projectId).toBeUndefined()
  })

  it('传递完整丰富属性 (docstring/params/external_calls/bases/decorators)', () => {
    const r = normalizeGraphResponse({
      project_id: 'p1',
      nodes: [{
        id: 'n1', label: 'foo', group: 'function',
        properties: {
          qualified_name: 'mod.foo',
          docstring: 'doc',
          params: [{ name: 'x', type: 'int' }],
          return_type: 'str',
          bases: ['Base'],
          decorators: ['@app.route'],
          external_calls: ['requests.get'],
          module_name: 'mod',
          source_code: 'def foo(): pass',
          is_method: true,
        },
      }],
      edges: [],
      stats: {},
    })
    const e = r.entities[0]
    expect(e.docstring).toBe('doc')
    expect(e.params).toEqual([{ name: 'x', type: 'int' }])
    expect(e.return_type).toBe('str')
    expect(e.bases).toEqual(['Base'])
    expect(e.decorators).toEqual(['@app.route'])
    expect(e.external_calls).toEqual(['requests.get'])
    expect(e.module_name).toBe('mod')
    expect(e.is_method).toBe(true)
  })

  it('stats key 映射: function_count -> function', () => {
    const r = normalizeGraphResponse({
      project_id: 'p1', nodes: [], edges: [],
      stats: {
        function_count: 5, class_count: 2, method_count: 3,
        module_count: 1, call_count: 10, relation_count: 15,
      },
    })
    expect(r.stats.function).toBe(5)
    expect(r.stats.class).toBe(2)
    expect(r.stats.method).toBe(3)
    expect(r.stats.module).toBe(1)
    expect(r.stats.call).toBe(10)
    expect(r.stats.relation).toBe(15)
  })

  it('JSON 字符串字段安全解析', () => {
    const r = normalizeGraphResponse({
      project_id: 'p1',
      nodes: [{
        id: 'n1', label: 'f', group: 'function',
        properties: {
          params: '[{"name":"a"}]',
          external_calls: '["requests.get"]',
          bases: '[]',
        },
      }],
      edges: [], stats: {},
    })
    expect(r.entities[0].params).toEqual([{ name: 'a' }])
    expect(r.entities[0].external_calls).toEqual(['requests.get'])
    expect(r.entities[0].bases).toEqual([])
  })
})

describe('projectGraph store - parseCurrentProject', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('成功: 读文件 -> 解析 -> setGraph + 存 localStorage', async () => {
    const ws = useWorkspaceStore()
    ws.root = '/fake/project'
    readProjectPyFiles.mockResolvedValue({ main: 'print("hi")' })
    parseProjectFiles.mockResolvedValue(FAKE_RESPONSE)

    const pg = useProjectGraphStore()
    await pg.parseCurrentProject()

    expect(pg.parsing).toBe(false)
    expect(pg.parseError).toBe(null)
    expect(pg.graph).toBeTruthy()
    expect(pg.graph.projectId).toBe('files-abc123')
    expect(pg.graph.entities).toHaveLength(2)
    expect(localStorage.getItem('kmatch-last-project-id')).toBe('files-abc123')
    expect(parseProjectFiles).toHaveBeenCalledWith({ main: 'print("hi")' })
  })

  it('无 .py 文件: parseError 提示, 不调 parse', async () => {
    const ws = useWorkspaceStore()
    ws.root = '/fake/empty'
    readProjectPyFiles.mockResolvedValue({})

    const pg = useProjectGraphStore()
    await pg.parseCurrentProject()

    expect(pg.parseError).toBe('项目中没有可解析的 .py 文件')
    expect(pg.graph).toBe(null)
    expect(parseProjectFiles).not.toHaveBeenCalled()
  })

  it('无项目根: 静默跳过', async () => {
    const ws = useWorkspaceStore()
    ws.root = null

    const pg = useProjectGraphStore()
    await pg.parseCurrentProject()

    expect(readProjectPyFiles).not.toHaveBeenCalled()
    expect(pg.graph).toBe(null)
  })

  it('解析 API 报错: parseError 记录', async () => {
    const ws = useWorkspaceStore()
    ws.root = '/fake/project'
    readProjectPyFiles.mockResolvedValue({ main: 'x = 1' })
    parseProjectFiles.mockRejectedValue(new Error('后端连接失败'))

    const pg = useProjectGraphStore()
    await pg.parseCurrentProject()

    expect(pg.parseError).toBe('后端连接失败')
    expect(pg.graph).toBe(null)
  })
})

describe('projectGraph store - restorePersisted', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('localStorage 有 id -> 从后端恢复图谱', async () => {
    localStorage.setItem('kmatch-last-project-id', 'files-old123')
    getProjectGraph.mockResolvedValue({
      project_id: 'files-old123',
      nodes: [{ id: 'n1', label: 'bar', group: 'class', properties: {} }],
      edges: [],
      stats: { class: 1 },
      written_to_neo4j: true,
    })

    const pg = useProjectGraphStore()
    await pg.restorePersisted()

    expect(pg.graph).toBeTruthy()
    expect(pg.graph.projectId).toBe('files-old123')
    expect(pg.graph.entities[0].name).toBe('bar')
  })

  it('已有图谱 -> 跳过 (不覆盖)', async () => {
    const pg = useProjectGraphStore()
    pg.setGraph({ projectId: 'existing', entities: [], relations: [], stats: {}, sourcePath: '', written: true }, '/proj')

    await pg.restorePersisted()
    expect(getProjectGraph).not.toHaveBeenCalled()
    expect(pg.graph.projectId).toBe('existing')
  })

  it('后端 404 -> 清 localStorage id (过期清理)', async () => {
    localStorage.setItem('kmatch-last-project-id', 'files-gone')
    getProjectGraph.mockRejectedValue(new Error('HTTP 404'))

    const pg = useProjectGraphStore()
    await pg.restorePersisted()

    expect(pg.graph).toBe(null)
    expect(localStorage.getItem('kmatch-last-project-id')).toBe(null)
  })

  it('无 localStorage id -> 跳过', async () => {
    const pg = useProjectGraphStore()
    await pg.restorePersisted()
    expect(getProjectGraph).not.toHaveBeenCalled()
  })
})

describe('projectGraph store - analyze (P3 深度分析)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('成功: 调 analyzeProject -> analysis 填充 + web_resources 流入 learningResources', async () => {
    const pg = useProjectGraphStore()
    pg.setGraph({ projectId: 'demo', entities: [], relations: [], stats: {}, sourcePath: '', written: true }, '/p')

    analyzeProject.mockResolvedValue({
      summary: '一个爬虫项目',
      architecture: { pattern: '单体脚本', entry_points: ['crawl'], key_modules: [] },
      complexity: { level: '低', note: '简单' },
      recommendations: ['学 requests'],
      tech_stack: ['requests', 'bs4'],
      web_resources: [{ title: '教程', url: 'https://ex.com', snippet: '示例', tech: 'requests' }],
    })

    await pg.analyze()

    expect(pg.analyzing).toBe(false)
    expect(pg.analysis).toBeTruthy()
    expect(pg.analysis.summary).toBe('一个爬虫项目')
    expect(analyzeProject).toHaveBeenCalledWith('demo', '')
  })

  it('无图谱 -> 提示, 不调 API', async () => {
    const pg = useProjectGraphStore()
    await pg.analyze()
    expect(analyzeProject).not.toHaveBeenCalled()
  })

  it('API 报错 -> analyzing 复位, analysis 不变', async () => {
    const pg = useProjectGraphStore()
    pg.setGraph({ projectId: 'demo', entities: [], relations: [], stats: {}, sourcePath: '', written: true }, '/p')
    analyzeProject.mockRejectedValue({ message: 'LLM 未配置' })

    await pg.analyze()
    expect(pg.analyzing).toBe(false)
    expect(pg.analysis).toBe(null)
  })
})

describe('projectGraph store - 历史回看 (openFromHistory 备份 / 返回当前)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.clearAllMocks()
  })

  const histResponse = (pid) => ({
    project_id: pid,
    nodes: [{ id: 'h1', label: 'baz', group: 'function', properties: {} }],
    edges: [],
    stats: { function: 1 },
    written_to_neo4j: true,
  })

  it('openFromHistory 备份当前项目图谱, backToCurrentProject 一键还原', async () => {
    const pg = useProjectGraphStore()
    pg.setGraph({ projectId: 'live-1', entities: [{ id: 'e1' }], relations: [], stats: {}, written: true }, '/live')

    getProjectGraph.mockResolvedValue(histResponse('hist-9'))
    const ok = await pg.openFromHistory('hist-9', '旧项目')
    expect(ok).toBe(true)
    expect(pg.historyViewing).toEqual({ projectId: 'hist-9', name: '旧项目' })
    expect(pg.graph.projectId).toBe('hist-9')

    pg.backToCurrentProject()
    expect(pg.historyViewing).toBe(null)
    expect(pg.graph.projectId).toBe('live-1')
    expect(pg.graph.entities[0].id).toBe('e1')
  })

  it('链式浏览历史不覆盖最初备份; 真实解析 (setGraph 默认) 清除回看态', async () => {
    const pg = useProjectGraphStore()
    pg.setGraph({ projectId: 'live-1', entities: [], relations: [], stats: {}, written: true }, '/live')

    getProjectGraph.mockResolvedValue(histResponse('hist-A'))
    await pg.openFromHistory('hist-A', 'A')
    getProjectGraph.mockResolvedValue(histResponse('hist-B'))
    await pg.openFromHistory('hist-B', 'B')
    expect(pg.historyViewing.projectId).toBe('hist-B')

    pg.backToCurrentProject()
    expect(pg.graph.projectId).toBe('live-1') // 仍还原到最初 live, 而非 hist-A

    pg.setGraph({ projectId: 'live-2', entities: [], relations: [], stats: {}, written: true }, '/live2')
    expect(pg.historyViewing).toBe(null)
    expect(pg.graph.projectId).toBe('live-2')
  })

  it('无 live 图谱时进历史浏览 (备份为空), 返回即退出回看清空回空态', async () => {
    const pg = useProjectGraphStore()
    getProjectGraph.mockResolvedValue({
      project_id: 'hist-1', stats: {},
      nodes: [{ id: 'h1', label: 'x', group: 'function', properties: { module_name: 'other' } }],
      edges: [],
    })
    await pg.openFromHistory('hist-1', '仅历史')
    expect(pg.historyViewing.projectId).toBe('hist-1')

    // 无备份 (进历史前无当前图谱) → 返回 = 退出回看并清空 (issue: 此前 no-op, "返回"键点了没反应)
    pg.backToCurrentProject()
    expect(pg.historyViewing).toBe(null)
    expect(pg.graph).toBe(null)
  })
})

// ============================================================
// v1.3.3 stale 检测修复: 改动文件 ∈ 图谱覆盖模块集 → 标过期 (原比较项目根===文件路径永假)
// ============================================================
describe('projectGraph store - stale 检测 (v1.3.3 修复)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.clearAllMocks()
  })

  const entitiesWithModules = [
    { id: 'e1', module_name: 'main' },
    { id: 'e2', module_name: 'pkg.mod' },
  ]

  it('改动文件命中覆盖模块集 → stale=true; 未命中文件/非 .py 不误标', () => {
    const pg = useProjectGraphStore()
    pg.setGraph({ projectId: 'p1', entities: entitiesWithModules, relations: [], stats: {}, written: true }, '/proj')

    pg.markStale('main.py')           // 命中 main 模块
    expect(pg.stale).toBe(true)
  })

  it('修复回归: 项目根路径 !== 文件路径, 改动具体文件也能标过期 (原 bug 永假)', () => {
    const pg = useProjectGraphStore()
    pg.setGraph({ projectId: 'p1', entities: entitiesWithModules, relations: [], stats: {}, written: true }, '/proj')
    expect(pg.stale).toBe(false)

    pg.markStale('pkg/mod.py')        // 子目录文件, 原 bug 下 g.sourcePath==='/proj' 永不等于它
    expect(pg.stale).toBe(true)
  })

  it('无关文件不误标; setGraph 新图谱清过期; 兼容旧 sourcePath 全等语义', () => {
    const pg = useProjectGraphStore()
    pg.setGraph({ projectId: 'p1', entities: entitiesWithModules, relations: [], stats: {}, written: true }, '/proj')

    pg.markStale('other.py')          // 不在覆盖集
    expect(pg.stale).toBe(false)

    pg.markStale('main.py')
    expect(pg.stale).toBe(true)
    pg.setGraph({ projectId: 'p1', entities: entitiesWithModules, relations: [], stats: {}, written: true }, '/proj')
    expect(pg.stale).toBe(false)      // 新图谱清过期

    pg.markStale('/proj')             // 旧语义: 传项目根
    expect(pg.stale).toBe(true)
  })
})

describe('projectGraph store - 历史回看期 stale 忽略 (终审修复)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('回看历史时 markStale 不误标; 返回当前图谱还原备份的真实 stale', async () => {
    const pg = useProjectGraphStore()
    pg.setGraph({ projectId: 'live', entities: [{ id: 'e1', module_name: 'utils' }], relations: [], stats: {}, written: true }, '/live')
    getProjectGraph.mockResolvedValue({
      project_id: 'hist-1', stats: {},
      nodes: [{ id: 'h1', label: 'x', group: 'function', properties: { module_name: 'other' } }],
      edges: [],
    })
    await pg.openFromHistory('hist-1', '历史B') // coveredModules 换成历史项目 B 的
    expect(pg.historyViewing.projectId).toBe('hist-1')

    // 改动当前项目 A 的 utils 模块 (与历史 B 覆盖集同名) — 回看期不得误标
    pg.markStale('utils.py')
    expect(pg.stale).toBe(false)

    pg.backToCurrentProject()
    expect(pg.historyViewing).toBe(null)
    // 返回后 watcher 再报同一文件 → 正确标当前项目过期
    pg.markStale('utils.py')
    expect(pg.stale).toBe(true)
  })
})
