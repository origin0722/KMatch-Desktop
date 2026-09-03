# CONTEXT — KMatch·知链 领域词汇表

> 项目的 ubiquitous language。术语从代码与现有注释提炼，不发明新词。重构建议、issue、文档统一用这里的定义。

## 项目本体

- **KMatch·知链** — 知识图谱驱动的多智能体协同个性化学习平台。赛题 XH-202630。
- **KMatch-Desktop** — 当前的 Electron + Monaco 桌面 IDE，统一收编原 KMatch Web 前端学习功能并接入 AI 助手。单人全栈。
- **原 KMatch Web** — 阶段0 前的 Vue3 + Element Plus + AntV G6 Web 前端（port 5173），三人协作时代产物，已收编进 Desktop，旧文档归档于 `docs/legacy/`。

## 两类学习场景

- **场景一（无项目技能训练）** — 学情检测 → 画像 → 图谱组装 → 资源生成 → 审核 → 交付 → 反馈迭代。LangGraph orchestrator 编排 6 子 agent。
- **场景二（有项目二次开发）** — 代码解析 → 项目图谱 → 代码审查 → 代码测试。前端驱动，复用 `/api/project/{parse,review,test}`。

## 四层知识图谱

Neo4j 中的四层结构：**领域元知识 → 项目框架 → 代码实体 → 演化扩展**。原生向量索引（cosine, 1536 维，千问 text-embedding-v2）。后端 `KnowledgeGraph` 引擎见 `backend/app/graph/engine.py`。

## 动态建域（domain_bootstrap，阶段16）

学习目标不命中既有域时的兜底链路，`backend/app/agents/domain_bootstrap.py`：

- **域注册表** — 内置 6 域前缀（PY/DA/DB/EN/WD/ML）+ 扫描 JSON 真相源收集的动态域前缀。
- **resolve_direction** — 域判定：LLM 分类为主判据（跨语言目标向量相似度天然偏高，LLM 判域更可靠），LLM 未配置降级向量启发（top 相似度 ≥ 0.55），皆无回退旧选点。返回 `hit / miss / unknown`。
- **bootstrap_domain** — 动态建域：Tavily 检索作事实锚 → LLM 生成 10 节点 DAG + 每节点 2 题 → validate 同套校验 → KB CRUD 同通道落库。
- **llm_generated 节点** — 动态域节点标记：`source="llm_generated"` + `domain_label` + `category="动态领域"`；与手工节点同库同链路，二次同域学习命中复用不重建。事实基准来自 LLM，**不纳入 M5 质检口径**。

## 学情画像（profile v3）

`assessment.profile` 的结构（对齐 `profile_schema.json`）：

- `theory_level` — 理论掌握等级
- `practice_level` — 实践掌握等级
- `weak_topics: [{name, node_id}]` — 薄弱知识点
- `known_topics: [{node_id}]` — 已掌握知识点

chat 的 `buildSystemPrompt` 注入这些字段做因材施教；导学模式下结合 `weak_topics` 出动态追问。

## 消息模型（chat store）

助手消息的分支与分块模型（核心数据结构，详见 ADR-0002 / ADR-0003）：

- **Chunk** — 判别联合：`{type:'think'|'content', content}` 或 `{type:'tool_call', id, tool, args, status, result?}`。相邻同类型 think/content 合并（`appendTextChunk`）。tool_call 自带状态机 `pending→in_progress→completed→error`。
- **Version** — 助手消息的可重生成版本：`{id, chunks, timestamp, trailingAfter: []}`。`activeVersion` 索引当前可见版本。
- **trailingAfter** — 该版本可见的"后续消息 id 集合"。重生成分支时旧版本冻结、新版本 `trailingAfter:[]`；切回旧版本恢复其 trailing。线性 versions，非树形。取代了旧的 `spanEnd` 单索引模型（spanEnd 分不清"旧 trailing 隐藏"与"regen 后新消息显示"）。
- **visibleMessages** — 按 `trailingAfter` 过滤后的可见消息序列。

## 三阶段交互测评（interactive）

`assessment` store 的测评闭环（赛题(4)①）：

- `phase: 'idle' | 'answering' | 'feedback'` — 三阶段状态机
- `pendingQuestions` / `userAnswers` — 当前轮题目与作答
- `feedbackStrategy: 'advance' | 'remediate' | 'scaffold'` — 动态反馈策略
- `feedbackContent` — 反馈内容

## 学习会话（session store）

三合一纵向会话流：Assessment + AgentView + 知识图谱合并为 `LearningSession`。4 阶段卡：目标 → 答题 → 协同 → 图谱。

- `activeStage` — computed，派生自 assessment（优先级 graph > agent > quiz > goal），**不另存**（避免双源真相）。
- `splitView` — 右侧分屏视图（`null | 'graph' | 'learning' | 'dashboard'`）。

