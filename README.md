# KMatch·知链 —— 知识图谱驱动的多智能体协同个性化学习平台

> 赛题 XH-202630 ｜ 单人全栈 ｜ **正式版 v1.3.4** ｜ Windows 桌面 IDE

以四层知识图谱为共享事实底座、LangGraph 多智能体协同为核心引擎，面向 **Python 学习** 的个性化教学桌面应用。覆盖 **场景一（无项目技能训练）** 与 **场景二（有项目二次开发）** 两类场景：内置 Monaco 代码编辑器、AI 助手、知识图谱、项目图谱、Git 版本管理、运行历史与数据看板，**端用户免 Docker、免命令行配置**。

> 📦 正式版发行物：`KMatch·知链-1.3.4-x64.exe` — [GitHub Release v1.3.4](https://github.com/origin0722/KMatch-Desktop/releases/tag/v1.3.4)
> 📖 详尽功能说明：[docs/交付材料/软件说明_v1.3.0.md](docs/交付材料/软件说明_v1.3.0.md)
> 🧪 真机核验清单：[docs/交付材料/真机核验清单_v1.0.0.md](docs/交付材料/真机核验清单_v1.0.0.md)

## 功能速览

| 模块 | 能力 |
|:---|:---|
| 桌面 IDE | 导航侧栏（可折叠）/ 资源管理器（懒加载目录树）/ Monaco 多标签编辑 / 文件内联预览 |
| AI 助手 | OpenAI 兼容多厂商 + SSE 流式 + 13 工具调用（写文件审批门/执行代码/图谱/联网）+ 苏格拉底导学 + 会话分支 + 流式指标栏（首 token·tok/s·缓存命中） |
| 学习引擎 | 学情测评（**VARK 三维**）→ 个性化路径（BFS+掌握度+折周估时）→ 分层讲义/实操指南/分阶测试题（5 节点扩量）→ 四维审核打回再生 → 动态迭代（降维/进阶）→ 画像跨次进化 |
| 知识图谱 | 四层图谱（6 域 222 节点 + 93 题库）+ 动态建域 + 路径查找 + 历史图谱快照 |
| 项目图谱 | 打开项目自动解析 + Monaco 符号联动 + 架构解读 + 代码审查/测试双 Agent + **LangGraph 流程编排（/api/project/pipeline）** |
| Git 仓库 | 克隆远程（自动切换项目）/ 初始化 / 状态着色列表 / 暂存提交 / 拉取推送 / 最近提交 / 文件变动实时刷新（无需终端） |
| 运行历史 | 结构化 run 事件落盘 + 复盘 + 一键重跑 / 重新测评 + 流程图 DAG |
| 设置页 | AI 助手 / 学习引擎（Key 自动回退 AI 助手）/ 联网搜索（一键测试）/ 自定义厂商 / 网络代理 / 数据与质量 / 高级参数 / **配置导入导出** / 主题皮肤（**默认深青珊瑚**） |

## 技术栈

| 模块 | 选型 | 版本 |
|:---|:---|:---|
| 桌面壳 | Electron + electron-vite | 33+ / 2.3+ |
| 编辑器 | Monaco Editor | 0.52+ |
| 前端 | Vue3 + Element Plus + AntV G6 | 3.4+ / 2.8+ / 5.x |
| 后端 | FastAPI + LangGraph（PyInstaller sidecar） | ≥0.137.0 / ≥1.0.0 |
| 知识图谱 | 嵌入式 `EmbeddedGraphStore`（默认，免 Docker）/ 可选 Neo4j 5.x | — |
| LLM 对话 | DeepSeek V4 Pro（OpenAI 兼容，可换任意厂商） | deepseek-v4-pro |
| LLM Embedding | 通义千问 | text-embedding-v2 (1536 维) |

## 快速启动

```bash
# Electron + Vite HMR 开发模式
npm install && npm run dev

# 仅前端 dev（浏览器，不走 Electron）
cd frontend && npm install && npm run dev

# 全栈（Neo4j + FastAPI + 前端，仅开发/演示）
docker-compose up -d
cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload
```

> **免 Docker 运行**：安装包零配置，默认进程内嵌入式存储（`EmbeddedGraphStore`，无 Docker/JVM/端口）；
> 开发期无 Docker 可设 `GRAPH_STORE=embedded` 单进程跑后端，或 `GRAPH_STORE=auto` 自动探测。
> 方案见 [docs/架构与设计/轻量化改造方案_免Docker_嵌入式存储.md](docs/架构与设计/轻量化改造方案_免Docker_嵌入式存储.md)。

> **端用户配置**：所有 API Key 均在 **设置页** 完成（AI 助手 / 学习引擎 / 联网搜索），
> 无需修改 `.env`；学习引擎未配独立 Key 时自动回退使用 AI 助手 Key。

## 打包（Windows 安装包）

```bash
# 1. 后端 PyInstaller 打 sidecar（仅后端 Python 改动时重跑）
cd backend && pyinstaller KMatchBackend.spec --noconfirm --distpath ../backend-dist --workpath ../build/pyinstaller

# 2. 前端 + Electron 打 NSIS 安装包（国内网络必须配镜像）
$env:ELECTRON_BUILDER_BINARIES_MIRROR='https://npmmirror.com/mirrors/electron-builder-binaries/'
$env:ELECTRON_MIRROR='https://npmmirror.com/mirrors/electron/'
npm run build:win
```

产物 `release/KMatch·知链-1.3.4-x64.exe`，装后 sidecar 自启；**端用户免 Docker**。首次打包需开 Windows 开发者模式（winCodeSign 符号链接）。详见 [CLAUDE.md](CLAUDE.md)。

## 项目结构

```
KMatch-Desktop/
├── electron/          # Electron 主进程 + preload + IPC（fs/workspace/http/git/proxy/watcher）+ watcher worker
├── frontend/src/
│   ├── ide/           # 导航侧栏 / FileExplorer / MainArea / GitView / AssistantPanel / settings / ...
│   ├── stores/        # Pinia: workspace / sidebar / chat / assessment / session / projectGraph / theme / aiSettings / agentLlm
│   ├── views/         # Workspace 壳 + 学习视图（LearningSession / KnowledgeGraph / ProjectGraphView / Dashboard / Learning）
│   └── __tests__/     # Vitest 单测（507 用例）
├── backend/app/       # FastAPI + LangGraph（agents/ graph/ api/）+ tests（726 通过 / 2 跳过）
├── backend-dist/      # PyInstaller sidecar 产物（gitignore）
├── data/              # 222 知识节点 / 8 提示词 / 10 组用户画像 / 93 题库 / 示例项目
├── docs/              # 文档中心 — 分类索引见 docs/README.md
├── CONTEXT.md         # 领域词汇表
└── CLAUDE.md / AGENTS.md  # 项目速查卡
```

## 质量与赛题对标

- **测试**：前端 **507 用例全过**（65 文件，Vitest）；后端 **726 通过 / 2 跳过**（Pytest）。
- **M5 指标**：幻觉率 <5% / 适配率 ≥85% / 覆盖率 ≥90%（独立裁判双口径，3 组画像实测达标）。
- **赛题要求**：≥3 个分工明确 Agent（实际 7+2）、分析-生成-校验-决策闭环、先验画像（含学历/专业背景 + VARK 学习风格）+专业知识库融合、
  三形态个性化资源、可视化学情报告（盲区定位/难度匹配曲线/路径规划图）、动态迭代机制、多 Agent 申诉-复审辩论 + 独立裁判交叉验证抗幻觉、数据合规、场景二延伸——自查表见
  [docs/项目规划/项目开发计划书.md §9](docs/项目规划/项目开发计划书.md#九赛题对标自查清单)。

## 开发约定

- 分支：`main` 直接开发，大功能开 `feature/xxx`。
- Commit：`type(scope): 中文简述`（feat/fix/docs/chore/refactor）。
- Bug/任务：开 GitHub Issue（见 [docs/agents/issue-tracker.md](docs/agents/issue-tracker.md)）。
- 文档：每完成模块更新 `docs/devlogs/`；架构决策记 `docs/adr/`。

> 完整文档导航见 [docs/README.md](docs/README.md)；详尽功能说明见 [docs/交付材料/软件说明_v1.3.0.md](docs/交付材料/软件说明_v1.3.0.md)。
