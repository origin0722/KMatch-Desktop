# KMatch·知链 —— 知识图谱驱动的多智能体协同个性化学习平台

> 赛题 XH-202630 | 单人全栈 | 桌面 IDE 形态

以 Neo4j 四层知识图谱为共享事实底座、LangGraph 多智能体协同为核心引擎，面向 Python 学习的个性化教学平台。覆盖"无项目技能训练"与"有项目二次开发"两类场景。当前形态为 **KMatch-Desktop**：Electron + Monaco 桌面 IDE，统一收编原 Web 前端学习功能并接入 AI 助手。

> 原 KMatch Web（Vue3 + G6，三人协作时代）已收编进 Desktop，旧文档归档于 [docs/legacy/三人协作时代/](docs/legacy/三人协作时代/)。

## 技术栈

| 模块 | 选型 | 版本 |
|:---|:---|:---|
| 桌面壳 | Electron + electron-vite | 33+ / 2.3+ |
| 编辑器 | Monaco Editor | 0.52+ |
| 前端 | Vue3 + Element Plus + AntV G6 | 3.4+ / 2.8+ / 5.x |
| 后端 | FastAPI | ≥0.137.0 |
| 多智能体 | LangGraph + LangChain | ≥1.0.0 |
| 知识图谱 | Neo4j Community | 5.x (Docker) |
| LLM 对话 | DeepSeek V4 Pro（OpenAI 兼容） | deepseek-v4-pro |
| LLM Embedding | 通义千问 | text-embedding-v2 (1536维) |

## 架构一图流

```text
KMatch-Desktop (Electron + Monaco)
  ├── 活动栏 / 资源管理器 / 主区 (code/graph/learning-session)
  ├── AI 助手 (AssistantPanel) — 多模型对话 SSE + 工具调用 + write_file 审批门 + 导学模式
  └── 状态栏
        │ IPC (window.api.*)
  Electron Main — IPC + backend sidecar + 文件监听 Worker (worker_threads + chokidar v4)
        │ HTTP/SSE (127.0.0.1:8000)
  Backend (FastAPI + LangGraph)
  ├── orchestrator 编排 6 子 agent（学情检测/图谱管控/内容生成/内容审核/代码审查/代码测试）
  └── KnowledgeGraph engine — Neo4j 图遍历 + 向量混合检索
        │ Bolt
  Neo4j — 四层图谱 (领域元知识 → 项目框架 → 代码实体 → 演化扩展) + 原生向量索引
```

完整进程拓扑 / 数据流 / 状态更新流见 [docs/架构与设计/ARCHITECTURE.md](docs/架构与设计/ARCHITECTURE.md)；领域词汇见 [CONTEXT.md](CONTEXT.md)。

## 快速启动

```bash
# Electron + Vite HMR 开发模式
npm install && npm run dev

# 仅前端 dev（浏览器，不走 Electron）
cd frontend && npm install && npm run dev

# 全栈（Neo4j + FastAPI + 前端）
docker-compose up -d
cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload
```

> **免 Docker 运行**：装好安装包后零配置（默认进程内嵌入式存储 `EmbeddedGraphStore`，无 Docker/JVM/端口）；开发期无 Docker 可设 `GRAPH_STORE=embedded` 单进程跑后端，或 `GRAPH_STORE=auto` 自动探测（Neo4j 可达则用 neo4j）。方案见 [docs/架构与设计/轻量化改造方案_免Docker_嵌入式存储.md](docs/架构与设计/轻量化改造方案_免Docker_嵌入式存储.md)。

环境变量：复制 `.env.example` → `.env`（`LLM_API_KEY` / `NEO4J_PASSWORD` 等，Neo4j 密码 `kmatch2026`）。首次 `docker-compose up` 前先跑 `scripts/setup_docker_mirror.*` 配置镜像源（国内网络）。

## 打包（Windows 安装包）

```bash
# 1. 后端 PyInstaller 打 sidecar（仅后端 Python 改动时重跑）
cd backend && pyinstaller KMatchBackend.spec --noconfirm --distpath ../backend-dist --workpath ../build/pyinstaller

# 2. 前端 + Electron 打 NSIS 安装包（国内网络必须配镜像）
ELECTRON_BUILDER_BINARIES_MIRROR=https://npmmirror.com/mirrors/electron-builder-binaries/ \
  npm run build:win
```

产物 `release/KMatch·知链-1.0.1-x64.exe`，装后 sidecar 自启；**端用户免 Docker**（安装包默认嵌入式存储，Neo4j 仅为可选 dev/演示后端）。首次打包需开 Windows 开发者模式（winCodeSign 符号链接）。详见 [CLAUDE.md](CLAUDE.md)。

> **可选：语义检索离线种子** — 先在 Neo4j 模式向量化后运行 `cd backend && python scripts/export_embeddings.py`，生成的 `data/local/embeddings.json` 会随 extraResources 打进安装包，端用户首跑即语义可用（免首跑自动回填）。嵌入式运行时可变数据（掌握状态/项目图谱/向量缓存）落用户 appData（`KMATCH_LOCAL_DIR`），安装包内 `data/local` 不在本库提交（gitignore）。

## 项目结构

```
KMatch-Desktop/
├── electron/          # Electron 主进程 + preload + IPC + watcher worker
├── frontend/src/
│   ├── ide/           # ActivityBar / FileExplorer / MainArea / MonacoEditor / AssistantPanel ...
│   ├── stores/        # Pinia: chat / assessment / session / projectGraph / workspace / sidebar / aiSettings / theme
│   └── views/         # Workspace 壳 + 学习视图
├── backend/app/       # FastAPI + LangGraph (agents/ graph/ api/)
├── data/              # 92 知识点 + 7 提示词 + 用户画像
├── docs/              # 文档中心 — 分类索引见 docs/README.md
│   ├── 项目规划/ 指南手册/ 架构与设计/ adr/ 质量与验收/
│   ├── 接口对接/ 评审记录/ 研究与调研/ 合规与安全/ 交付材料/ 缺陷管理/
│   └── agents/ devlogs/ legacy/ superpowers/
├── CONTEXT.md         # 领域词汇表
└── CLAUDE.md          # 项目速查卡
```

> 全部文档已统一收纳进 `docs/` 并按主题分类，导航见 [docs/README.md](docs/README.md)。

## 开发约定

- 分支：`main` 直接开发，大功能开 `feature/xxx`。
- Commit：`type(scope): 中文简述`（feat/fix/docs/chore/refactor）。
- Bug/任务：开 GitHub Issue（见 [docs/agents/issue-tracker.md](docs/agents/issue-tracker.md)）；`docs/缺陷管理/BUG决策日志.md` 为历史存档。
- 文档：每完成模块更新 `docs/devlogs/`；架构决策记 `docs/adr/`。

## 赛题功能锚点

场景一全流程闭环 · 场景二全链路 · 赛题(3)①图谱可视化 · 赛题(4)②动态追问导学 · M5 质量指标（幻觉率<5% / 适配率≥85% / 覆盖率≥90%）· 四层图谱契约。

> 开发排期与赛题对标见 [docs/项目规划/项目开发计划书.md](docs/项目规划/项目开发计划书.md)；完整文档导航见 [docs/README.md](docs/README.md)。
