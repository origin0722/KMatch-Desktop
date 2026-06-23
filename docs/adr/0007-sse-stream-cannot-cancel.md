# ADR-0007: SSE 流不可真取消（已知限制）

- 状态：Accepted（已知限制）
- 日期：2026-06-24
- 关联：issue #9 (F5)

## 背景

用户点"停止"时，`stopStreaming` 仅本地 `abortController.abort()`。但 IPC SSE 路的 fetch（main 进程）与后端 `AsyncOpenAI` stream 会继续跑到自然结束，浪费 token/后端算力。

## 决策

**接受此限制，不做真取消**。原因：

- Electron IPC `ipcRenderer` 一旦 `http:stream` 启动，无原生取消原语；要真取消需 main 侧 abort fetch + 后端 stream close，跨两层改造，收益（省少量 token）不抵成本。
- `useChatStream` 的 abort 已让渲染层 `finish()`（resolve），UI 立即解禁，用户感知上"已停止"。
- 后端 stream 自然结束后 main 自动 `http:stream:done`，无泄漏（监听器在 settle 时移除）。

## 后果

- 每次点"停止"会浪费已生成但未消费的 token（DeepSeek 流式通常几百 token 量级，可接受）。
- 若后续需真取消，路径：preload 暴露 `cancelStream(reqId)` → main 按 reqId abort 对应 fetch → 后端检测客户端断开 stream close。属增强，非赛题必需。