## 项目代码图谱（projectGraph store）

场景二的代码图谱与 Monaco 双向联动：

- `graph: {projectId, stats, entities, relations, sourcePath, written}` — 实体 `entities[]` 含 `{id, name, kind, qualified_name, line_start, line_end}`
- `stale` — 外部文件改动后行号可能漂移，置真时禁用实体跳转（赛题场景二正确性）
- `revealTarget` — chat→Monaco 跳转目标；`activeLine` — Monaco→chat 光标行；`activeEntityId` — 行所在实体

## 导学模式（tutorMode）

赛题(4)② 动态追问与启发式导学。开启后 `buildSystemPrompt` 走 Socratic 分支：引导式回答替代直接答案 + 每轮动态追问 + 注入学情画像因材施教 + 事实底座抗幻觉（复用工具）。`aiSettings.tutorMode` 持久化。

## AI 助手工具集（6 项）

| 工具 | 用途 | 权限默认 |
|---|---|---|
| `read_file` | 读工作区文件 | allow |
| `list_directory` | 列目录 | allow |
| `write_file` | 写文件（经审批门 + 安全预检） | ask |
| `generate_project_graph` | 项目代码图谱（可离线） | ask |
| `code_review` | 四维度代码审查（需 Neo4j） | ask |
| `code_test` | LLM 生成测试 + 沙箱 pytest（需 Neo4j） | ask |

工具**定义**（`TOOLS`）与**权限默认**已收编至单一源 `frontend/src/ide/tools/registry.js`（C1.2 解耦完成）。

## write_file 审批门

`write_file` 工具的安全闭环：`pendingApproval` 单槽 → `/api/chat/safety-check` 预检（`hard_check_code_safety` 纯 AST，high 阻断/medium 提示）→ 用户可编辑内容 → 批准/拒绝 → 写后刷新文件树+打开文件。安全预检失败优雅降级（不阻断，用户决定）。

## IDE 布局

- **NavSidebar** - 左侧带文字导航栏（由 VSCode 式活动栏 ActivityBar 演化而来）。仍是 `activeView` 单一指示模型，6+1 视图导航。
- **AI 助手双形态** - 同一 AssistantPanel 组件的两种装载形态：主区 `chat` 视图（居中大留白对话，760px max-width）与右侧可折叠分栏（学习会话等视图内并排答疑）。`sidebar.aiPanelVisible` 只控制侧栏形态；chat store 单会话，双形态共享同一对话。

- **图谱详情分栏** - 知识图谱视图的详情/路径侧栏，flex 布局推挤画布（非浮层遮盖）。展开时 G6 重算画布尺寸，dagre 布局不做侧栏避让（无 panelGap）。

## 进程拓扑

四进程：**Renderer**（Vue3，沙箱，无 Node）↔ **Main**（Electron/Node）↔ **Backend**（FastAPI/uvicorn :8000）↔ Neo4j。跨进程边界用 `[PB]` 标注。IPC 全表与数据流见 `docs/架构与设计/ARCHITECTURE.md`。

## AI 配置

- **provider/apiKey/customBaseUrl/model** — 当前存在 `chat.js`（散装 localStorage 键）。重构目标：并入 `aiSettings`（见 C1）。
- **reasoningMode** — `auto | fast | deep`，驱动后端 `extra_body.thinking`。DeepSeek v4* 为 native thinking。
- **toolPermissions** — 每工具 `allow | ask | deny`。
- **memories** — 注入系统提示的持久记忆条目。

## M5 独立裁判（quality_judge）

赛题 M5 三指标（幻觉率<5% / 适配率≥85% / 覆盖率≥90%）的判定升级（阶段15）：

- **独立裁判** — `backend/app/agents/quality_judge.py`，LLM-as-Judge 逐资源判定 `grounded|hallucinated|unverifiable`。裁判只拿资源内容 + 图谱事实（summary/key_points），**不拿**生成过程与 reviewer 结论，打破"作者自评"循环验证。
- **双口径** — `quality_metrics.py` 自评（reviewer 维度分）与独立裁判双列并存；**幻觉率达标以独立裁判为主口径**（口径决策见 `docs/质量与验收/质量检测报告.md`）。
- **JUDGE_LLM_*** — `.env` 独立配置裁判模型（可异源），未配置回退主 LLM（标注同源裁判）。
- **反馈快模型** — `agentLlm.feedbackModel`（默认 deepseek-v4-flash），仅针对性反馈请求经 `buildFeedbackOverrides` 换快模型，主引擎模型不变。

## 赛题功能锚点（重构不可破坏）

- 场景一全流程闭环、场景二全链路
- 赛题(3)① 知识图谱可视化
- 赛题(4)② 动态追问与启发式导学
- M5 质量指标：幻觉率<5% / 适配率≥85% / 覆盖率≥90%（主口径：独立裁判）
- 四层图谱契约
