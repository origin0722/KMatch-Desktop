# ADR-0006: chat.js 拆分与 store 解耦 (C1–C4)

- 状态：Accepted
- 日期：2026-06-23
- 关联：阶段10 后规范化重构，issue #3/#4/#5/#6，`docs/架构与设计/重构方案_解耦.md`

## 背景

`chat.js` 增长到 1128 行的 god store，混 6 职责（消息/chunk/version 模型、SSE 传输、工具定义+执行、provider/apiKey/model 管理、系统提示词构建、write_file 审批门）。`workspace→projectGraph` 硬编码观察者耦合。profile/knowledgeGraph 字段名散落在 `buildSystemPrompt`。`session.js` 去留未决。

## 决策

按 `improve-codebase-architecture` 方法论拆分（C1–C4）：

- **C1 拆 chat.js**（5 步）：
  - C1.1 provider/model/apiKey/PROVIDERS + fetchModels/setter 迁入 `aiSettings.js`（统一 AI 配置单一源 + 一套 JSON blob 持久化，旧散装 localStorage 键一次性迁移）
  - C1.2 工具定义(TOOLS)+权限默认+广告/审批/提示词块 helper 抽 `ide/tools/registry.js` 单一源（消灭 chat.js 与 aiSettings.js 两处硬编码同名 6 工具）
  - C1.3 SSE 传输层抽 `ide/chat/useChatStream.js` composable（IPC + fetch 回退两路统一 framing）
  - C1.4 `sendMessage`/`regenMessage` 共享工具循环抽 `_runToolRound` + `summarizeToolResults` 单一源（消灭 regen 的精简重复副本）
  - C1.5 消息模型 7 个纯函数抽 `ide/chat/model.js`
- **C2 workspace→projectGraph 解耦**：workspace 暴露 `onExternalChange` 订阅 API，projectGraph 在 setGraph 时订阅并自行 `markStale`。反转依赖方向（projectGraph→workspace 消费者），workspace 不再 import projectGraph。
- **C3 profile/knowledgeGraph 类型契约**：`ide/chat/types.js` JSDoc 类型 + 类型化 helper，`buildSystemPrompt` 经 helper 读取，不再硬编码字段名。
- **C4 session.js 保留**：近 pass-through store 保留为独立 store（splitView 是布局状态，与 assessment 领域非同一关注点，并入反增耦合），仅补边界注释。

## 理由

- chat.js 6 职责耦合使任何单点改动要在 1100+ 行定位，AI 导航困难，测试只能整体跑。按 seam 拆分让每块集中原本散落的复杂性（deletion test 通过：拆出后每块都集中复杂性，非 pass-through）。
- C2 反转依赖方向后，workspace 删 projectGraph 仍完整工作（事件无人接 = no-op）。
- C3 类型契约让 assessment schema 改动不再静默崩 chat 提示词。
- C4 保留避免领域 store 混入布局职责。

## 后果

- chat.js 1128→766 行（-32%），拆为 `model.js` / `useChatStream.js` / `tools/registry.js` / `aiSettings` 配置 / `chat/types.js` 各司其职。
- chat.js re-export model helpers 保持 `@/stores/chat` 既有契约，调用方不动。
- 新增测试：tools-registry(7) / useChatStream(7) / chat-summarize(7) / chat-types(5) + 各处回归，共 128 测试。
- 赛题功能锚点（场景一二闭环/导学/M5/可视化/四层图谱）行为不变。

## 审查后修正

二轮 code-review 发现并修正：
- model 持久化竞态（审查 #1）：setters 先 fetchModels 校正 model 再 persist → 但把 persist 整体 gate 在网络后会在慢网络下丢 provider/key。修正为：立即 persist（同步落盘 provider/key）→ fetchModels → 二次 persist（校正后的 model）。
- isBusy 统一禁用源（审查 #2）：`toolLoopRunning` 覆盖 streaming 后的工具执行窗口；`clearMessages` 同步重置该 flag。
- F9 Monaco model 缓存：项目切换 dispose 全部 model 后**无条件**从 editor 摘下（openProject 先设 root 再清 activeFile，watcher 触发时 activeFile 仍旧值）。
- F6 坏 JSON：有效 JSON 缺 tool 字段也标 `_malformed`，避免 fallthrough 成混淆的权限报错。
