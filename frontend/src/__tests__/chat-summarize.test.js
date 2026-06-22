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
})
