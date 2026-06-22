# Desktop 开发阶段总览（阶段0–10）

> 从 CLAUDE.md 迁出的历史阶段日志。详细 devlog 见同目录按端分类的日期文件。架构决策见 [../adr/](../adr/)。

## 阶段0 (6/19): 迁移现有 Vue 前端 + 双场景路由骨架 ✅

## 阶段1 (6/19-20): Electron 壳 + Monaco IDE + TRAE 风格亮暗主题 + IDE 三栏布局 + 学习功能收编 ✅
- 1.5: 收编学习功能进 IDE 侧栏
- 1.6: 三栏布局重构 — 主区多视图 + 右侧 AI 面板
- 1.7: 去顶部 Tab + 修活动栏重复指示 + 空白/黑屏修复
- 1.8: 设计系统重构（--km-* token + Apix 风格暖 Indigo 主题）

## 阶段2 (6/20): AI 助手 — 多模型对话 SSE + 工具调用循环 (read_file/list_directory) + 工作区上下文注入 ✅
- 2.1: 修赛题 3 断点 — S7 Learning 视图挂载主区；S8 Dashboard M5 用真实 learning_report；S9 interactive 测评三阶段闭环

## 阶段3 (6/21): write_file 工具 + 权限审批门 ✅
- 后端抽 `app/agents/code_safety.py`（纯 AST，无 langchain/neo4j 依赖），code_reviewer re-export 兼容
- 新增 `POST /api/chat/safety-check`（.py 才真检，high 阻断/medium 提示）
- chat.js: write_file + pendingApproval 审批门；AssistantPanel.vue 审批卡 UI

## 阶段4 (6/21): 图谱委派工具 + Monaco 符号联动 ✅
- 4a: 三项委派工具（generate_project_graph/code_review/code_test）接入 chat tool 循环，前端驱动，零后端改动；http:request 加 opts.timeoutMs（code_test 180s）
- 4b: Monaco 符号联动 — 新建 stores/projectGraph.js；MonacoEditor revealTarget/activeLine 双向
- 4c: 启发式交互导学模式（赛题(4)②）— chat.js tutorMode + buildSystemPrompt 导学分支；AssistantPanel 开关
- 对题：code_review/code_test 需 Neo4j 在线，generate_project_graph 可离线

## 阶段5 (6/21): PyInstaller 打包 backend sidecar + Windows 安装包 ✅
- S3: backend PyInstaller 打包通（KMatchBackend.spec 修 cipher 废弃参数 + hiddenimport + collect_all）
- config.py 支持 KMATCH_DATA_DIR；运行时验证 /api/health 200 优雅降级
- electron-builder.yml 映射；第一版 NSIS 安装包（239M）
- 瘦身：spec 只收集 langchain_core/openai/langgraph，excludes 排重依赖 → 548M→141M
- **沙箱强化 DockerSandboxExecutor 仍待做**；打包后 code_test 沙箱不可用属已知限制

## 阶段6 (6/22): chat 深度思考收尾 + 消息 chunks 判别联合重构 ✅
- 6a: DeepSeek 深度思考收尾（commit 9ccb4e8）— 删 deepThinking 孤儿状态，统一由 aiSettings.reasoningMode 驱动；http-proxy 保留非 200 错误回传
- 6b: 消息模型重构为 chunks 判别联合（commit 2b69416，借鉴 Apix）— Chunk 判别联合 + 工具状态机；删 role:'tool'；后端契约不变；80 测试过

## 阶段7 (6/22): 学习视图主题收编（Dashboard/KnowledgeGraph/Learning/Assessment）✅
- 阶段1.8 建了 --km-* token，但只 AgentView/Assessment 收编；其余仍用 Element 默认色（"AI-web-template feeling"残留）
- 各视图硬编码色 → token + THEME 镜像（ECharts/G6 canvas 不能读 CSS 变量）；去 emoji-as-icon
- utils/format.js 共享 masteryColor；Redesign-Preserve：只动视觉层，业务逻辑一字未改；80 测试过

## 阶段8 (6/22): 文件监听 Worker + S6 治理 + 项目图谱失效 ✅
- worker_threads + chokidar v4（v5 ESM-only 与 main CJS 冲突）；createWatcherController 纯工厂可单测
- S6 治愈：MainArea code 视图 v-if→v-show 常驻；MonacoEditor externalChanges watcher
- 项目图谱失效（赛题场景二正确性）：projectGraph stale + markStale；AssistantPanel stale alert + 禁用跳转
- 93 测试过（新增 13）；手动 e2e 待跑

## 阶段9 (6/22): 学习会话三合一（答题 + Agent 协同 + 专属图谱）✅
- Assessment + AgentView + 知识图谱三合一成 LearningSession；4 阶段卡（目标→答题→协同→图谱）
- 新增 stores/session.js（activeStage 派生自 assessment，splitView 白名单）；SplitPane 主从分屏
- 双向联动：chat 非导学模式也注入学情画像
- 删除 Assessment.vue/AgentView.vue + 孤儿报告组件 + 4 测试
- 82 测试过；subagent-driven 12 commits，code review Approved

## 阶段10 (6/23): 消息分支（重生成分支）— Apix 借鉴收官 ✅
- 助手消息重生成不覆盖原回复，新建 version，‹n/m› 切换；用户消息编辑不做（YAGNI）
- 线性 versions + trailingAfter（非树形）；任意助手可重生成，后续消息隐藏不删
- **关键**：spanEnd 单索引 → trailingAfter（id 集）。spanEnd 分不清"旧 trailing 隐藏"vs"regen 后新消息显示"，导致"重生末条→追问"静默丢消息
- 94 测试过（新增 12 含 Critical 回归）；subagent-driven 9 commits，code review Approved
- Apix 借鉴三大项（文件监听 Worker / 消息 chunks / 消息分支）全部完成

## 已知待修
- S1–S6 均已修（见各阶段）
- 沙箱强化 DockerSandboxExecutor（阶段5 残留）
- F1–F15 脆弱点 + 解藕 candidates → GitHub Issues 跟踪（见 [../重构方案_解藕.md](../重构方案_解藕.md)）
