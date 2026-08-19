# KMatch·知链 — Claude 项目速查卡

> 知识图谱驱动的多智能体协同个性化学习平台 | 赛题 XH-202630 | 单人全栈开发

## 一句话描述

以 Neo4j 四层知识图谱为共享事实底座、LangGraph 多智能体协同为核心引擎，面向 Python 学习的个性化教学平台。覆盖"无项目技能训练"和"有项目二次开发"两类场景。

当前在构建 **KMatch-Desktop**：Electron + Monaco 桌面 IDE，统一收编原 Web 前端学习功能，并接入 AI 助手。

## 快速启动

```bash
# 开发模式 (Electron + Vite HMR)
npm install && npm run dev

# 仅前端 dev (浏览器, 不走 Electron)
cd frontend && npm install && npm run dev

# 全栈启动 (Neo4j + FastAPI + 前端)
docker-compose up -d
cd backend  && pip install -r requirements.txt && uvicorn app.main:app --reload
```

## 打包 (出 Windows 安装包)

```bash
# 1. 后端 PyInstaller 打包 sidecar (仅后端 Python 改动时需重跑, 产物 backend-dist/)
cd backend && pyinstaller KMatchBackend.spec --noconfirm --distpath ../backend-dist --workpath ../build/pyinstaller

# 2. 前端 + Electron 打 NSIS 安装包 (产物 release/*.exe)
#    国内网络必须配镜像, 否则 GitHub 下 electron / winCodeSign / nsis 会超时
#    一次性设永久环境变量 (Windows: 系统→环境变量; 或当前 shell export):
#      ELECTRON_BUILDER_BINARIES_MIRROR=https://npmmirror.com/mirrors/electron-builder-binaries/
#      ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/
ELECTRON_BUILDER_BINARIES_MIRROR=https://npmmirror.com/mirrors/electron-builder-binaries/ \
  npm run build:win
```

- 首次打包需开 **Windows 开发者模式** (设置→系统→开发者选项), 否则 winCodeSign 解压 macOS 符号链接报"客户端没有所需特权"。
- `backend-dist/`、`build/`、`release/`、`out/` 均已 gitignore, 不进仓库。
- 改前端 UI 用 `npm run dev` (HMR 热更新), 不要靠重打安装包迭代; 仅后端 Python 变动才需重跑步骤 1。
- 安装包 `release/KMatch·知链-0.1.0-x64.exe` 可直接分发, 装后 sidecar (KMatchBackend.exe) 自启; Neo4j 仍需用户 Docker 起。

## 架构速览

```
KMatch-Desktop (Electron + Monaco, 本地桌面 IDE)
  ├── 活动栏 (ActivityBar) — 视图切换 + 工具开关
  ├── 资源管理器 (FileExplorer) — 文件树 + 打开项目
  ├── 主区 (MainArea)
  │     ├── 代码视图: EditorTabs + MonacoEditor
  │     └── 学习视图: Assessment | KnowledgeGraph | AgentView
  ├── AI 助手 (AssistantPanel) — 多模型对话 + 工具调用 (阶段2)
  └── 状态栏 (StatusBar) — 后端健康 + 文件状态

原 KMatch Web 前端 (Vue3+Element Plus+AntV G6, port 5173)
  ├── Assessment, KnowledgeGraph, AgentView → 收编进 IDE 主区
  └── Dashboard, Learning, Home → 仅 IDE 内可达
         │ HTTP / IPC 代理
后端 (FastAPI+LangGraph, port 8000)
  ├── 主控调度Agent → 编排6个子Agent
  ├── 学情检测 | 图谱管控 | 内容生成 | 内容审核 | 代码审查 | 代码测试
  ├── KnowledgeGraph engine (engine.py) — Neo4j 图遍历 + 向量混合检索
  └── OpenAI 兼容接口 → DeepSeek Chat + 千问 Embedding
         │ Bolt
数据层 (Neo4j 5.x Community, ports 7474/7687)
  ├── 四层图谱: 领域元知识 → 项目框架 → 代码实体 → 演化扩展
  └── 原生向量索引 (cosine, 1536维)
```

## 关键文件索引

