/**
 * AI 助手优化 (W?) 单测: 历史预算裁剪 + 对话持久化序列化
 *
 * buildApiHistory   — 长对话上下文不再无限膨胀 (超预算从头裁, 保证 user 开头)
 * serializeMessages — 持久化序列化 (丢图片段/附件原始数据, 保留文本与分支结构)
 * restoreMessages   — 脏数据防护 (非数组/缺 id/坏角色一律过滤)
 * fitPersistJson    — 持久化体积兜底 (超限从头丢最旧, 至少留 2 条)
 */
import { describe, it, expect } from 'vitest'
import {
  buildApiHistory,
  serializeMessages,
  restoreMessages,
  fitPersistJson,
} from '@/stores/chat'

function userMsg(text, id = `u_${text}`) {
  return { id, role: 'user', chunks: [{ type: 'content', content: text }], timestamp: 't' }
}

function assistantMsg(text, id = `a_${text}`) {
  return {
    id, role: 'assistant', timestamp: 't',
    versions: [{ id: `v_${id}`, chunks: [{ type: 'content', content: text }], timestamp: 't', trailingAfter: [] }],
    activeVersion: 0,
  }
}

describe('buildApiHistory (历史预算裁剪)', () => {
  it('预算内全量保留, assistant 剥 tool_call 后为纯文本', () => {
    const visible = [userMsg('你好'), assistantMsg('有什么可以帮你?')]
    const out = buildApiHistory(visible, 48000)
    expect(out).toHaveLength(2)
    expect(out[0]).toEqual({ role: 'user', content: '你好' })
    expect(out[1].role).toBe('assistant')
    expect(typeof out[1].content).toBe('string')
    expect(out[1].content).toContain('有什么可以帮你')
  })

  it('超预算从头裁最旧, 最新消息一定保留', () => {
    const visible = []
    for (let i = 0; i < 20; i++) {
      visible.push(userMsg(`问${i}: ${'x'.repeat(500)}`, `u${i}`))
      visible.push(assistantMsg(`答${i}: ${'y'.repeat(500)}`, `a${i}`))
    }
    const out = buildApiHistory(visible, 5000)
    expect(out.length).toBeGreaterThan(0)
    expect(out.length).toBeLessThan(visible.length)
    // 最新 assistant 内容保留
    expect(JSON.stringify(out)).toContain('答19')
    // 历史以 user 开头 (裁剪后不落在 assistant 中间)
    expect(out[0].role).toBe('user')
  })

  it('极端小预算也保留最后一条 user 及其后继 (当前回合永不丢)', () => {
    const visible = [userMsg('唯一问题'), assistantMsg('唯一回答')]
    const out = buildApiHistory(visible, 1)
    expect(out.length).toBeGreaterThanOrEqual(1)
    expect(JSON.stringify(out)).toContain('唯一问题')
  })

  it('多模态 user content (数组) 原样透传', () => {
    const multimodal = { id: 'u_m', role: 'user', timestamp: 't', content: [
      { type: 'text', text: '看这张图' },
      { type: 'image_url', image_url: { url: 'data:image/png;base64,xxx' } },
    ] }
    const out = buildApiHistory([multimodal], 48000)
    expect(Array.isArray(out[0].content)).toBe(true)
    expect(out[0].content[1].type).toBe('image_url')
  })
})

describe('serializeMessages / restoreMessages (对话持久化)', () => {
  it('序列化丢弃图片段与附件原始数据, 保留文本', () => {
    const msgs = [{
      id: 'u1', role: 'user', timestamp: 't',
      chunks: [],
      content: [
        { type: 'text', text: '看图提问' },
        { type: 'image_url', image_url: { url: 'data:image/png;base64,AAAA' } },
      ],
      _attachments: [{ id: 'att1', base64DataUrl: 'data:image/png;base64,AAAA' }],
    }]
    const out = serializeMessages(msgs)
    expect(out[0].content).toEqual([{ type: 'text', text: '看图提问' }])
    expect(out[0]._attachments).toBeUndefined()
    expect(JSON.stringify(out)).not.toContain('base64,AAAA')
  })

  it('序列化保留助手分支结构 (versions/trailingAfter)', () => {
    const msgs = [assistantMsg('v1 内容', 'a1')]
    const restored = restoreMessages(JSON.stringify(serializeMessages(msgs)))
    expect(restored).toHaveLength(1)
    expect(restored[0].versions).toHaveLength(1)
    expect(restored[0].versions[0].chunks[0].content).toBe('v1 内容')
  })

  it('restoreMessages 防脏数据: 坏 JSON/非数组/缺 id/坏角色全部过滤', () => {
    expect(restoreMessages('not json')).toEqual([])
    expect(restoreMessages('{"a":1}')).toEqual([])
    expect(restoreMessages(JSON.stringify([{ role: 'user' }, { id: 'x', role: 'system' }]))).toEqual([])
    expect(restoreMessages(JSON.stringify([{ id: 'ok', role: 'user', chunks: [] }]))).toHaveLength(1)
  })
})

describe('fitPersistJson (持久化体积兜底)', () => {
  it('超限从头丢最旧, 至少保留 2 条且体积达标', () => {
    const msgs = []
    for (let i = 0; i < 50; i++) {
      msgs.push(userMsg(`m${i}: ${'z'.repeat(2000)}`, `u${i}`))
    }
    const json = fitPersistJson(msgs, 50000)
    expect(json.length).toBeLessThanOrEqual(50000)
    const restored = JSON.parse(json)
    expect(restored.length).toBeGreaterThanOrEqual(2)
    // 最旧的被裁掉
    expect(json).not.toContain('m0:')
  })

  it('不超限原样返回', () => {
    const msgs = [userMsg('短'), assistantMsg('答')]
    const json = fitPersistJson(msgs, 1_500_000)
    expect(JSON.parse(json)).toHaveLength(2)
  })
})
