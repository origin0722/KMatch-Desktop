# 消息分支 (重生成分支) 设计

> 状态: 设计稿, 待写实施计划
> 范围: 前端 chat 模型扩展 (后端契约不变)

## Context (为什么做)

Apix 借鉴最后一项。当前 chat 对话线性推进,助手回复一旦生成不可回溯 — 用户对某条回复不满意只能清空重来,丢失前后文。赛题(4)②"动态追问与启发式导学"强调多轮探索,学习者在导学对话里常想"换个方式解释""再给一个思路",重生成应保留原回复可回看,而非覆盖。

本设计给**助手消息**加重生成分支:重新生成不覆盖原回复,保留为历史版本,UI prev/next 切换。用户消息编辑不做 (YAGNI, 导学场景修正笔误覆盖即可, 探索不同问法是 Agent 的事)。任意助手消息可重生成,其后消息隐藏(不删, 切回原版恢复), 非树形分支。

交互以"舒服"为准: 版本切换淡入淡出, 重生成复用现有 SSE 流自然进入, 箭头/重生成钮 hover 浮现不常驻, 全部 reduced-motion 兜底, 不堆装饰动效。

## 核心决策

| 决策 | 选择 | 理由 |
|:---|:---|:---|
| 分支范围 | 仅助手消息重生成分支; 用户消息编辑不做 | 导学场景重生成价值大; 用户编辑多修正笔误, 覆盖即可, YAGNI |
| 重生成范围 | 任意助手消息可重生成 (非仅末条) | Apix/ChatGPT 标准行为; 学习者中途不满意也能重来 |
| 后续消息处理 | 隐藏不删, 切回原版恢复 (非树形) | 线性 versions + visible 标记, 比树简单; 不丢数据可恢复; 契合探索场景 |
| 数据模型 | 助手消息 versions 数组 + activeVersion + trailingAfter | 温和扩展, 不改用户消息; computed visibleMessages 派生显示 |
| UI 交互 | hover 浮现箭头/钮, 淡入淡出切换 | 舒服不干扰; 单版本不显示箭头 |
| API 序列化 | 只发当前 version 链 (activeVersion chunks + 其 visible 后续) | 后端契约不变, LLM 看到的是连贯当前对话 |

## 数据模型扩展

```js
// 现状 (阶段6 chunks 重构)
assistantMsg = { id, role:'assistant', chunks:[...], timestamp }

// 扩展后
assistantMsg = {
  id, role:'assistant',
  versions: [{ id, chunks:[...], timestamp }],
  activeVersion: 0,                              // 当前显示版 index
  trailingAfter: { [versionId]: msgId[] }        // 该版后续可见消息 id (隐藏/恢复用)
}
```

- 用户消息不变: `{ id, role:'user', chunks:[...], timestamp }`
- `visibleMessages` computed: 按 activeVersion 过滤, 只显示当前 version 链 (该助手 active version + 其 trailingAfter 标记 visible=true 的后续)
- 现有 helper 适配: `contentTextOf(msg)` 读 `msg.versions[activeVersion].chunks`; `stripToolCalls` 同理; 旧无 versions 的消息兼容 (视为单 version)

## 行为

### 重生成第 N 条助手消息

1. 若 N 后有消息 (M=N+1..末尾), 标记为 "N 当前 activeVersion 的 trailingAfter", visible=false (隐藏)
2. 在 `N.versions` 追加新 version, `N.activeVersion` 指向新 version
3. 触发重生成: 以 N 前的 visible 历史 + N 对应的用户提问 (N 的上一条 user 消息) 为 API 上下文, 重新调 `/api/chat/completions`, 新回复流进新 version 的 chunks (复用现有 `_streamResponse` + 工具循环)
4. 新 version 流式期间, N 显示 streaming 态 (同首次生成)

### 切版本 (‹/›)

