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
- [frontend/src/ide/ActivityBar.vue](frontend/src/ide/ActivityBar.vue) — 活动栏 (视图切换 + 工具开关, 单一指示模型)
- [frontend/src/ide/FileExplorer.vue](frontend/src/ide/FileExplorer.vue) — 文件资源管理器 (code 视图内)
- [frontend/src/ide/MainArea.vue](frontend/src/ide/MainArea.vue) — 主区视图装载 (code/graph/assessment/learning/agents/dashboard)
- [frontend/src/ide/EditorTabs.vue](frontend/src/ide/EditorTabs.vue) — 多标签页
- [frontend/src/ide/MonacoEditor.vue](frontend/src/ide/MonacoEditor.vue) — Monaco 编辑器
- [frontend/src/ide/AssistantPanel.vue](frontend/src/ide/AssistantPanel.vue) — AI 助手面板
- [frontend/src/ide/StatusBar.vue](frontend/src/ide/StatusBar.vue) — 底部状态栏
- [frontend/src/stores/sidebar.js](frontend/src/stores/sidebar.js) — IDE 布局状态 (单一指示模型)
- [frontend/src/stores/workspace.js](frontend/src/stores/workspace.js) — 工作区/文件状态
- [frontend/src/stores/theme.js](frontend/src/stores/theme.js) — 亮暗主题
- [frontend/src/stores/assessment.js](frontend/src/stores/assessment.js) — 学情测评状态 (含 interactive 三阶段 + learningReport)
- [frontend/src/stores/chat.js](frontend/src/stores/chat.js) — AI 助手对话 (SSE 流式 + 工具调用循环 + write_file 审批门 + 多厂商)
- [backend/app/api/chat.py](backend/app/api/chat.py) — AI 对话 SSE 后端 (/api/chat/completions + /models + /safety-check)
- [backend/app/agents/code_safety.py](backend/app/agents/code_safety.py) — 纯 Python AST 安全检查 (hard_check_code_safety, 供 chat 审批门复用)

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
- [项目开发计划书.md](项目开发计划书.md) — 9 周排期 + 赛题对标
- [docs/BUG决策日志.md](docs/BUG决策日志.md) — BUG 记录与决策
- [docs/devlogs/](docs/devlogs/) — 开发日志

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

**阶段0** (6/19): 迁移现有 Vue 前端 + 双场景路由骨架 ✅
**阶段1** (6/19-20): Electron 壳 + Monaco IDE + TRAE 风格亮暗主题 + IDE 三栏布局 + 学习功能收编 ✅
  - 阶段1.5: 收编学习功能进 IDE 侧栏 ✅
  - 阶段1.6: 三栏布局重构 — 主区多视图 + 右侧 AI 面板 ✅
  - 阶段1.7: 去顶部 Tab + 修活动栏重复指示 + 空白/黑屏修复 ✅
  - 阶段1.8: 设计系统重构 (--km-* token + Apix 风格暖 Indigo 主题) ✅
**阶段2** (6/20): AI 助手 — 多模型对话 SSE + 工具调用循环 (read_file/list_directory) + 工作区上下文注入 ✅
**阶段2.1** (6/20): 修赛题 3 断点 ✅
  - S7: Learning 视图(≥3形态资源)挂载进主区
  - S8: Dashboard M5 指标改用后端真实 learning_report (不再伪造恒绿)
  - S9: interactive 测评三阶段闭环 (出题→答题→动态反馈), 接通 submit/feedback
**阶段3** (6/21): write_file 工具 + 权限审批门 ✅
  - 阶段3.1: write_file 工具 + 权限审批门 (复用 hard_check_code_safety)
    · 后端抽 `app/agents/code_safety.py` (纯 Python AST 安全检查, 无 langchain/neo4j 依赖), code_reviewer re-export 保持向后兼容
    · 新增 `POST /api/chat/safety-check` 端点 (.py 才真检, high 阻断 / medium 提示)
    · 前端 chat.js: write_file 工具 + pendingApproval 审批门 (safety 预检 → 用户可编辑内容 → 批准/拒绝 → 写后刷新文件树+打开文件)
    · AssistantPanel.vue: 审批卡 UI (安全预检结果 + 可编辑内容 + 批准/拒绝)
**阶段4** (待做): 图谱委派工具 (code_review/code_test/generate_project_graph) + Monaco 符号联动 ← **下一步**
**阶段5** (待做): 沙箱强化 (DockerSandboxExecutor) + PyInstaller 打包 backend sidecar
**已知待修** (见 docs/Apix借鉴与代码审查报告_2026-06-20.md): SSE 打包后断流 (chat/diagnostics 需改走 window.api.http.stream)、渲染层打包加载路径 + backend sidecar 打包 (阶段5)、chat.py SSE 阻塞事件循环 (改 AsyncOpenAI)、沙箱泄露环境密钥 (env 白名单)、切视图丢 Monaco 未保存内容 (改 v-show 常驻)。

### 原 KMatch 后端已交付项
- ✅ 92 个 Python 元知识节点 + Neo4j 导入 + 验证
- ✅ 7 个 Agent 系统提示词 (全部 v0.3-final)
- ✅ 6 个 Agent 全部实现 (orchestrator/diagnostics/graph_controller/content_generator/reviewer/code_reviewer/code_tester)
- ✅ 场景一全流程闭环 (学情画像→图谱组装→资源生成→审核→交付→反馈迭代)
- ✅ 场景二全链路 (代码解析→项目图谱→代码审查→代码测试)
- ✅ 395 后端 + 42 前端单元测试全部通过
- ✅ 赛题 M5 质量检测指标 (幻觉率<5%/适配率≥85%/覆盖率≥90%)
- ✅ 知识库管理 CRUD API
- ✅ SSE 流式测评

BUG 清单: 76 条 (76 已解决, 含 IDE 化 S7-S9 三断点)

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
- 遇到 Bug 记录到 `docs/BUG决策日志.md`
- 重大架构变更更新本文件

## 首次使用

```bash
git clone <repo-url> && cd KMatch-Desktop
cp .env.example .env  # 填入 API Key
npm install && npm run dev  # 启动 Electron 开发模式
```

> **国内网络**: Docker Hub 被墙，首次 `docker-compose up` 前务必运行 `scripts/setup_docker_mirror.*` 配置镜像源。