### Desktop IDE (开发中)
- [electron/main/index.js](electron/main/index.js) — Electron 主进程入口，窗口 + IPC + backend sidecar
- [electron/main/ipc/fs.js](electron/main/ipc/fs.js) — 文件系统 IPC
- [electron/main/ipc/workspace.js](electron/main/ipc/workspace.js) — 工作区/项目 IPC
- [electron/main/ipc/http-proxy.js](electron/main/ipc/http-proxy.js) — HTTP 代理 IPC (渲染进程→主进程→backend)
- [electron/preload/index.js](electron/preload/index.js) — Preload 脚本，暴露 window.api
- [frontend/src/views/Workspace.vue](frontend/src/views/Workspace.vue) — IDE 壳布局
- [frontend/src/ide/NavSidebar.vue](frontend/src/ide/NavSidebar.vue) — 左侧文字导航栏 (Codex 化, 替代 ActivityBar)
- [frontend/src/ide/FileExplorer.vue](frontend/src/ide/FileExplorer.vue) — 文件资源管理器 (code 视图内)
- [frontend/src/ide/MainArea.vue](frontend/src/ide/MainArea.vue) — 主区视图装载 (code/graph/assessment/learning/agents/dashboard)
- [frontend/src/ide/EditorTabs.vue](frontend/src/ide/EditorTabs.vue) — 多标签页
- [frontend/src/ide/MonacoEditor.vue](frontend/src/ide/MonacoEditor.vue) — Monaco 编辑器
- [frontend/src/ide/AssistantPanel.vue](frontend/src/ide/AssistantPanel.vue) — AI 助手面板
- [frontend/src/ide/StatusBar.vue](frontend/src/ide/StatusBar.vue) — 底部状态栏
- [frontend/src/ide/settings/SettingsView.vue](frontend/src/ide/settings/SettingsView.vue) - 设置页主壳 + 锚点导航 (Spec B)
- [frontend/src/ide/settings/AssistantSettings.vue](frontend/src/ide/settings/AssistantSettings.vue) - AI 助手段 (厂商/模型/key + 思考模式 + 工具权限 + 记忆 + 清历史)
- [frontend/src/ide/settings/AgentSettings.vue](frontend/src/ide/settings/AgentSettings.vue) - Agent 独立 key 段 + 测试连接 (Spec B)
- [frontend/src/ide/settings/ProvidersSettings.vue](frontend/src/ide/settings/ProvidersSettings.vue) - 自定义厂商 CRUD + 视觉探测 + 网络代理 UI
- [frontend/src/stores/sidebar.js](frontend/src/stores/sidebar.js) — IDE 布局状态 (单一指示模型)
- [frontend/src/stores/workspace.js](frontend/src/stores/workspace.js) — 工作区/文件状态
- [frontend/src/stores/theme.js](frontend/src/stores/theme.js) — 亮暗主题
- [frontend/src/stores/assessment.js](frontend/src/stores/assessment.js) — 学情测评状态 (含 interactive 三阶段 + learningReport)
- [frontend/src/stores/chat.js](frontend/src/stores/chat.js) — AI 助手对话 (SSE 流式 + 工具调用循环 + write_file 审批门 + 图谱委派工具 + 消息分支; isBusy 统一禁用源)
- [frontend/src/stores/aiSettings.js](frontend/src/stores/aiSettings.js) — AI 配置单一源 (provider/apiKey/model/PROVIDERS + 工具权限 + 记忆 + 推理模式; C1.1/C1.2 后收编)
- [frontend/src/stores/agentLlm.js](frontend/src/stores/agentLlm.js) - Agent 学习引擎独立 LLM 配置 + withOverrides 注入 helper (Spec B)
- [frontend/src/stores/customProviders.js](frontend/src/stores/customProviders.js) - 自定义厂商 CRUD + autoFetchModels (Spec A)
- [frontend/src/stores/modelVision.js](frontend/src/stores/modelVision.js) - 模型视觉能力探测缓存 (Spec A)
- [frontend/src/ide/tools/registry.js](frontend/src/ide/tools/registry.js) — 工具定义 + 权限默认 + 广告/审批/提示词块 helper 单一源 (C1.2)
- [frontend/src/stores/projectGraph.js](frontend/src/stores/projectGraph.js) — 项目代码图谱 + Monaco 符号联动状态 (阶段4b)
- [frontend/src/stores/learningResources.js](frontend/src/stores/learningResources.js) — 联网搜索 web_link 资源 store (阶段14 F1)
- [frontend/src/components/PathFinderModal.vue](frontend/src/components/PathFinderModal.vue) — 图谱路径查找 (BFS 最短学习路径, 阶段14 F2)
- [frontend/src/components/ScaffoldGuide.vue](frontend/src/components/ScaffoldGuide.vue) — 5 级渐进式实操引导 (阶段13 T1)
- [frontend/src/components/ReviewReport.vue](frontend/src/components/ReviewReport.vue) — 内容审核四维度报告 (阶段13 T2)
- [frontend/src/components/AssessmentReport.vue](frontend/src/components/AssessmentReport.vue) — 学情测评题目明细/错题回顾 (阶段13 T3)
- [frontend/src/views/ProjectGraphView.vue](frontend/src/views/ProjectGraphView.vue) — 项目代码图谱视图 (场景二可视化, 阶段14 F3)
- [backend/app/utils/web_search.py](backend/app/utils/web_search.py) — Tavily 联网搜索封装 (search_web + search_weak_topics, 阶段14 F1)
- [backend/app/api/search.py](backend/app/api/search.py) — /api/search/web 联网搜索路由 (阶段14 F1)
- [backend/app/api/chat.py](backend/app/api/chat.py) — AI 对话 SSE 后端 (/api/chat/completions + /models + /safety-check)
- [backend/app/agents/code_safety.py](backend/app/agents/code_safety.py) — 纯 Python AST 安全检查 (hard_check_code_safety, 供 chat 审批门复用)
- [backend/app/api/agents.py](backend/app/api/agents.py) - /api/agents/ping Agent 独立 key 连通性测试 (Spec B)
- [backend/app/agents/llm.py](backend/app/agents/llm.py) - LLM 适配层 + use_llm_overrides ContextVar (per-request overrides, Spec B)
- [backend/app/agents/sandbox.py](backend/app/agents/sandbox.py) - 代码测试沙箱 (SubprocessSandboxExecutor + DockerSandboxExecutor + select_executor)

