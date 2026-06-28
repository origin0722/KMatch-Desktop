/**
 * Chat 消息模型纯函数 (C1.5, 从 chat.js 抽出)。
 *
 * Chunk 判别联合 (借鉴 Apix MessageChunk, ADR-0002):
 *   { type: 'think',    content: string }
 *   { type: 'content',  content: string }
 *   { type: 'tool_call', id, tool, args, status: 'pending'|'in_progress'|'completed'|'error', result? }
 *
 * 相邻同类型 think/content 合并; tool_call 带状态机。
 * 助手消息读 versions[activeVersion].chunks; 旧消息/用户消息读 msg.chunks (activeChunksOf 统一适配)。
 *
 * 纯函数, 不依赖 store/响应式, 可独立单测 (chat-chunks.test.js)。
 */

let _tcCounter = 0

/** 从文本中解析所有 ```tool_call fence 为调用对象数组 (坏 JSON 跳过)。 */
export function parseToolCalls(text) {
  const re = /```tool_call\n([\s\S]*?)```/g
  const calls = []
  let m
  while ((m = re.exec(text)) !== null) {
    try {
      calls.push(JSON.parse(m[1].trim()))
    } catch { /* skip malformed */ }
  }
  return calls
}

/** 剥离文本中的 ```tool_call fence (供 assistant 历史序列化给后端, 后端契约不变)。 */
export function stripToolCalls(text) {
  if (!text) return ''
  return text.replace(/```tool_call\n[\s\S]*?```/g, '').trim()
}

/** 向 chunks 末尾追加文本 chunk, 末尾同类型 (think/content) 合并 (Apix 相邻合并)。 */
export function appendTextChunk(chunks, type, text) {
  if (!text) return
  const last = chunks[chunks.length - 1]
  if (last && last.type === type && (type === 'think' || type === 'content')) {
    last.content += text
  } else {
    chunks.push({ type, content: text })
  }
}

/** 取消息当前生效的 chunks (助手消息读 versions[activeVersion], 旧消息/用户消息读 chunks)。 */
export function activeChunksOf(msg) {
  if (!msg) return []
  if (msg.role === 'assistant' && Array.isArray(msg.versions)) {
    const v = msg.versions[msg.activeVersion ?? 0]
    return v?.chunks ?? []
  }
  return Array.isArray(msg.chunks) ? msg.chunks : []
}

/** 拼接消息当前 version 的 content chunk 文本 (供 API 历史 + MarkdownViewer)。 */
export function contentTextOf(msg) {
  // 兼容: msg.content 是数组 (user 多模态) → 拼接 type==='text' 段
  if (Array.isArray(msg?.content)) {
    return msg.content.filter((p) => p?.type === 'text').map((p) => p.text || '').join('')
  }
  return activeChunksOf(msg).filter((c) => c.type === 'content').map((c) => c.content).join('')
}

/** 拼接消息当前 version 的 think chunk 文本。 */
export function thinkTextOf(msg) {
  return activeChunksOf(msg).filter((c) => c.type === 'think').map((c) => c.content).join('')
}

/**
 * 把一段 content 文本按 ```tool_call 块切成 [content?, tool_call{status:'pending'}, content?, ...] 段。
 * 复用 parseToolCalls 的正则, 但保留位置信息以便分段。
 */
export function splitToolCallChunks(contentText) {
  if (!contentText) return []
  const chunks = []
  const re = /```tool_call\n([\s\S]*?)```/g
  let last = 0
  let m
  while ((m = re.exec(contentText)) !== null) {
    const before = contentText.slice(last, m.index)
    if (before.trim()) chunks.push({ type: 'content', content: before })
    let call
    let malformed = null
    const raw = m[1].trim()
    try {
      call = JSON.parse(raw)
    } catch (e) {
      // F6: 坏 JSON 不再静默丢——生成可见的 _malformed tool_call, 执行时给明确错误
      call = { tool: '_malformed', _raw: raw }
      malformed = e.message || 'JSON 解析失败'
    }
    // F6: 有效 JSON 但缺 tool 字段 (或非字符串) 也算格式错误, 否则会 fallthrough 成混淆的权限报错
    if (!malformed && (typeof call.tool !== 'string' || !call.tool)) {
      malformed = '缺少 tool 字段'
      call = { tool: '_malformed', _raw: raw, _orig: call }
    }
    chunks.push({
      type: 'tool_call',
      id: `tc_${++_tcCounter}`,
      tool: call.tool || '_malformed',
      args: call,
      status: 'pending',
      _malformed: malformed, // 非空表示格式错误, _executeTool 据此报错
    })
    last = re.lastIndex
  }
  const tail = contentText.slice(last)
  if (tail.trim()) chunks.push({ type: 'content', content: tail })
  return chunks
}
