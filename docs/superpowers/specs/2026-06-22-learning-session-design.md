# 学习会话三合一设计 (答题 + Agent 协同 + 专属图谱)

> 状态: 设计稿, 待写实施计划
> 范围: 前端重构 (后端契约不变, AnySearch 留独立项)

## Context (为什么做)

当前学习侧六个视图 (Assessment/KnowledgeGraph/AgentView/Learning/Dashboard/Code) 通过左侧活动栏手动切换,彼此割裂。用户答完题后不会自动看到 Agent 协同过程,也不会自动看到自己专属的图谱,要在 `assessment → agents → graph` 间反复点。这丢失了"答题→协同→产出图谱"本该有的连贯叙事,也削弱了赛题"多智能体协同"的演示力。

本设计把**答题 + Agent 协同 cockpit + 专属图谱**三合一成一条纵向会话流,像与 Agent 对话一样由 Agent 推动阶段推进。学习资源/Dashboard/Code 仍保留为左侧栏独立视图。会话流产出与右侧 AI 助手双向联动 (UI 独立),助手可被追问"为什么这样规划"。

分屏采用主从布局 (会话流主体 + 至多 1 个右侧分屏视图对照),不引布局库,自研轻量实现。

## 核心决策

| 决策 | 选择 | 理由 |
|:---|:---|:---|
| 整合范围 | 答题+协同+图谱三合一;资源/看板/代码独立 | 三者有强叙事连贯;资源等独立访问更灵活 |
| 会话形态 | 纵向会话流, Agent 推动 4 阶段产出卡 | 最接近"与 Agent 会话"的体感, 产出卡避免纯聊天 |
| 分屏风格 | 主从布局 (会话流主体 + 至多 1 右侧分屏) | YAGNI; VSCode 平等容器组超出学习场景, 自研布局引擎代价过大 |
| 分屏技术 | 布局模式 (不复制组件) | 左侧栏视图组件原样渲染, v-show 常驻, 零状态同步 |
| 布局库 | 不引, 自研轻量主从分屏 | Vue 无成熟 mosaic; 与 --km-* token/Monaco 常驻冲突; 赛题验收风险 |
| 左侧栏 | 替换 assessment 为 learning-session; graph/learning/dashboard 保留 | 会话流成答题唯一入口; 图谱等仍可独立随时看 |
| AI 助手 | 右侧 AssistantPanel UI 独立, 会话产出注入其上下文 | 专业知识获取更适合"联动但独立"而非"会话即对话" |
| AnySearch | 本次不做, 留后端独立项 | 范围控制, 避免混入后端工作 |

## 架构

### 视图调整

```
活动栏 (左侧):
  code / learning-session(替换原 assessment) / graph / learning / dashboard
                ↑
        LearningSession 视图 (三合一会话流)
        原 Assessment.vue 答题逻辑搬进会话流"阶段②答题"
        原 AgentView.vue cockpit 搬进会话流"阶段③协同"内联展开

原 assessment/agents 视图入口移除 (逻辑搬进会话流, 不再单独入口)
graph/learning/dashboard 保留独立入口 (分屏时可拖入主区对照)
```

### LearningSession 视图结构

```
LearningSession.vue (主区视图)
├── 会话流 (纵向, Agent 推动)
│   ├── 阶段① 目标设定卡   ← 搬自 Assessment 输入区 (form.targetDirection/scene)
│   ├── 阶段② 答题卡       ← 搬自 Assessment interactive 三阶段 (input→answering→feedback)
│   ├── 阶段③ Agent 协同卡 ← 搬自 AgentView cockpit 三栏 (花名册/对话流/证据), 默认折叠可展开
│   └── 阶段④ 专属图谱卡   ← 摘要 (节点数/路径/掌握度) + "查看完整图谱"按钮 → 切 graph 视图
│
└── 主从分屏层 (覆盖在会话流右侧, 可选)
    └── 分屏视图 = 左侧栏某视图组件原样渲染 (graph/learning/dashboard 之一)
        顶部标签 + 关闭钮 × (关闭回到纯会话流)
```

### 阶段推进规则 (会话流状态机)

会话流阶段由 `assessment` store 的现有状态派生, `session.activeStage` 是 **computed** (不独立存状态, 避免双源真相):

| store 状态 | activeStage | 说明 |
|:---|:---|:---|
| `!hasResults && !loading && phase!=='answering' && !orchestrationLog.length` | `goal` | ① 目标设定 (输入区可填) |
| `phase === 'answering'` | `quiz` | ② 答题 (题目可作答) |
| `loading && phase!=='answering' && orchestrationLog.length` | `agent` | ③ 协同 (demo SSE 流期间, cockpit 展开实时日志) |
| `phase === 'feedback'` | `quiz` | ② 答题反馈 (画像+策略, interactive 判分后, 仍属答题卡) |
| `hasResults` | `graph` | ④ 图谱摘要 (协同卡完成折叠, 图谱卡展开) |

