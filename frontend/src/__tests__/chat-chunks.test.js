/**
 * 场景：chat 消息 chunk 模型纯函数（阶段6b，借鉴 Apix MessageChunk）。
 *
 * 由 Chunk 判别联合驱动：{type:'think'|'content',content} | {type:'tool_call',...}。
 * 这里测纯 helper，不挂 store：
 *  - appendTextChunk：相邻同类型 think/content 合并，不同类型分块；
 *  - contentTextOf / thinkTextOf：从 chunks 抽出可读文本；
 *  - splitToolCallChunks：把 content 中 ```tool_call fence 拆成内联 tool_call chunk；
 *  - stripToolCalls：序列化给后端时剥离工具调用（后端契约不变）。
 */
import { describe, expect, it } from 'vitest'
import {
  appendTextChunk,
  contentTextOf,
  thinkTextOf,
  splitToolCallChunks,
  stripToolCalls,
  assistantApiContent,
  formatChatStats,
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

  it('F6: 坏 JSON 的 tool_call 标 _malformed + _raw, 不静默丢', () => {
    const text = '```tool_call\n{not valid json}\n```'
    const chunks = splitToolCallChunks(text)
    expect(chunks).toHaveLength(1)
    expect(chunks[0].type).toBe('tool_call')
    expect(chunks[0].tool).toBe('_malformed')
    expect(chunks[0]._malformed).toBeTruthy() // 含解析错误信息
    expect(chunks[0].args._raw).toBe('{not valid json}')
    expect(chunks[0].status).toBe('pending')
  })

  it('F6: 有效 JSON 缺 tool 字段也标 _malformed (不 fallthrough 成权限报错)', () => {
    const text = '```tool_call\n{"path":"a.py"}\n```'
    const chunks = splitToolCallChunks(text)
    expect(chunks[0].tool).toBe('_malformed')
    expect(chunks[0]._malformed).toBeTruthy()
  })

  it('assistantApiContent: 剥离工具调用; 全工具调用消息给占位而非空串', () => {
    const msg = { role: 'assistant', chunks: [
      { type: 'content', content: '前 ```tool_call\n{"tool":"read_file","path":"a.py"}\n``` 后' },
    ] }
    expect(assistantApiContent(msg)).toBe('前  后')

    const onlyTool = { role: 'assistant', chunks: [
      { type: 'content', content: '```tool_call\n{"tool":"read_file","path":"a.py"}\n```' },
    ] }
    const c = assistantApiContent(onlyTool)
    expect(c).not.toBe('')
    expect(c).toContain('工具调用已执行')
  })

  it('formatChatStats: 首 token/速率/缓存命中/输入输出 token 格式化', () => {
    expect(formatChatStats(null)).toBe('')
    const text = formatChatStats({
      firstTokenSec: 2.5, tokPerSec: 117, cacheHitPct: 99.8,
      promptTokens: 324_000_000, completionTokens: 1234,
    })
    expect(text).toContain('首 token 2.5s')
    expect(text).toContain('117 tok/s')
    expect(text).toContain('缓存命中 99.8%')
    expect(text).toContain('输入 324.0M tok')
    expect(text).toContain('输出 1.2k tok')
  })
})

describe('contentTextOf 适配 versions', () => {
  it('旧消息 (无 versions) 仍读 chunks', () => {
    const msg = { role: 'assistant', chunks: [{ type: 'content', content: 'old' }] }
    expect(contentTextOf(msg)).toBe('old')
  })

  it('新版助手消息读 activeVersion 的 chunks', () => {
    const msg = {
      role: 'assistant',
      versions: [
        { id: 'v1', chunks: [{ type: 'content', content: 'first' }] },
        { id: 'v2', chunks: [{ type: 'content', content: 'second' }] },
      ],
      activeVersion: 1,
    }
    expect(contentTextOf(msg)).toBe('second')
  })

  it('activeVersion=0 读第一版', () => {
    const msg = {
      role: 'assistant',
      versions: [
        { id: 'v1', chunks: [{ type: 'content', content: 'first' }] },
        { id: 'v2', chunks: [{ type: 'content', content: 'second' }] },
      ],
      activeVersion: 0,
    }
    expect(contentTextOf(msg)).toBe('first')
  })

  it('thinkTextOf 同理读 activeVersion', () => {
    const msg = {
      role: 'assistant',
      versions: [
        { id: 'v1', chunks: [{ type: 'think', content: 'think1' }] },
      ],
      activeVersion: 0,
    }
    expect(thinkTextOf(msg)).toBe('think1')
  })
})