- 改 `N.activeVersion`, 同步恢复/隐藏对应 version 的 trailingAfter (visible 切换)
- 切换淡入淡出 (opacity 150ms), 不滑动不翻转

### API 历史序列化

`apiMessages = [system, ...visibleMessages.map(m => ({role, content: stripToolCalls(contentTextOf(m))}))]`
只发当前 version 链, LLM 看到连贯当前对话。

## UI (舒服交互)

- **版本切换器**: 助手消息底部左下角 `‹ 2/3 ›` 灰色小箭头, **仅多版本时显示** (单版本不显示, 避免噪声)。hover 整条消息时箭头浮现 (opacity 0→1, 120ms), 不常驻。点 ‹/› 切 activeVersion。
- **重生成钮**: 助手消息 hover 时右下角浮现 RefreshRight 图标, 点击触发重生成。streaming 中禁用。
- **版本切换动效**: 内容区淡入淡出 (opacity 150ms `--km-ease`), 不滑动/翻转/缩放。
- **重生成流式**: 复用现有 SSE 流进入新 version chunks, 渲染同首次生成 (think/content/tool_call 内联), 无额外动效。
- **trailingAfter 隐藏/恢复**: 隐藏的消息直接不渲染 (v-if visible), 无退出动效 (避免切版本时大量消息动画卡顿); 恢复时淡入 (opacity 100ms)。
- **reduced-motion**: 所有过渡 → 0ms, 箭头/钮常驻显示 (不靠 hover 浮现)。
- **禁用态**: streaming 中重生成钮 disabled + 灰; 工具循环中 (有 pending tool_call) 禁用重生成。

## 范围

- 助手消息 versions + activeVersion + trailingAfter
- 重生成任意助手消息 (隐藏后续, 切回恢复)
- prev/next 切换 + hover 浮现 UI
- API 序列化只发当前 version 链
- `visibleMessages` computed + 兼容旧消息

## 不做 (YAGNI)

- 用户消息编辑分支 (覆盖即可)
- 树形分支 (parent/children) — 线性 versions + trailingAfter 够
- 版本 diff 对比视图
- 版本重命名/备注
- 版本删除 (用户不主动删, 切版本即可)
- 多分支并发流式 (一次只重生成一条)

## 关键文件

| 文件 | 动作 |
|:---|:---|
| `frontend/src/stores/chat.js` | 改 — 消息模型 versions/activeVersion/trailingAfter; sendMessage 拆出 regenMessage; contentTextOf/stripToolCalls 适配 activeVersion; visibleMessages computed; _addMessage 兼容 |
| `frontend/src/ide/AssistantPanel.vue` | 改 — visibleMessages 渲染; 版本切换器 ‹n/m›; 重生成钮; hover 浮现; 切换淡入淡出; reduced-motion |
| `frontend/src/__tests__/chat-chunks.test.js` | 改 — contentTextOf 读 activeVersion; 兼容旧无 versions 消息 |
| `frontend/src/__tests__/chat-branch.test.js` | 新增 — 重生成追加 version + 隐藏 trailingAfter; 切版本恢复; visibleMessages 过滤 |

## 验证

1. **单测**: `npm test` — 新增 chat-branch + 既有 chat-chunks 适配, 全过
2. **构建**: `npm run build` — 通过
3. **手动 e2e** (`npm run dev`):
   - 对话几轮 → 中间某条助手回复点重生成 → 新回复流式进入, 原回复保留, 后续消息隐藏
   - 点 ‹ 切回原版 → 原回复显示, 后续消息恢复
   - 点 › 切到新版 → 新回复 + 其后续
   - 末条重生成 (无后续) → 直接追加 version, 无隐藏
   - streaming 中重生成钮 disabled
   - hover 消息 → 箭头/钮浮现; 移开 → 消失
   - 单版本消息不显示箭头
   - reduced-motion (系统设置) → 切换瞬切, 箭头/钮常驻
