# ADR-0002: 消息模型重构为 chunks 判别联合

- 状态：Accepted
- 日期：2026-06-22
- 关联：阶段6b（commit 2b69416），借鉴 Apix MessageChunk

## 背景

原消息模型用 `role: 'tool'` 双重表示工具调用，且 think / content / tool_call 混在同一 content 字符串里，渲染与状态追踪困难。

## 决策

消息内容改为 **Chunk 判别联合**：

```
{ type: 'think' | 'content', content }
{ type: 'tool_call', id, tool, args, status: 'pending'|'in_progress'|'completed'|'error', result? }
```

- 相邻同类型 think/content 合并（`appendTextChunk`）。
- 工具调用变内联 chunk，自带状态机。
- 删除 `role:'tool'` 双重表示。
- 后端契约不变（序列化时 `stripToolCalls(contentTextOf)`）。

## 理由

- 判别联合让渲染层 `v-for chunks` 直接按 type 分派，状态徽标内联。
- 工具调用状态机显式化，pending/in_progress/completed/error 可独立追踪。
- 借鉴 Apix MessageChunk，已验证可行。

## 后果

- 纯 helper（`activeChunksOf`/`contentTextOf`/`thinkTextOf`/`splitToolCallChunks`/`appendTextChunk`）成为消息模型的公共契约，测试在 `chat-chunks.test.js`。
- 后续重构 chat.js（C1）时这些 helper 是天然的拆分边界。
