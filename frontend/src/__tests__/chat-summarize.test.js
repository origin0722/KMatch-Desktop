/**
 * 场景：工具结果摘要 (C1.4 单一源)。
 *
 * summarizeToolResults 此前在 sendMessage 与 regenMessage 各有一份副本 (regen 的是精简版,
 * 漏了实体清单/维度/失败用例)。C1.4 抽为单一源, 此测试守卫各工具类型的摘要格式。
 */
import { describe, expect, it } from 'vitest'
import { summarizeToolResults } from '@/stores/chat'

describe('summarizeToolResults (C1.4 单一源)', () => {
  it('错误结果: 报工具失败', () => {
    const out = summarizeToolResults([{ call: { tool: 'read_file' }, result: { error: '文件不存在' } }])
    expect(out).toContain('工具 read_file 失败: 文件不存在')
  })

  it('write_file 结果: 报写入字节', () => {
    const out = summarizeToolResults([{ call: { tool: 'write_file' }, result: { written: true, path: 'a.py', bytes: 42 } }])
    expect(out).toContain('a.py 已成功写入 (42 字节)')
  })

  it('read_file 结果: 含内容 (截断 6000 字符)', () => {
    const out = summarizeToolResults([{ call: { tool: 'read_file' }, result: { content: 'print(1)', path: 'a.py' } }])
    expect(out).toContain('print(1)')
    expect(out).toContain('a.py 内容')
  })

  it('generate_project_graph: 含实体清单', () => {
    const out = summarizeToolResults([{
      call: { tool: 'generate_project_graph' },
      result: { tool: 'generate_project_graph', sourcePath: 'a.py', written: false, stats: { module: 1, class: 2, function: 3, method: 4 }, entities: [{ kind: 'function', qualified_name: 'foo', line_start: 1, line_end: 2 }] },
    }])
    expect(out).toContain('模块1/类2/函数3/方法4')
    expect(out).toContain('function foo (行1-2)')
  })

  it('code_review: 含维度与 overall', () => {
    const out = summarizeToolResults([{
      call: { tool: 'code_review' },
      result: { tool: 'code_review', sourcePath: 'a.py', review: { verdict: 'pass', overall_score: 0.9, dimensions: { logic: { score: 0.9, issues: [] } }, retry_hint: '注意边界' } },
    }])
    expect(out).toContain('verdict=pass')
    expect(out).toContain('overall=90%')
    expect(out).toContain('logic: 90%')
    expect(out).toContain('注意边界')
  })

  it('code_test: 含通过率与覆盖率', () => {
    const out = summarizeToolResults([{
      call: { tool: 'code_test' },
      result: { tool: 'code_test', sourcePath: 'a.py', report: { summary: { passed: 3, total: 4 }, coverage: { line_coverage: 0.8, branch_coverage: 0.5, function_coverage: 1 }, failed_tests: [{ test_name: 'test_x', suggestion: '修 null' }] } },
    }])
    expect(out).toContain('3/4 通过')
    expect(out).toContain('行覆盖80%')
    expect(out).toContain('test_x: 修 null')
  })

  it('多结果用空行连接, 过滤空串', () => {
    const out = summarizeToolResults([
      { call: { tool: 'read_file' }, result: { content: 'a', path: 'a.py' } },
      { call: { tool: 'unknown' }, result: {} }, // 未知工具 → 空串, 被过滤
    ])
    expect(out).toContain('a.py 内容')
    expect(out).not.toContain('\n\n\n')
  })

  it('F7: 大文件截断 6000 字符时明示 (不再静默降级)', () => {
    const big = 'x'.repeat(7000)
    const out = summarizeToolResults([{ call: { tool: 'read_file' }, result: { content: big, path: 'a.py' } }])
    expect(out).toContain('内容已截断')
    expect(out).toContain('7000 字符')
    expect(out).not.toContain('x'.repeat(7000)) // 未全量塞回
  })

  // ---- 行号范围续读 (治"截断提示要求指明行号范围, 但工具无该参数 → 模型卡死") ----

  it('F7+: 截断提示给出 start_line/end_line 续读指引与已覆盖行区间', () => {
    const big = 'x'.repeat(7000)
    const out = summarizeToolResults([{
      call: { tool: 'read_file' },
      result: { content: big, path: 'a.py', total_lines: 300 },
    }])
    expect(out).toContain('start_line/end_line')
    expect(out).toContain('1-')
  })

  it('F7+: 行号范围结果头部标注行区间与文件总行数', () => {
    const out = summarizeToolResults([{
      call: { tool: 'read_file' },
      result: { content: 'line81\nline82', path: 'a.py', start_line: 81, end_line: 82, total_lines: 300 },
    }])
    expect(out).toContain('第 81-82 行')
    expect(out).toContain('文件共 300 行')
    expect(out).toContain('line81')
  })

  it('F7+: 行号范围结果仍超长 → 提示用更窄范围续读', () => {
    const out = summarizeToolResults([{
      call: { tool: 'read_file' },
      result: { content: 'x'.repeat(7000), path: 'a.py', start_line: 1, end_line: 200, total_lines: 300 },
    }])
    expect(out).toContain('第 1-200 行')
    expect(out).toContain('已截断')
    expect(out).toContain('start_line/end_line')
  })

  it('written 分支限定 write_file: generate_project_graph(written=true) 走 graph 摘要不被吞 (review 修正)', () => {
    const out = summarizeToolResults([{
      call: { tool: 'generate_project_graph' },
      result: { tool: 'generate_project_graph', sourcePath: 'a.py', written: true, stats: { module: 1, class: 0, function: 0, method: 0 }, entities: [] },
    }])
    expect(out).toContain('模块1')          // graph 摘要
    expect(out).not.toContain('已成功写入') // 不被 write_file 分支吞
  })

  // ---- P3 只读工具摘要 (此前缺失分支被静默丢弃 → LLM 看不到结果, 根因修复) ----

  it('search_knowledge: 含检索词/命中数/节点清单', () => {
    const out = summarizeToolResults([{
      call: { tool: 'search_knowledge' },
      result: {
        tool: 'search_knowledge', query: '列表推导式', count: 2,
        nodes: [{ node_id: 'PY-003', name: '列表推导式', summary: '简洁构造列表', difficulty: 2, category: '基础语法' }],
      },
    }])
    expect(out).toContain('知识检索结果 (列表推导式)')
    expect(out).toContain('命中 2 个节点')
    expect(out).toContain('PY-003 列表推导式')
    expect(out).toContain('基础语法 · 难度2')
  })

  it('get_learning_path: 含路径节点序列与预计学时', () => {
    const out = summarizeToolResults([{
      call: { tool: 'get_learning_path' },
      result: {
        tool: 'get_learning_path', count: 20, estimated_total_hours: 12.5,
        learning_path: [{ node_id: 'PY-001', name: '基础语法', difficulty: 1, category: '基础语法' }],
      },
    }])
    expect(out).toContain('个性化学习路径: 共 20 个节点, 预计 12.5h')
    expect(out).toContain('1. PY-001 基础语法')
  })

  it('get_knowledge_node: 含节点详情与摘要', () => {
    const out = summarizeToolResults([{
      call: { tool: 'get_knowledge_node' },
      result: { tool: 'get_knowledge_node', node_id: 'PY-002', name: '循环', difficulty: 2, category: '基础语法', summary: 'for/while' },
    }])
    expect(out).toContain('知识点 PY-002 循环')
    expect(out).toContain('摘要: for/while')
  })

  it('query_project_graph: 含实体/关系统计与清单', () => {
    const out = summarizeToolResults([{
      call: { tool: 'query_project_graph' },
      result: {
        tool: 'query_project_graph', project_id: 'p1', entity_count: 2, relation_count: 1,
        entities: [{ name: 'foo', kind: 'function', qualified_name: 'mod.foo' }],
        relations: [{ source: 'mod.foo', label: 'CALLS', target: 'mod.bar' }],
      },
    }])
    expect(out).toContain('项目图谱 p1: 2 实体 / 1 关系')
    expect(out).toContain('function mod.foo')
    expect(out).toContain('mod.foo CALLS mod.bar')
  })

  it('web_search: 含查询/结果数/标题链接摘要', () => {
    const out = summarizeToolResults([{
      call: { tool: 'web_search' },
      result: { tool: 'web_search', query: '装饰器', count: 1, results: [{ title: 'Python 装饰器', url: 'https://x.dev', snippet: '详解' }] },
    }])
    expect(out).toContain('联网搜索 (装饰器): 1 条结果')
    expect(out).toContain('Python 装饰器: https://x.dev')
  })

  it('search_weak_topics: 含薄弱点溯源与结果清单', () => {
    const out = summarizeToolResults([{
      call: { tool: 'search_weak_topics' },
      result: {
        tool: 'search_weak_topics', count: 1, weak_topics: ['PY-003'],
        results: [{ title: '装饰器教程', url: 'https://x.dev', snippet: '详解', target_node_id: 'PY-003' }],
      },
    }])
    expect(out).toContain('薄弱点联网搜索 (PY-003)')
    expect(out).toContain('装饰器教程: https://x.dev (PY-003)')
  })

  it('generate_learning_resources: 含生成数/节点数/落位提示', () => {
    const out = summarizeToolResults([{
      call: { tool: 'generate_learning_resources' },
      result: { tool: 'generate_learning_resources', strategy: 'scaffold', generated: 4, node_count: 2, hint: '资源已落入「学习资源」页' },
    }])
    expect(out).toContain('学习资源生成完成 (strategy=scaffold)')
    expect(out).toContain('新增 4 份资源, 覆盖 2 个节点')
  })

  it('hint 型降级结果 (未完成测评) 回喂 AI, 不再被静默丢弃', () => {
    const out = summarizeToolResults([{
      call: { tool: 'get_learning_path' },
      result: { tool: 'get_learning_path', hint: '用户尚未完成学情测评, 无法生成个性化学习路径。' },
    }])
    expect(out).toContain('工具 get_learning_path 提示')
    expect(out).toContain('尚未完成学情测评')
  })

  it('未知工具空结果仍被过滤 (不产生空行噪音)', () => {
    const out = summarizeToolResults([{ call: { tool: 'unknown' }, result: {} }])
    expect(out).toBe('')
  })
})