### 后端核心 (原 KMatch)
- [backend/app/main.py](backend/app/main.py) — FastAPI 入口
- [backend/app/config.py](backend/app/config.py) — 全局配置
- [backend/app/graph/engine.py](backend/app/graph/engine.py) — KnowledgeGraph 引擎
- [backend/app/agents/](backend/app/agents/) — 7 个 Agent 实现
- [backend/app/api/](backend/app/api/) — REST API 路由

### 前端 API 层
- [frontend/src/api/index.js](frontend/src/api/index.js) — Axios 实例，Electron IPC / Vite proxy 双模式
- [frontend/src/api/diagnostics.js](frontend/src/api/diagnostics.js) — 学情检测 API
- [frontend/src/api/graph.js](frontend/src/api/graph.js) — 知识图谱 API

### 数据与文档
- [data/knowledge_base/](data/knowledge_base/) — 92 个 Python 知识点 (JSON)
- [data/prompts/](data/prompts/) — 7 个 Agent 系统提示词
- [data/user_profiles/](data/user_profiles/) — 3 组用户画像
- [docs/项目规划/项目开发计划书.md](docs/项目规划/项目开发计划书.md) — 9 周排期 + 赛题对标
- [docs/缺陷管理/BUG决策日志.md](docs/缺陷管理/BUG决策日志.md) — BUG 记录与决策
- [docs/devlogs/](docs/devlogs/) — 开发日志
- [docs/README.md](docs/README.md) — 文档中心分类索引

## 技术栈版本约束

| 模块 | 选型 | 版本 |
|:---|:---|:---|
| 桌面壳 | Electron + electron-vite | 33+ / 2.3+ |
| 编辑器 | Monaco Editor | 0.52+ |
| 多智能体框架 | LangGraph + LangChain | ≥1.0.0 |
| 图数据库 | Neo4j Community | 5.x (Docker) |
| 后端框架 | FastAPI | ≥0.137.0 |
| LLM 对话 | DeepSeek V4 Pro (OpenAI 兼容) | deepseek-v4-pro |
| LLM Embedding | 千问 text-embedding-v2 | 1536维 |
| 前端框架 | Vue3 + Element Plus + AntV G6 | 3.4+/2.8+/5.x |
| 容器化 | Docker + docker-compose | — |

## 当前开发阶段