**阶段③协同的边界**: 仅在 demo 模式 (`startDemoStream`) SSE 流期间, 由 `orchestrationLog` 驱动 cockpit。interactive 模式的 `loading` (判分/取反馈) 属答题卡内部进度, 不进阶段③。判据: `loading && orchestrationLog.length > 0` → 阶段③; `loading && orchestrationLog.length === 0` → 仍属阶段②答题卡内 loading。

阶段卡按"已完成→进行中→未到"三态展示: 已完成卡折叠为摘要条, 进行中卡展开, 未到卡灰显。用户可点击已完成卡回看展开。

### 主从分屏交互

- **触发**: 阶段④图谱摘要卡的"对照查看"按钮, 或会话流任意产出卡右上角的"分屏"图标
- **选择分屏视图**: 弹出小菜单选 graph/learning/dashboard (复用左侧栏视图)
- **落位**: 固定右侧 (主从, 不支持拖方向; 如需上下后续可扩, 本次 YAGNI)
- **布局**: 主区变 `grid-template-columns: 1fr 1fr`, 左会话流 + 右分屏视图
- **分屏视图组件**: 原左侧栏视图组件 (如 KnowledgeGraph.vue) 原样在右半渲染, **v-show 常驻** (与 S6 治理一致, 切换不销毁 G6/Monaco 状态)
- **关闭**: 分屏卡顶部 × → 回到纯会话流
- **同屏最多 1 分屏** (主从, 不嵌套)

### 与右侧 AI 助手双向联动

- **会话产出 → 助手上下文**: 会话流完成阶段③后, `assessment.profile` (theory_level/weak_topics) + `knowledgeGraph` (learning_path) 注入 `chat.buildSystemPrompt` 的 context (已有 tutorMode 注入机制, 扩展为无论是否 tutorMode 都注入学情画像)
- **助手 → 会话**: 不直接驱动会话流 (会话流由 assessment store 驱动); 助手可被用户追问"为什么把异常处理前置", 基于注入的画像/图谱回答
- **UI 独立**: AssistantPanel 仍在右侧栏, 不并入会话流

## 数据流 (复用现有 store, 不改后端契约)

```
用户在阶段①填目标 → store.startAssessment({targetDirection, scene})
  → 后端 /api/diagnostics/stream (SSE)
  → store.currentStep 推进 → 会话流阶段③ cockpit 实时显示日志
  → store.profile/knowledgeGraph/generatedContent 就绪
  → 会话流阶段④ 图谱摘要卡展开 (派生自 store.knowledgeGraph)
  → 同步注入 chat store 上下文 (双向联动)

阶段②答题 (interactive): store.startAssessment → phase='answering'
  → 用户作答 → store.submitAssessmentAnswers → phase='feedback'
  → store.fetchFeedback → 反馈资源
```

复用: `useAssessmentStore` (startAssessment/submitAssessmentAnswers/fetchFeedback/orchestrationLog/profile/knowledgeGraph), `useAgentStatus` (agentNodes/pipelineRunning), `useSidebarStore` (setView 切图谱), `useChatStore` (buildSystemPrompt context 扩展)。

## 关键文件

| 文件 | 动作 |
|:---|:---|
| `frontend/src/views/LearningSession.vue` | 新增 — 三合一会话流主视图, 4 阶段产出卡 |
| `frontend/src/components/session/StageGoal.vue` | 新增 — 阶段①目标设定卡 (搬自 Assessment 输入区) |
| `frontend/src/components/session/StageQuiz.vue` | 新增 — 阶段②答题卡 (搬自 Assessment interactive) |
| `frontend/src/components/session/StageAgent.vue` | 新增 — 阶段③协同卡 (搬自 AgentView cockpit, 折叠展开) |
| `frontend/src/components/session/StageGraph.vue` | 新增 — 阶段④图谱摘要卡 + 分屏触发 |
| `frontend/src/components/session/SplitPane.vue` | 新增 — 主从分屏容器 (右半 v-show 渲染左侧栏视图) |
| `frontend/src/stores/session.js` | 新增 — 会话流阶段状态 (activeStage/splitView) + 分屏控制 |
| `frontend/src/stores/sidebar.js` | 改 — ACTIVITY_ITEMS 替换 assessment 为 learning-session; 移除 agents |
| `frontend/src/ide/MainArea.vue` | 改 — 装载 LearningSession 视图; 分屏布局 |
| `frontend/src/views/Assessment.vue` | 删 (逻辑搬进 StageQuiz/StageGoal) |
| `frontend/src/views/AgentView.vue` | 删 (逻辑搬进 StageAgent) |
| `frontend/src/stores/chat.js` | 改 — buildSystemPrompt 注入学情画像 (扩展现有 tutorMode 分支) |
| `frontend/src/__tests__/session-store.test.js` | 新增 — 阶段状态机 (activeStage computed 派生) + 分屏控制单测 |
| `frontend/src/__tests__/learning-session.test.js` | 新增 — 阶段卡渲染 + 推进 + 分屏触发 |
| `frontend/src/__tests__/assessment-redesign.test.js` | 删或改 — 原测 Assessment.vue, 改为测 StageQuiz/StageGoal |
| `frontend/src/__tests__/agent-view-redesign.test.js` | 删或改 — 原测 AgentView.vue, 改为测 StageAgent |
| `frontend/src/__tests__/titlebar-menu.test.js` | 改 — 断言里 `答题测评` 改 `学习会话`, `Agent 协同` 移除 |

