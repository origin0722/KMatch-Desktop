# KMatch·知链 —— 知识图谱驱动的多智能体协同个性化学习平台

> **赛题编号**：XH-202630 | **团队规模**：3 人 | **开发周期**：2026/7/1 — 8/31

## 项目简介

KMatch 是一个以四层知识图谱为共享事实底座、以多智能体协同决策为核心引擎的个性化学习平台。系统覆盖"无项目定向技能训练"与"有项目二次开发能力提升"两类核心场景，实现"学情画像 → 多智能体协同 → 个性化资源生成 → 交互反馈 → 动态决策更新"的全流程闭环。

## 技术栈

| 模块 | 选型 | 版本 |
|:---|:---|:---|
| 多智能体框架 | LangGraph + LangChain | ≥1.0.0 / ≥1.0.0 |
| 知识图谱 | Neo4j Community | ≥5.x (Docker) |
| 后端 | FastAPI | ≥0.137.0 |
| 前端 | Vue3 + Element Plus + AntV G6 | 3.4+ / 2.8+ / 5.x |
| LLM 对话 | DeepSeek V4 Pro (OpenAI 兼容) | deepseek-v4-pro |
| LLM Embedding | 通义千问 (OpenAI 兼容) | text-embedding-v2 (1536维) |
| 容器化 | Docker + docker-compose | — |

## 快速启动

### 1. 环境要求

- Python 3.12+
- Node.js 18+
- Docker Desktop
- Git

### 2. 一键启动

```bash
# 启动所有服务（Neo4j + FastAPI + 前端）
docker-compose up -d

# 或本地开发模式
cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload
cd frontend && npm install && npm run dev
```

### 3. 导入知识库

```bash
cd backend
python scripts/validate_data.py ../data/knowledge_base/
python scripts/import_knowledge_base.py ../data/knowledge_base/
```

## 部署详解

### 方式 A：Docker Compose（推荐，评委/演示用）

三服务编排：Neo4j 5.x + FastAPI 后端 + Vue3 前端。

```bash
# 1. 克隆 + 配置环境变量
git clone <repo-url> && cd KMatch
cp .env.example .env   # 填入 LLM_API_KEY 等（见下文环境变量）

# 2. 国内网络：配置 Docker 镜像源（否则 docker pull 超时）
#    Windows: powershell -ExecutionPolicy Bypass -File scripts/setup_docker_mirror.ps1
#    Linux/macOS/Git Bash: bash scripts/setup_docker_mirror.sh
#    配置后重启 Docker Desktop 生效

# 3. 启动全部服务
docker-compose up -d

# 4. 导入知识库（首次必须，建图 + 向量索引）
docker exec kmatch-backend python scripts/import_knowledge_base.py /data/knowledge_base/

# 5. 查看日志 / 停止
docker-compose logs -f backend
docker-compose down
```

启动后访问：
- **前端**：http://localhost:5173 （首页 / 测评 / 图谱 / 学习 / Agent可视化 / 看板 / 项目上传）
- **后端 API 文档**：http://localhost:8000/api/docs （Swagger UI）
- **Neo4j 浏览器**：http://localhost:7474 （密码见 .env，默认 kmatch2026）

### 方式 B：本地开发（分服务启动）

适合开发调试，各服务独立重启。

```bash
# 1. 起 Neo4j（用 Docker 单独起，或本地装）
docker run -d --name kmatch-neo4j -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/kmatch2026 \
  -v $(pwd)/data/knowledge_base:/import/knowledge_base:ro \
  neo4j:5-community

# 2. 后端
cd backend
python -m venv .venv && .venv\Scripts\activate  # Windows
pip install -r requirements.txt
python scripts/import_knowledge_base.py ../data/knowledge_base/  # 首次导入
uvicorn app.main:app --reload --port 8000

# 3. 前端（另开终端）
cd frontend
npm install
npm run dev   # http://localhost:5173
```

### 环境变量（.env）

