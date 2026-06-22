# ADR-0003: 消息分支用线性 versions + trailingAfter（非树形）

- 状态：Accepted
- 日期：2026-06-23
- 关联：阶段10（commit 8f3a386），借鉴 Apix

## 背景

助手消息重生成时不应覆盖原回复，要能切换历史版本。用户消息编辑不做（YAGNI）。

初版用 `spanEnd` 单索引模型记录"该版本后续消息到哪为止"，但在"重生末条助手消息 → 再追问"场景下静默丢消息。

## 决策

采用 **线性 versions + trailingAfter**：

- 助手消息 `versions: [{id, chunks, timestamp, trailingAfter: []}]`，`activeVersion` 索引当前可见版本。
- `trailingAfter` = 该版本可见的后续消息 id 集合（精确表达归属）。
- 重生成：追加新 version（`trailingAfter:[]`），旧 version 冻结。后续消息隐藏不删，切回旧版本恢复。
- 非树形：任意助手可重生成，后续消息按 trailingAfter 过滤显示。

## 理由（spanEnd → trailingAfter）

`spanEnd` 是单索引（"trailing 到第 N 条"），分不清两种情况：

1. 旧版本的 trailing 已被隐藏（不应显示）
2. regen 后新追加的消息（应显示）

`trailingAfter` 用 id 集合精确表达每条 trailing 的归属，`_addMessage` 追加新消息时维护前一助手 active version 的 `trailingAfter`。`visibleMessages` computed 据此过滤。

## 后果

- 可见性模型集中在 `visibleMessages` + `_addMessage` hook + `regenMessage` 冻结点，是高复杂度核心，测试在 `chat-branch.test.js`（含 Critical 回归）。
- 重生成钮在 streaming / 审批门期间禁用（F10 指出 `regenMessage` 本身只查 `streaming`，程序化调用有并发风险——见 issue）。
