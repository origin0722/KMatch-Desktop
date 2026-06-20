# KMatch·知链 — Claude 项目速查卡

> 知识图谱驱动的多智能体协同个性化学习平台 | 赛题 XH-202630 | 3人团队

## 一句话描述

以 Neo4j 四层知识图谱为共享事实底座、LangGraph 多智能体协同为核心引擎，面向 Python 学习的个性化教学平台。覆盖"无项目技能训练"和"有项目二次开发"两类场景。

## 快速启动

```bash
# 全栈启动 (Neo4j + FastAPI + Vue3)
docker-compose up -d

# 本地开发
cd backend  && pip install -r requirements.txt && uvicorn app.main:app --reload
cd frontend && npm install && npm run dev

# 导入知识库
cd backend
python scripts/validate_data.py ../data/knowledge_base/
python scripts/import_knowledge_base.py ../data/knowledge_base/
```

## 架构速览

```
前端 (Vue3+Element Plus+AntV G6, port 5173)
  ├── Home, Assessment, KnowledgeGraph, Learning
  ├── AgentView (多Agent流转可视化), Dashboard (数据看板)
  └── ProjectUpload (二次开发场景)
         │ HTTP / WebSocket
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

## 目录归属 (防冲突核心规则)

| 目录 | 归属 | 规则 |
|:---|:---|:---|
| `backend/` | **A** | 只读 for B/C |
| `frontend/` | **B** | 只读 for A/C |
| `data/knowledge_base/nodes/` | **A 统筹** | 知识节点 JSON (原 member_a/b/c 已扁平化, /api/kb CRUD 统一管理) |
| `data/knowledge_base/questions/` | **A 统筹** | 题目 JSON (/api/kb CRUD 统一管理) |
| `data/prompts/` | **C 统筹** | A/B 各自负责独立文件 |
| `docs/devlogs/A_后端/` | **A** | 不碰 |
| `docs/devlogs/B_前端/` | **B** | 不碰 |
| `docs/devlogs/C_数据/` | **C** | 不碰 |
| `docs/BUG决策日志.md` | **共享** | 追加式写入 |

**各自目录独立，不会冲突。修改他人目录前先沟通。**

## 关键文件索引

### 后端核心
- [main.py](backend/app/main.py) — FastAPI 入口，健康检查，路由注册
- [config.py](backend/app/config.py) — 全局配置 (Neo4j/LLM/Embedding Agent)
- [engine.py](backend/app/graph/engine.py) — **KnowledgeGraph 类**：图遍历、向量检索、混合检索、学习路径组装 + 项目图谱 (W6: write/get/delete_project_graph + annotate_risk/link_entity_to_knowledge)
- [code_parser/](backend/app/code_parser/) — **W6 代码解析模块**：AST 提取 (ast_parser) + Jedi 语义调用解析 (jedi_resolver) + 多文件编排 (loader)，构建项目框架层(2)/代码实体层(3)
- [agents/](backend/app/agents/) — 1 主控 + 6 子 Agent 全部实现 (orchestrator 主控 / diagnostics 学情检测 / graph_controller 图谱管控 / content_generator 内容生成 / reviewer 内容审核 / code_reviewer 代码审查 / code_tester 代码测试) + report_builder (W7② 可视化报告数据契约) + quality_metrics (W7② 赛题M5 质量检测: 幻觉率/适配率/覆盖率)
- [api/](backend/app/api/) — 业务路由 (diagnostics + graph + project + learning + kb 已实现；代码审查并入 /api/project/review，独立 /api/review 未拆分)

### 前端核心
- [router/index.js](frontend/src/router/index.js) — 7条路由: / → Home, /assessment, /graph, /learning, /agents, /dashboard, /project
- [views/](frontend/src/views/) — 7个页面组件
- [components/GraphDemo.vue](frontend/src/components/GraphDemo.vue) — G6 图谱渲染组件

### 数据层
- [data/knowledge_base/](data/knowledge_base/) — 92个 Python 知识点 (JSON, 6分类，已审核)
- [data/prompts/](data/prompts/) — 7个 Agent 系统提示词 (.txt, 全部 v0.3-final)
- [data/user_profiles/](data/user_profiles/) — 3组差异化用户画像 + 1模板 + Schema规范 (v3 格式)
- [data/example_projects/](data/example_projects/) — simple_crawler + todo_backend 示例项目
- [backend/scripts/validate_data.py](backend/scripts/validate_data.py) — **v3** 知识节点 + 用户画像双阶段校验
- [backend/scripts/import_knowledge_base.py](backend/scripts/import_knowledge_base.py) — Neo4j 导入含向量索引

### 文档
- [项目开发计划书.md](项目开发计划书.md) — 9周开发排期、赛题对标、风险管理
- [前置数据准备指南.md](前置数据准备指南.md) — 元知识库Schema、画像定义、Prompt模板
- [docs/BUG决策日志.md](docs/BUG决策日志.md) — BUG记录与决策
- [docs/devlogs/](docs/devlogs/) — 每日开发日志 (按成员分目录)

## 技术栈版本约束

| 模块 | 选型 | 版本 |
|:---|:---|:---|
| 多智能体框架 | LangGraph + LangChain | ≥1.0.0 |
| 图数据库 | Neo4j Community | 5.x (Docker) |
| 后端框架 | FastAPI | ≥0.137.0 |
| LLM 对话 | DeepSeek V4 Pro (OpenAI 兼容) | deepseek-v4-pro |
| LLM Embedding | 千问 text-embedding-v2 | 1536维 |
| 前端框架 | Vue3 + Element Plus + AntV G6 | 3.4+/2.8+/5.x |
| 代码解析 | Python AST + Jedi | ≥0.19 |
| 容器化 | Docker + docker-compose | — |

## 当前开发阶段

**第1周 (7月1-5日): 环境搭建与技术验证** ← 技术验证已完成，前端骨架就绪
**第2周 (7月7-11日): 多智能体核心框架** ← A 已超前完成（学情检测→审核局部闭环）
**第3周 (7月14-18日): 知识图谱引擎开发** ← A 端 graph_controller Agent + 图谱查询 API 已交付
**第4周 (7月21-25日): 后端全流程打通** ← A 端 content_generator + reviewer 内容审核循环已交付
**第5周 (7月28日-8月1日): 前端全面开发+联调** ← A 端 interactive 答题接口 + 动态反馈再生已交付 (assess/submit/feedback)
**第6周 (8月4-8日): 进阶功能——二次开发场景** ← A 端 4 子任务全部交付 (代码解析+项目图谱+代码审查+code_tester，场景二解析→图谱→审查→测试全链路就绪)

已完成的前置准备 (6/18 更新):
- ✅ 92个 Python 元知识节点 (v2 Schema, 全部通过验证)
- ✅ KnowledgeGraph 引擎骨架 (engine.py — 图遍历/向量/混合检索/路径组装)
- ✅ Neo4j 导入 + 验证脚本 (validate_data.py v3: 知识节点 + 画像双阶段校验 + recommended_path 结构校验)
- ✅ 7个 Agent 系统提示词 (.txt, 全部 v0.3-final)
- ✅ 3组用户画像 JSON + 1模板 (v3 格式统一, recommended_path 对象结构)
- ✅ 画像 JSON Schema 规范 (profile_schema.json)
- ✅ 统一日志模块 (app/utils/logging.py)
- ✅ engine.py print() → logging + 无声吞错修复 (ERROR级别+完整调用栈)
- ✅ 2个示例项目 (simple_crawler + todo_backend)
- ✅ Docker Compose 三服务编排
- ✅ 前端 Vue3 骨架 (7页面 + 路由)
- ✅ 多 Agent 核心框架 (orchestrator + diagnostics + reviewer + graph_controller + content_generator)
- ✅ POST /api/diagnostics/assess 路由 + lifespan 全局单例 (KG/OpenAI/workflow)
- ✅ 知识图谱管控 Agent (graph_controller — 画像→学习路径组装 + 节点状态写回)
- ✅ 领域知识生成 Agent (content_generator — 讲义/实操指南/分阶测试题 + source_nodes 溯源)
- ✅ 内容审核 Agent 双模式 (画像审核 + 生成内容审核，BUG-016 已解决)
- ✅ /api/graph 查询 API (10 路由: node/category/difficulty/tags/prereq/dependents/search/hybrid/path/status)
- ✅ interactive 答题接口 (POST /assess·/submit·/feedback — 两步答题 + 动态反馈再生, W5)
- ✅ demo 模式 SSE 流式测评 (POST /assess/stream — 逐步推送节点进度, 解决全流程2-4分钟超前端60s超时, W7③)
- ✅ 代码解析模块 (code_parser — AST 提取函数/类/方法/参数/调用/继承 + Jedi 语义调用解析, W6)
- ✅ 项目图谱生成 (engine.write/get/delete_project_graph — 落 Neo4j 四层图谱第2/3层, :ProjectEntity 命名空间隔离)
- ✅ /api/project 路由 (POST /parse·GET /graph·/examples·POST /review·POST /test — 解析+落库+G6 结构+代码审查+代码测试, W6)
- ✅ 代码审查 Agent (code_reviewer — AST 安全检查硬规则+LLM 对照领域规范审查，场景二 Step6①, W6)
- ✅ 代码测试 Agent (code_tester — 图谱驱动Pytest生成+分层沙箱执行+pytest-cov覆盖率+反向标注风险节点，场景二 Step6②, W6)
- ✅ 395 项后端 + 42 项前端单元测试全部通过 (含 W7② BUG-039~044 + B/C 端 BUG-045~056 前端修复 + W7③ BUG-057~073 后端代码审查全量修复 + W7③ 知识库管理CRUD API + SSE流式测评)
- ✅ 赛题 M5 质量检测指标 (quality_metrics — 幻觉率<5%/适配率≥85%/覆盖率≥90%, per-session实时+批量脚本run_quality_test.py聚合写报告, 3画像实测全达标, W7②)
- ✅ 运行时 prompt 补齐优化 (5级脚手架补入运行时+反馈路径难度强制赋值BUG-044+6初稿对齐, W7②)
- ✅ 知识库管理 CRUD API (/api/kb — 节点+题目增删改查, JSON为源写后同步Neo4j, ID自动递增, prerequisites重建+embedding重算, W7③)
- ⬜ B/C 需审阅 A 代理完成的数据工作

BUG 清单: 73 条 (73 已解决, 含 C 端 BUG-045~047 前端 XSS/emoji + B 端 BUG-048~056 图谱无边/搜索竞态/mastery + W7③ BUG-057~073 后端代码审查全量修复: code_tester崩溃/diagnostics走题库/driver泄漏/async阻塞/弱项cap/并发写/图谱原子性/循环检测/key_points/先LLM后skip/孤儿题/内容阶段路由/while-True/Jedi偏移/entity碰撞/双重惩罚/边角) — 详见 docs/BUG决策日志.md

## 开发约定

- **分支策略**: 第1-4周 `main` 直接开发; 第5-6周 `feature/xxx`; 第7-9周 `main` 冲刺
- **Git**: 每次开发前 `git pull`，开发后 `git add . && git commit -m "..." && git push`
- **Commit 格式**: 中文简述，关键节点注明 `feat:` `fix:` `docs:` `chore:`
- **环境变量**: 复制 `.env.example` → `.env`，包含 LLM_API_KEY、NEO4J_PASSWORD 等
- **Neo4j 密码**: `kmatch2026`
- **API 风格**: RESTful，FastAPI 自动生成 OpenAPI 文档 (`/api/docs`)
- **代码审查**: A 和 B 的关键代码提交前由 C 审查

## Claude 行为指引

### 代码探索
- **CodeGraph 已索引** → 查代码结构用 `codegraph_explore`，别用 grep 遍历
- 查函数调用链用 `codegraph_callers` / `codegraph_callees`
- 需要全局文本搜索 (注释/日志/字符串) 时用 `Grep`

### 编辑守则
- 匹配现有代码风格 (注释密度、命名约定)
- 改他人目录前提醒沟通
- 修改 `docker-compose.yml`、`.env.example`、`README.md` 等共享文件后手动合并

### 文档维护
- 每完成一个功能模块，同步更新 [docs/devlogs/](docs/devlogs/) 对应成员目录
- 遇到 Bug 记录到 [docs/BUG决策日志.md](docs/BUG决策日志.md)
- 重大架构变更更新本文件

## 首次使用本项目 (协作者)

```bash
git clone <repo-url> && cd KMatch
cp .env.example .env  # 填入 API Key

# 国内环境: 配置 Docker 镜像源 (否则 docker pull 超时)
# Windows: powershell -ExecutionPolicy Bypass -File scripts/setup_docker_mirror.ps1
# Linux/macOS/Git Bash: bash scripts/setup_docker_mirror.sh
# 配置后重启 Docker Desktop 生效

codegraph init -i      # 初始化代码索引 (可选，推荐)
docker-compose up -d   # 启动所有服务
```

> **国内网络**: Docker Hub 被墙，首次 `docker-compose up` 前务必运行 `scripts/setup_docker_mirror.*` 配置镜像源，否则 neo4j:5-community 镜像无法拉取。