**最新 (2026/08/18)：工作流可观测 & 多智能体协同资产化**（来源：对 dsh_workflow / dsh-deepseek-flow 逐文件对比后落地的六阶段）——
Phase0 结构化 run 事件（`log_events.to_log_event`，事件驱动状态替代正则）✅ / Phase1 耐久 run 记录（`run_store`：run.json+events.jsonl、GET /runs 复盘、一键续跑）✅ / Phase2 流程即数据（`workflow_def` + preflight + /workflows API，SSE 阶段文案由定义驱动）✅ / Phase3a 只读流程进度 DAG（`FlowDiagram` + `useFlowStatus`）✅ / Phase4 逻辑门自适应决策（`evaluate_gate`/decisions，strategy 与 decide_feedback 对齐）✅ / Phase3b 可编辑流程工作台（`flow_transactions` 提交事务 + revision 回滚；导航默认隐藏，待"定义驱动执行"接线后恢复）✅。
同日另有：提示词-代码契约漂移测试（`test_prompt_contract`）、设置页「API 设置」栏目（`apiSettings`：AI 助手与出题引擎 API 统一/分开 + 预设模型 + 连通性测试支持 openai/anthropic）、分阶测试题先自测后对答案、知识图谱详情「重测该点」/「问 AI 助手」双入口、Agent 协同降级(`degraded`)可视化、动态建域 PU 迷你域入库（292 节点/648 题/11 画像）、**画像跨次进化档案**（`profile_store`：稳定 learner 档案 + 加权合并掌握度 + 版本 diff，答题反馈展示"本次变化"；diff 落 run 复盘 + 遗忘/时效降级 recheck_due 30 天）、**提示词共享契约页** `data/prompts/00_shared_contracts.md`（01-08 头部引用 + 契约测试钉新页；03 embedding 降级显式条款）、**裁判 golden 回归集**（`backend/tests/fixtures/judge_goldens.json` + `test_judge_goldens` 离线全量 12 例 + `scripts/run_judge_golden.py` 真模型 live，判据措辞钉住护 M5 口径）、**懒加载目录树**（`FileTreeBranch` 递归分支 + workspace 惰性展开，修复大项目文件树卡顿）、**估时节奏语境**（report `pacing`：连续学时→按每周可学时折周展示）、**文件内联预览**（`FilePreview`：图片 base64 / Markdown(marked+DOMPurify) / HTML sandbox / PDF；`fs:readBase64` IPC；Monaco 预览分发+守卫）、**后台任务页**（`RunsPanel`：运行历史列表/事件时间线/按此重跑/重新测评，复用 P1 run 资产）、**Mermaid 图表**（Markdown 预览惰性渲染 + 失败降级，依赖 mermaid@^11）、**性能优化 A–G**（Monaco 惰性加载 / externalChanges 去深 / G6 rAF 节流 / 项目解析让主线程+过期丢弃 / 流式去重 Set+窗口上限 / Resizable rAF+will-change）。测试：前端 434 / 后端 242+ 宽回归全过（含修复 interactive run 未落盘死代码）。devlogs 见 [docs/devlogs/B_前端/](docs/devlogs/B_前端/)。

**此前里程碑：阶段14** (2026/08/02) 联网搜索 + 图谱增强 + 代码梳理 - F1 Tavily 联网搜索（web_search 工具 + 设置页 key + Learning 联网资源 tab）✅ / F2 图谱路径查找（BFS 最短学习路径）✅ / F3 项目代码图谱视图（场景二可视化）✅ / F4 双 agent 代码审查修复（snippet 字段 bug + SettingsView 拼写回归 + tooltip 死代码清理）✅。阶段13 学情报告组件回填（T1 ScaffoldGuide / T2 ReviewReport / T3 AssessmentReport）已全部收官。上一个里程碑：Spec B (2026/07/19) 设置页 + Agent 独立 key - Task 1-17 已合并 main (a38cd98)。完整阶段日志见 [docs/devlogs/Desktop_阶段总览.md](docs/devlogs/Desktop_阶段总览.md)。248 前端 + 471 后端测试全过。

**Spec B 进度**：Task 1-7 后端 (ContextVar per-request llm_overrides + AgentState 字段 + 5 agent 透传 + 8 路由 + /api/agents/ping) ✅；Task 8-17 前端 (设置页主壳 + AI 助手 / Agent 独立 key / 供应商管理 CRUD + 视觉探测 + 网络代理 UI) ✅；Task 18-19 代理主进程落盘 (preload setProxyConfig/restartBackend + sidecar env 注入) ⏳ 待做；Task 20 全量收尾 ⏳。

