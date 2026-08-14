# Codex 化 UI 改造 - 剩余工作 V2（2026-08-14）✅ 已全部完成

> T1-T5 五任务已逐个完成并独立提交（94155bb / 6dc7917 / 9df5781 / 21b7e90 / 0626bd8），详见 [docs/devlogs/B_前端/2026-08-14_Codex化UI收官.md](../docs/devlogs/B_前端/2026-08-14_Codex化UI收官.md)。剩手测验收。
> 以下为原决策记录存档。

> V1 方案（完整 5 阶段）大部分已落地并提交。本文档只覆盖**剩余工作**，决策已与用户确认。
> 已完成部分存档见 git 历史（NavSidebar / OnboardingOverlay / view-card / PERSONA 尺寸 + nodesep/ranksep 均已在 main）。

## 已确认决策（本次 grill 会话敲定）

| 决策点 | 结论 |
|---|---|
| AI 助手形态 | **双形态共存**：新增主区 `chat` 视图（Codex 式居中 760px）+ 保留右侧可折叠侧栏（学习会话等视图并排答疑）。chat store 不动，同一 AssistantPanel 组件两处装载。已入 CONTEXT.md「AI 助手双形态」 |
| 图谱详情侧栏 | **真 split**：flex 推挤画布非浮层遮盖，删 `panelGap=300` 避让，展开/收起触发 G6 resize 重算。已入 CONTEXT.md「图谱详情分栏」 |
| 引导对话 | **接受卡片向导**（OnboardingOverlay.vue），不改对话式；做 UX 打磨 |
| 执行方式 | 任务从小到大逐个做，每个独立提交，改完跑前端测试 |

## 任务清单（按此顺序执行）

### T1 - 死代码清理：ActivityBar
- 删 `frontend/src/ide/ActivityBar.vue` + `frontend/src/__tests__/activitybar-theme.test.js`（主布局已不引用，仅测试还在 import）
- 全局 grep `ActivityBar` 确认无残留引用（CLAUDE.md 文件索引里的条目一并移除）

### T2 - 设置页「重新引导」入口
- SettingsView.vue 加入口（推荐放「通用/AI 助手」段底部或关于段）：点后 `localStorage.removeItem('kmatch-onboarded')` 并触发重载/直接置 Workspace 的 onboardingVisible
- 实现提示：不重载页面的做法 - 把 onboardingVisible 提到 sidebar store（如 `onboardingActive` ref），设置页 set true，Workspace 响应式联动，finish 时回写 localStorage

### T3 - 图谱详情分栏 split
- KnowledgeGraph.vue：`.side-panel` 从 `position:absolute` 浮层改为 flex 行布局占位（画布 flex:1 + 侧栏固定宽），删 [KnowledgeGraph.vue:516-517](frontend/src/views/KnowledgeGraph.vue#L516-L517) panelGap 避让
- 侧栏展开/收起 toggle -> dispatch `window.resize`（复用 MainArea 现有机制）让 G6 重算
- path-summary + node-detail 两卡融合为单卡分段（V1 阶段 C 原案）
- 验收：展开详情不遮节点、画布占满剩余宽、暗亮主题正常

### T4 - AI 助手双形态（最大件）
- `sidebar.js`：ACTIVITY_ITEMS 加第 7 项 `{ id: 'chat', icon: 'ChatLineRound', title: 'AI 助手' }`（放「学习会话」之后）
- MainArea.vue：`chat` 视图分支装载 AssistantPanel（`variant="wide"`），容器 max-width 760px 居中、view-card 圆角留白
- AssistantPanel.vue：加 `variant: 'side' | 'wide'` prop（默认 side 零改动）；wide 下：气泡间距 16px、user 右对齐主色、assistant 左对齐带 avatar、输入框底部圆角胶囊、工具栏（厂商/模型/reasoning/导学/附件）收进 `⋮` popover、建议 chip 圆角胶囊居中
- Workspace.vue 右侧 ResizablePanel 保留，`aiPanelVisible` 语义不变（只控侧栏）
- **红线**：chat store 全部逻辑、chunks 渲染、工具卡状态机、版本切换、审批门、SSE、附件零改动
- 验收：chat 视图对话 + 学习会话侧栏并排答疑同时可用；Monaco v-show 常驻不受影响

### T5 - 引导向导 UX 打磨（卡片向导保留）
- 完成（「进入 KMatch」）后自动切到 `chat` 视图开始体验（而非停在 code）
- 学习方向选择真正消费：goal 持久化已有，就绪步把 goal 注入学习会话起始目标（轻接线，若无现成通道则仅在就绪清单展示，不过度设计）
- 微调：API Key 步错误态提示（Key 格式校验 soft 提示）、进度点/按钮 hover 一致性、窗口窄高时滚动顺畅（已有 max-height）
- 已有 onboarding-overlay.test.js 全过，新增交互补测试

## 执行提示词（每任务开始时用）

```
在 KMatch-Desktop 仓库执行 .claude/plan.md 的 T{n} 任务。要求：
1. 只做 T{n} 范围内改动，不顺手重构
2. 匹配现有代码风格（km-* token、注释密度）
3. 改完跑 cd frontend && npm run test（或 npx vitest run），全过后 git commit "feat/fix/refactor(scope): 中文简述"
4. chat store / Monaco v-show 常驻 / G6 resize 机制是红线，不碰
```

## 不做（已知局限，沿袭 V1）
- 多会话历史（chat store 单会话保留）
- 真实 LLM 对话式引导
- code 视图 Monaco 深度 Codex 化（保持全宽 IDE）

## 风险
- T4 是唯一动 Workspace 装载结构的任务，影响所有视图切换 -> 逐视图手测 + 截图
- 248 前端测试：T4 可能触发 AssistantPanel 相关测试选择器失败，逐个修
- 每任务独立提交，可单独回滚