## 交互与动效 (平滑 + 强交互感)

目标: 视图转化平滑不卡顿, 阶段推进有清晰节奏感。所有动画 `transform/opacity` 为主, honor `prefers-reduced-motion`。

### 阶段卡推进
- **新阶段卡进入**: Vue `<Transition>` + `--km-ease-out`, 从 `translateY(12px) opacity:0` → `0/1`, 300ms
- **已完成卡折叠**: `height + opacity` 过渡 (400ms), 折叠为摘要条 (阶段号 + 标题 + 结果摘要), 点击可重新展开
- **自动滚动**: 阶段切换时 `scrollIntoView({behavior:'smooth'})` 定位到当前阶段卡, 用户无需手动找
- **状态三态视觉**: 已完成 (✓ + 收起)、进行中 (脉动边框)、未到 (灰显)

### 进度连线 (左侧竖线)
- 会话流最左侧一条竖线串联 4 阶段卡, 类时间轴
- 已完成段: `--km-success` 实线
- 进行中段: `--km-primary` 渐变流动 (CSS `@keyframes` 沿竖线流动, reduced-motion 下改静态实色)
- 未到段: `--km-border` 虚线
- 每阶段卡左侧一个节点圆点, 状态对应填色

### 当前阶段卡脉动
- 进行中的阶段卡左边框 `--km-primary` 带 `box-shadow` 脉动 (`@keyframes` 透明度循环, 2s)
- reduced-motion 下取消脉动, 改静态左边框高亮

### 分屏开合
- 右半分屏: `grid-template-columns` 从 `1fr 0fr` → `1fr 1fr` 过渡 (grid 列宽可动画, 350ms `--km-ease`)
- 分屏视图淡入 (`opacity` 200ms, 延迟 100ms 等列宽展开)
- 关闭反向: 列宽收回 + 视图淡出
- 分屏视图 `v-show` 常驻 (S6 治理), 切换不销毁 G6/Monaco, 不闪

### Agent 协同卡 (阶段③)
- cockpit 三栏展开时, 对话流逐条日志 `opacity + translateY` 错峰进入 (stagger, 60ms 间隔)
- 运行中的 Agent 节点 status-dot 脉动 (复用现有 `--km-warning` 呼吸)
- pipelineRunning 期间卡顶有细进度条流动 (非精确进度, 表"进行中")

### 性能保障
- 所有动画限 `transform/opacity/box-shadow` (不触发 layout, GPU 加速)
- 阶段卡用 `v-show` 常驻已完成卡 (折叠态), 不 v-if 重建
- 分屏视图 v-show 常驻 (前述)
- 大列表 (cockpit 日志/实体) 用虚拟滚动或限长 (现有 AgentView 已限长)
- `prefers-reduced-motion: reduce` 下: 所有 keyframe 动画 → 静态, 过渡时间 → 0

## 不做 (YAGNI)

- VSCode 平等容器组分屏 / 嵌套分屏 / 拖方向落位 (主从 1 分屏足够)
- 布局序列化保存 (下次打开恢复分屏)
- AnySearch 专业搜索 (后端独立项, 有 spec)
- 会话流"编辑/重生成"分支 (Apix 借鉴另一独立项)
- 助手直接驱动会话流 (会话流由 store 驱动, 助手只读上下文)
- 学习资源/数据看板并入会话流 (保留独立左侧栏入口)

## 验证

1. **单测**: `npm test` — 新增 session-store + learning-session 测试 + 既有测试全过
2. **构建**: `npm run build` — 无新依赖, 通过
3. **手动 e2e** (`npm run dev`):
   - 进 learning-session → 阶段①填目标 → 阶段②答题 → 阶段③协同实时日志 → 阶段④图谱摘要
   - 点图谱摘要"对照查看" → 右侧分屏出图谱, G6 可交互
   - 关分屏 → 回纯会话流
   - 切左侧栏 graph → 图谱独立视图正常 (与分屏是同一组件, 状态保留)
   - 右侧 AI 助手问"为什么这样规划" → 基于注入画像回答
   - 已完成阶段卡可点击回看展开
