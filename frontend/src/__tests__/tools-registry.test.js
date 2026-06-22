/**
 * 场景：工具注册中心单一源（C1.2）。
 *
 * 验证 TOOLS / DEFAULT_TOOL_PERMISSIONS / TOOL_NAMES 同源一致，
 * 以及广告决策（shouldAdvertiseTool/buildAdvertisedToolNames）、权限门（toolPermissionError）、
 * 提示词工具块（buildToolBlock）行为。增删工具只改 registry，本测试守卫其一致性。
 */
import { describe, expect, it } from 'vitest'
import {
  TOOLS,
  TOOL_NAMES,
  TOOL_PERMISSION,
  DEFAULT_TOOL_PERMISSIONS,
  shouldAdvertiseTool,
  buildAdvertisedToolNames,
  toolPermissionError,
  buildToolBlock,
  toolCallExample,
} from '@/ide/tools/registry'

describe('tools registry (C1.2 单一源)', () => {
  it('TOOL_NAMES 与 TOOLS / DEFAULT_TOOL_PERMISSIONS 三方一致', () => {
    const toolNames = TOOLS.map((t) => t.name)
    expect(TOOL_NAMES).toEqual(toolNames)
    expect(Object.keys(DEFAULT_TOOL_PERMISSIONS).sort()).toEqual([...toolNames].sort())
  })

  it('每个工具都有 name/description/parameters 与调用示例', () => {
    for (const t of TOOLS) {
      expect(t.name).toBeTruthy()
      expect(t.description).toBeTruthy()
      expect(t.parameters).toBeTruthy()
      expect(toolCallExample(t.name)).toBeTruthy()
    }
  })

  it('shouldAdvertiseTool: allow 恒广告, write_file 在 ask 下广告, 其余 ask/deny 不广告', () => {
    expect(shouldAdvertiseTool('read_file', 'allow')).toBe(true)
    expect(shouldAdvertiseTool('write_file', 'ask')).toBe(true)
    expect(shouldAdvertiseTool('write_file', 'allow')).toBe(true)
    expect(shouldAdvertiseTool('code_review', 'ask')).toBe(false)
    expect(shouldAdvertiseTool('read_file', 'deny')).toBe(false)
  })

  it('buildAdvertisedToolNames 按权限决策过滤', () => {
    const perm = (tool) => (tool === 'code_test' ? 'deny' : (DEFAULT_TOOL_PERMISSIONS[tool] || 'deny'))
    const advertised = buildAdvertisedToolNames(perm)
    expect(advertised).toContain('read_file')
    expect(advertised).toContain('write_file') // ask 下仍广告
    expect(advertised).not.toContain('code_test')
  })

  it('toolPermissionError: deny 报禁用, 非 write_file 的 ask 报需确认, 其余放行', () => {
    expect(toolPermissionError('read_file', 'deny')).toContain('已在 AI 设置中禁用')
    expect(toolPermissionError('code_review', 'ask')).toContain('需要用户确认')
    expect(toolPermissionError('write_file', 'ask')).toBeNull()
    expect(toolPermissionError('read_file', 'allow')).toBeNull()
  })

  it('buildToolBlock 含允许工具的示例与 503 提示', () => {
    const block = buildToolBlock(['read_file', 'write_file'])
    expect(block).toContain('## 可用工具')
    expect(block).toContain('read_file')
    expect(block).toContain('write_file')
    expect(block).toContain('503')
    // 未允许的工具不出示例
    expect(block).not.toContain('"tool": "code_test"')
  })

  it('buildToolBlock 无工具时显示占位', () => {
    const block = buildToolBlock([])
    expect(block).toContain('(当前没有可用工具)')
  })
})