复制 `.env.example` → `.env`，必填项：

| 变量 | 说明 | 示例 |
|:---|:---|:---|
| `LLM_API_KEY` | DeepSeek API Key | `sk-xxx` |
| `LLM_BASE_URL` | LLM 接口地址 | `https://api.deepseek.com/v1` |
| `LLM_MODEL` | 对话模型 | `deepseek-v4-pro` |
| `EMBEDDING_API_KEY` | 千问 Embedding Key（未设则 fallback LLM_*） | `sk-xxx` |
| `EMBEDDING_BASE_URL` | Embedding 接口 | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `EMBEDDING_MODEL` | 向量模型 | `text-embedding-v2` |
| `NEO4J_URI` | Neo4j Bolt 地址 | `bolt://localhost:7687` |
| `NEO4J_PASSWORD` | Neo4j 密码 | `kmatch2026` |

> LLM/Embedding 未配置（保留 `sk-placeholder`）时系统降级：不调 LLM、向量检索退化为纯图模式，仍可启动用于界面演示（但测评/生成/质量检测不可用）。

### 知识库管理（运行时扩展）

知识节点/题目支持通过 API 增删改查（JSON 为源，写后同步 Neo4j）：

```bash
# 创建知识点（ID 自动递增）
curl -X POST http://localhost:8000/api/kb/nodes -H "Content-Type: application/json" -d '{...}'

# 创建题目
curl -X POST http://localhost:8000/api/kb/questions -H "Content-Type: application/json" -d '{...}'
```

完整 CRUD 端点 + 引入新领域流程见 [docs/知识库扩展指南.md](docs/知识库扩展指南.md)。

### 常见问题

- **`docker pull` 超时**：国内网络被墙，先跑 `scripts/setup_docker_mirror.*` 配置镜像源。
- **Neo4j 连接失败（503）**：确认 Neo4j 已起（`docker ps`），`.env` 的 NEO4J_URI/PASSWORD 正确。
- **测评/生成无响应**：LLM_API_KEY 未配置或额度耗尽，查 `docker-compose logs backend`。
- **图谱/向量检索降级**：EMBEDDING_API_KEY 未配，系统自动退化为纯图模式（不影响启动）。

## 项目结构

```
KMatch/
├── backend/         # FastAPI + LangGraph 后端
│   ├── app/         # 主应用（agents, graph, api, data, utils）
│   ├── scripts/     # 数据导入与验证脚本
│   └── tests/       # Pytest 单元测试
├── frontend/        # Vue3 + Element Plus + G6 前端
├── data/
│   ├── knowledge_base/
│   │   ├── nodes/       # 知识节点 JSON（92 个，CRUD API 管理）
│   │   └── questions/   # 题目 JSON（276 题，CRUD API 管理）
│   ├── prompts/     # 7 个 Agent 系统提示词
│   └── user_profiles/ # 用户画像
├── week1_demos/     # 第1周技术验证 Demo
└── docs/            # 架构文档、开发日志、BUG 决策、扩展指南
```

## 团队成员

| 角色 | 职责 |
|:---|:---|
| A — 后端负责人 | 多智能体框架、知识图谱引擎、FastAPI、系统集成 |
| B — 前端负责人 | Vue3 前端、G6 图谱可视化、Agent 协同可视化 |
| C — 数据与质量负责人 | 元知识库、Prompt 工程、测试数据、文档与视频 |

## 里程碑

| 检查点 | 时间 | 内容 |
|:---|:---|:---|
| M0 | 6/30 前 | 前置数据就绪 |
| M1 | 第1周末 | 技术验证完成 |
| M2 | 第4周末 | 无项目场景后端闭环 |
| M3 | 第5周末 | 前端联调完成 |
| M4 | 第6周末 | 二次开发场景完成 |
| M5 | 第7周末 | 质量检测达标 |
| M6 | 第8周末 | 全部材料就绪 |
| M7 | 9/5 前 | 最终提交 |
