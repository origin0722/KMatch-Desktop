import { describe, expect, it } from 'vitest'
import {
  appendTextChunk,
  contentTextOf,
  thinkTextOf,
  splitToolCallChunks,
  stripToolCalls,
} from '@/stores/chat'

describe('chat chunk model helpers (借鉴 Apix MessageChunk)', () => {
  it('appendTextChunk 合并相邻同类型, 不同类型分块', () => {
    const chunks = []
    appendTextChunk(chunks, 'think', '推理')
    appendTextChunk(chunks, 'think', '继续') // 合并
    appendTextChunk(chunks, 'content', '正文')
    appendTextChunk(chunks, 'content', '续') // 合并
    expect(chunks).toEqual([
      { type: 'think', content: '推理继续' },
      { type: 'content', content: '正文续' },
    ])
  })

  it('appendTextChunk 空文本不追加', () => {
    const chunks = [{ type: 'content', content: 'x' }]
    appendTextChunk(chunks, 'content', '')
    expect(chunks).toHaveLength(1)
  })

  it('contentTextOf / thinkTextOf 拼接对应类型 chunk', () => {
    const msg = {
      chunks: [
        { type: 'think', content: 'A' },
        { type: 'content', content: 'B' },
        { type: 'think', content: 'C' },
        { type: 'tool_call', tool: 'read_file', status: 'completed' },
      ],
    }
    expect(contentTextOf(msg)).toBe('B')
    expect(thinkTextOf(msg)).toBe('AC')
    expect(contentTextOf(null)).toBe('')
    expect(thinkTextOf({})).toBe('')
  })

  it('splitToolCallChunks 把 content 切成 content? + tool_call + content? 段', () => {
    const text = '请读取文件\n```tool_call\n{"tool":"read_file","path":"a.py"}\n```\n谢谢'
    const chunks = splitToolCallChunks(text)
    expect(chunks).toHaveLength(3)
    expect(chunks[0]).toEqual({ type: 'content', content: '请读取文件\n' })
    expect(chunks[1].type).toBe('tool_call')
    expect(chunks[1].tool).toBe('read_file')
    expect(chunks[1].args).toEqual({ tool: 'read_file', path: 'a.py' })
    expect(chunks[1].status).toBe('pending')
    expect(chunks[2]).toEqual({ type: 'content', content: '\n谢谢' })
  })

  it('splitToolCallChunks 无 tool_call 时整段作为单个 content chunk', () => {
    expect(splitToolCallChunks('纯文本无工具')).toEqual([{ type: 'content', content: '纯文本无工具' }])
    expect(splitToolCallChunks('')).toEqual([])
  })

  it('splitToolCallChunks 多个 tool_call 块都切出', () => {
    const text = '```tool_call\n{"tool":"read_file","path":"a.py"}\n```\n中间\n```tool_call\n{"tool":"list_directory"}\n```'
    const chunks = splitToolCallChunks(text)
    expect(chunks.filter((c) => c.type === 'tool_call')).toHaveLength(2)
    expect(chunks.map((c) => c.type)).toEqual(['tool_call', 'content', 'tool_call'])
  })

  it('splitToolCallChunks 与 stripToolCalls 互补 (assistant 历史序列化)', () => {
    const text = '前\n```tool_call\n{"tool":"read_file","path":"a.py"}\n```\n后'
    // split 出的 content 段拼起来应等于 stripToolCalls 结果 (trim 差异由调用方处理)
    const contentOnly = splitToolCallChunks(text).filter((c) => c.type === 'content').map((c) => c.content).join('')
    expect(contentOnly.trim()).toBe(stripToolCalls(text))
  })
})
