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
      data: {
        summary: '一个爬虫项目',
        architecture: { pattern: '单体脚本', entry_points: ['crawl'], key_modules: [] },
        complexity: { level: '低', note: '简单' },
        recommendations: ['学 requests'],
        tech_stack: ['requests', 'bs4'],
        web_resources: [{ title: '教程', url: 'https://ex.com', snippet: '示例', tech: 'requests' }],
      },
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
