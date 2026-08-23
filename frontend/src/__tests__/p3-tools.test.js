/**
 * P3 新增只读工具单测: search_knowledge / get_learning_path / query_project_graph
 *
 * 验证 registry 单一源一致性: 工具定义/权限默认/调用示例/广告文案。
 * 执行器逻辑 (chat.js _executeTool 闭包) 依赖 SSE 工具循环, 此处测 registry 层契约。
 */
import { describe, it, expect } from 'vitest'
import {
  TOOLS,
  TOOL_NAMES,
  DEFAULT_TOOL_PERMISSIONS,
  TOOL_PERMISSION,
  buildToolBlock,
  toolCallExample,
  buildAdvertisedToolNames,
} from '@/ide/tools/registry'

const NEW_TOOLS = ['search_knowledge', 'get_learning_path', 'query_project_graph']

describe('P3 新增只读工具 - registry 契约', () => {
  it('3 个新工具均已注册', () => {
    for (const name of NEW_TOOLS) {
      expect(TOOL_NAMES).toContain(name)
      const def = TOOLS.find((t) => t.name === name)
      expect(def).toBeTruthy()
      expect(def.description).toBeTruthy()
      expect(def.parameters).toBeTruthy()
    }
  })

  it('新工具默认权限 ALLOW (只读, 无副作用)', () => {
    for (const name of NEW_TOOLS) {
      expect(DEFAULT_TOOL_PERMISSIONS[name]).toBe(TOOL_PERMISSION.ALLOW)
    }
  })

  it('新工具均有调用示例', () => {
    for (const name of NEW_TOOLS) {
      const ex = toolCallExample(name)
      expect(ex).toBeTruthy()
      expect(ex).toContain(name)
    }
  })

  it('search_knowledge 示例含 query 参数', () => {
    expect(toolCallExample('search_knowledge')).toContain('"query"')
    expect(toolCallExample('search_knowledge')).toContain('"top_k"')
  })

  it('get_learning_path 示例含 level 参数', () => {
    expect(toolCallExample('get_learning_path')).toContain('"level"')
  })

  it('buildToolBlock 广告新工具 (全 allow 时)', () => {
    const allAllow = (tool) => TOOL_PERMISSION.ALLOW
    const advertised = buildAdvertisedToolNames(allAllow)
    for (const name of NEW_TOOLS) {
      expect(advertised).toContain(name)
    }

    const block = buildToolBlock(NEW_TOOLS)
    expect(block).toContain('search_knowledge')
    expect(block).toContain('get_learning_path')
    expect(block).toContain('query_project_graph')
    // 广告文案含查证引导
    expect(block).toContain('优先调它查证')
  })

  it('buildToolBlock 不广告未允许的工具', () => {
    const block = buildToolBlock(['read_file'])
    expect(block).not.toContain('"tool": "search_knowledge"')
    expect(block).not.toContain('"tool": "get_learning_path"')
    expect(block).not.toContain('"tool": "query_project_graph"')
  })
})

describe('P3 generate_learning_resources 降级文案', () => {
  it('广告文案含"未完成测评引导"语义', () => {
    const block = buildToolBlock(['generate_learning_resources'])
    expect(block).toContain('学情测评')
    expect(block).toContain('引导先去学习会话')
  })
})

describe('P4 search_weak_topics (issue-68: 按薄弱点联网搜索)', () => {
  it('已注册 + 默认 ALLOW + 有示例', () => {
    expect(TOOL_NAMES).toContain('search_weak_topics')
    expect(DEFAULT_TOOL_PERMISSIONS.search_weak_topics).toBe(TOOL_PERMISSION.ALLOW)
    const ex = toolCallExample('search_weak_topics')
    expect(ex).toContain('search_weak_topics')
    expect(ex).toContain('max_per_topic')
  })

  it('广告文案强调"优先于泛泛 web_search"', () => {
    const block = buildToolBlock(['search_weak_topics', 'web_search'])
    expect(block).toContain('优先于泛泛的 web_search')
  })
})
