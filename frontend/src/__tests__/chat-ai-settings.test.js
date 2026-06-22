/**
 * 场景：chat 与 aiSettings 的集成点——系统提示词与工具集成（阶段2/4c/6a）。
 *
 * 测 chat.js 暴露的纯 helper：
 *  - buildSystemPrompt：注入用户记忆、推理指令（reasoningMode auto/fast/deep → thinking 字段），
 *    导学模式下走 Socratic 分支（赛题(4)②）；
 *  - buildAdvertisedToolNames：按权限（allow/ask）对外广告工具名，deny 不暴露；
 *  - parseToolCalls / stripToolCalls：工具调用 fence 解析与后端序列化剥离；
 *  - toolPermissionError：权限门决策（write_file 默认 ask）。
 */
import { describe, expect, it } from 'vitest'
import { buildAdvertisedToolNames, buildSystemPrompt, parseToolCalls, stripToolCalls, toolPermissionError } from '@/stores/chat'

describe('chat AI settings integration helpers', () => {
  it('injects enabled memory and reasoning instruction into normal prompt', () => {
    const prompt = buildSystemPrompt({
      memoriesBlock: '\n\n## 用户记忆\n- [preference] 回答风格: 先讲思路再给代码',
      reasoningInstruction: '思考模式: 深度。请更仔细地分析问题。',
    })

    expect(prompt.content).toContain('## 用户记忆')
    expect(prompt.content).toContain('先讲思路再给代码')
    expect(prompt.content).toContain('思考模式: 深度')
  })

  it('injects enabled memory and reasoning instruction into tutor prompt', () => {
    const prompt = buildSystemPrompt({
      tutorMode: true,
      memoriesBlock: '\n\n## 用户记忆\n- [learning] 学情: 递归薄弱',
      reasoningInstruction: '思考模式: 快速。请直接给出简洁实用的回答。',
      profile: { theory_level: 2, practice_level: 3, weak_topics: ['递归'] },
    })

    expect(prompt.content).toContain('## 用户记忆')
    expect(prompt.content).toContain('递归薄弱')
    expect(prompt.content).toContain('思考模式: 快速')
    expect(prompt.content).toContain('启发式导学助手')
  })

  it('does not advertise tools when prompt context has no filtered allowlist', () => {
    const prompt = buildSystemPrompt({})

    expect(prompt.content).toContain('(当前没有可用工具)')
    expect(prompt.content).not.toContain('code_review')
    expect(prompt.content).not.toContain('code_test')
  })

  it('filters denied tools from tool prompt text', () => {
    const prompt = buildSystemPrompt({
      allowedTools: ['read_file', 'write_file'],
    })

    expect(prompt.content).toContain('"read_file"')
    expect(prompt.content).toContain('"write_file"')
    expect(prompt.content).not.toContain('code_test')
    expect(prompt.content).not.toContain('code_review')
  })

  it('advertises allow tools and write_file ask, but hides non-write ask tools', () => {
    const allowedTools = buildAdvertisedToolNames((tool) => ({
      read_file: 'allow',
      list_directory: 'deny',
      write_file: 'ask',
      generate_project_graph: 'allow',
      code_review: 'ask',
      code_test: 'ask',
    }[tool] || 'deny'))
    const prompt = buildSystemPrompt({ allowedTools })

    expect(allowedTools).toEqual(['read_file', 'write_file', 'generate_project_graph'])
    expect(prompt.content).toContain('"read_file"')
    expect(prompt.content).toContain('"write_file"')
    expect(prompt.content).toContain('"generate_project_graph"')
    expect(prompt.content).not.toContain('code_review')
    expect(prompt.content).not.toContain('code_test')
    expect(prompt.content).not.toContain('list_directory')
  })

  it('blocks ask non-write tools while preserving write_file approval path', () => {
    expect(toolPermissionError('code_review', 'ask')).toContain('需要用户确认')
    expect(toolPermissionError('code_test', 'ask')).toContain('需要用户确认')
    expect(toolPermissionError('write_file', 'ask')).toBeNull()
    expect(toolPermissionError('read_file', 'allow')).toBeNull()
    expect(toolPermissionError('read_file', 'deny')).toContain('已在 AI 设置中禁用')
  })

  it('keeps tool parsing helpers stable', () => {
    const text = '请读取文件\n```tool_call\n{"tool":"read_file","path":"a.py"}\n```\n谢谢'
    expect(parseToolCalls(text)).toEqual([{ tool: 'read_file', path: 'a.py' }])
    expect(stripToolCalls(text)).toBe('请读取文件\n\n谢谢')
  })
})