**已知待修**：沙箱强化已落地（DockerSandboxExecutor + SANDBOX_MODE auto/subprocess/docker，实现见 [backend/app/agents/sandbox.py](backend/app/agents/sandbox.py)，Dockerfile 见 `backend/sandbox/`）；feature/regularization 分支（F 系列脆弱点修复 + C1-C4 解耦 + 24 GitHub Issues）已合并 main（见 [docs/架构与设计/重构方案_解耦.md](docs/架构与设计/重构方案_解耦.md) + ADR-0006）；Apix 审查 S1-S9 全部已修（ADR-0005）；Spec B Task 18-19 代理落盘未接线（UI 已就绪，preload/IPC/env 注入待做）。

### 原 KMatch 后端已交付项
- ✅ 92 个 Python 元知识节点 + Neo4j 导入 + 验证
- ✅ 7 个 Agent 系统提示词 (全部 v0.3-final)
- ✅ 6 个 Agent 全部实现 (orchestrator/diagnostics/graph_controller/content_generator/reviewer/code_reviewer/code_tester)
- ✅ 场景一全流程闭环 (学情画像→图谱组装→资源生成→审核→交付→反馈迭代)
- ✅ 场景二全链路 (代码解析→项目图谱→代码审查→代码测试)
- ✅ 459 后端 + 223 前端单元测试全部通过 (2026/07/19 main 实测)
- ✅ 赛题 M5 质量检测指标 (幻觉率<5%/适配率≥85%/覆盖率≥90%)
- ✅ 知识库管理 CRUD API
- ✅ SSE 流式测评

BUG 清单: 77 条 (77 已解决, 含 IDE 化 S7-S9 三断点; 见 [docs/缺陷管理/BUG决策日志.md](docs/缺陷管理/BUG决策日志.md) BUG-001~077)

## 开发约定

- **分支**: `main` 直接开发，大功能可开 `feature/xxx`
- **Git**: 开发前 `git pull`，开发后 `git add . && git commit -m "..." && git push`
- **Commit 格式**: `type(scope): 中文简述` — type: feat/fix/docs/chore/refactor
- **环境变量**: 复制 `.env.example` → `.env`，含 LLM_API_KEY、NEO4J_PASSWORD 等
- **Neo4j 密码**: `kmatch2026`
- **API 风格**: RESTful，FastAPI 自动生成 OpenAPI 文档 (`/api/docs`)

## Claude 行为指引

### 代码探索
- **CodeGraph 已索引** → 查代码结构用 `codegraph_explore`，别用 grep 遍历
- 查函数调用链用 `codegraph_callers` / `codegraph_callees`
- 需要全局文本搜索 (注释/日志/字符串) 时用 `Grep`

### 编辑守则
- 匹配现有代码风格 (注释密度、命名约定)
- 修改 `docker-compose.yml`、`.env.example`、`README.md` 等共享文件注意影响面

### 文档维护
- 每完成一个功能模块，同步更新 `docs/devlogs/`
- 新 Bug 开 GitHub Issue（见下方 Agent skills），`docs/缺陷管理/BUG决策日志.md` 为历史存档不再新增
- 重大架构变更更新本文件 + 记 ADR (`docs/adr/`)

## Agent skills

> 配套 Matt Pocock 中文版 skills（装在 `.claude/skills/`）。engineering skills 读取下列三份配置文件。

### Issue tracker

GitHub Issues（`gh` CLI）。新 bug/任务一律开 issue。见 `docs/agents/issue-tracker.md`。

### Triage labels

5 个 canonical role（`needs-triage`/`needs-info`/`ready-for-agent`/`ready-for-human`/`wontfix`）+ 分类 label（`bug`/`refactor`/`documentation`/`competition`）。见 `docs/agents/triage-labels.md`。

### Domain docs

Single-context：根 `CONTEXT.md` + `docs/adr/`。见 `docs/agents/domain.md`。

## 首次使用

```bash
git clone <repo-url> && cd KMatch-Desktop
cp .env.example .env  # 填入 API Key
npm install && npm run dev  # 启动 Electron 开发模式
```

> **国内网络**: Docker Hub 被墙，首次 `docker-compose up` 前务必运行 `scripts/setup_docker_mirror.*` 配置镜像源。
