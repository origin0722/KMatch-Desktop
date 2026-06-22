# KMatch·知链 — 项目依赖清单

> 最后更新：2026-06-23 | 基于 `package.json` + `backend/requirements.txt` + 本地实测版本

## 0. Desktop 壳栈（Electron + Monaco）

| 依赖 | 版本 | 说明 |
|:---|:---|:---|
| `electron` | `^33.4.11` | 桌面壳主进程 |
| `electron-vite` | `^2.3.0` | Electron + Vite 集成 |
| `electron-builder` | `^25.1.0` | NSIS 安装包打包 |
| `monaco-editor` | `^0.52.0` | 代码编辑器（frontend 依赖） |
| `chokidar` | `^4.0.3` | 文件监听（v4 非 v5，ESM/CJS 兼容，见 [ADR-0004](adr/0004-file-watcher-worker-threads.md)） |
| `rollup` | (electron-vite 拉取) | watcher-worker 多入口 build |

## 1. 运行环境

| 依赖 | 版本要求 | 备注 |
|:---|:---|:---|
| Python | `>=3.10` | 推荐 3.12 |
| Node.js | `>=18` | — |
| Docker Desktop | 最新稳定版 | Neo4j + 容器化部署 |
| Git | `>=2.30` | — |
| Windows 开发者模式 | — | 首次打包 winCodeSign 符号链接需要 |

## 2. 多智能体框架（核心）

| 包名 | 最低版本 | 已测版本 | 说明 |
|:---|:---|:---|:---|
| `langgraph` | `>=1.0.0` | 1.2.5 | 多智能体编排 |
| `langgraph-checkpoint` | (自动安装) | 4.1.1 | 状态持久化 |
| `langgraph-prebuilt` | (自动安装) | 1.1.0 | 预置 Agent 模式 |
| `langgraph-sdk` | (自动安装) | 0.4.2 | SDK 工具 |
| `langchain` | `>=1.0.0` | 1.3.9 | LLM 应用框架 |
| `langchain-core` | (自动安装) | 1.4.7 | LangChain 核心抽象 |
| `langchain-openai` | `>=1.0.0` | 1.3.2 | OpenAI 兼容接口 |
| `langchain-community` | `>=0.3.0` | 0.4.2 | 社区集成 |

## 3. Web 框架（后端）

| 包名 | 最低版本 | 已测版本 | 说明 |
|:---|:---|:---|:---|
| `fastapi` | `>=0.137.0` | 0.137.1 | 异步 Web 框架 |
| `starlette` | (自动安装) | 1.3.1 | FastAPI 底层 |
| `uvicorn` | `>=0.49.0` | 0.49.0 | ASGI 服务器 |
| `httpx` | `>=0.27.0` | 0.28.1 | HTTP 客户端 |
| `httpcore` | (自动安装) | 1.0.9 | httpx 底层 |
| `python-multipart` | `>=0.0.9` | 0.0.29 | 表单解析 |

## 4. 知识图谱

| 依赖 | 版本要求 | 说明 |
|:---|:---|:---|
| Neo4j Community | `>=5.x` | Docker 镜像: `neo4j:5` |
| `neo4j` (Python) | `>=5.20.0` | 官方 Python driver |

## 5. 数据校验

| 包名 | 最低版本 | 已测版本 | 说明 |
|:---|:---|:---|:---|
| `pydantic` | `>=2.13.0` | 2.13.4 | 数据模型校验 |
| `pydantic-core` | (自动安装) | 2.46.4 | pydantic 底层引擎 |
| `jsonschema` | `>=4.20.0` | — | JSON Schema 校验 |

## 6. 测试

| 包名 | 最低版本 | 说明 |
|:---|:---|:---|
| `pytest` | `>=8.0.0` | 测试框架 |
| `pytest-asyncio` | `>=0.23.0` | 异步测试支持 |
| `pytest-cov` | `>=4.1.0` | 覆盖率报告 |

## 7. 大模型兼容

KMatch 使用 **OpenAI 兼容接口**，可接入以下模型（择一即可）：

| 模型提供商 | 所需包 | 说明 |
|:---|:---|:---|
| DeepSeek | `langchain-openai` | 通过 `base_url` 指向 DeepSeek API |
| 通义千问 | `langchain-openai` 或 `dashscope` | 兼容接口模式 |
| OpenAI | `langchain-openai` | 原生支持 |
| Anthropic Claude | `anthropic>=0.109.0` | 备选（已装 0.109.2） |

## 8. 开发工具 / 杂项

| 包名 | 最低版本 | 说明 |
|:---|:---|:---|
| `jedi` | `>=0.19.0` | Python 代码分析 |
| `pyyaml` | `>=6.0.0` | YAML 配置解析 |
| `python-dotenv` | `>=1.0.0` | `.env` 环境变量 |
| `certifi` | 最新 | CA 证书（已装 2026.5.20） |
| `cryptography` | 最新 | 加密库（已装 49.0.0） |

## 9. 前端

| 框架/库 | 版本 | 说明 |
|:---|:---|:---|
| Vue 3 | `^3.4.0` | 渐进式前端框架 |
| Element Plus | `^2.8.0` | UI 组件库 |
| AntV G6 | `^5.0.0` | 知识图谱可视化 |
| Pinia | `^2.2.0` | 状态管理（8 stores） |
| Vue Router | `^4.3.0` | 路由 |
| Vite | `^5.4.0` | 构建工具 |
| `marked` | `^18.0.5` | Markdown 渲染（AI 消息） |
| Vitest | `^2.1.9` | 单元测试 |
| `@vue/test-utils` | `^2.4.11` | Vue 组件测试 |
| `jsdom` | `^29.1.1` | Vitest DOM 环境 |

## 10. 示例/演示项目依赖

这些是 `data/example_projects/` 和 `week1_demos/` 的独立依赖，不需要在主环境安装：

| 项目 | 所需包 | 说明 |
|:---|:---|:---|
| `todo_backend` | `flask>=3.0`, `pytest>=8.0` | Flask REST API 示例 |
| `simple_crawler` | `requests>=2.31`, `beautifulsoup4>=4.12`, `pytest>=8.0` | 爬虫示例 |
| `langgraph_demo` | `langgraph`, `langchain`, `langchain-openai` | LangGraph Week1 演示 |
| `neo4j_demo` | `neo4j`, `openai`, `python-dotenv` | Neo4j Week1 演示 |

---

## 一键安装

```bash
# === 后端（主力开发环境）===
pip install \
  langgraph>=1.0.0 langchain>=1.0.0 langchain-openai>=1.0.0 langchain-community>=0.3.0 \
  fastapi>=0.137.0 "uvicorn[standard]>=0.49.0" httpx>=0.27.0 python-multipart>=0.0.9 \
  neo4j>=5.20.0 \
  pydantic>=2.13.0 jsonschema>=4.20.0 \
  jedi>=0.19.0 python-dotenv>=1.0.0 pyyaml>=6.0.0 \
  pytest>=8.0.0 pytest-asyncio>=0.23.0 pytest-cov>=4.1.0

# === 前端 ===
npm install vue@^3.4 element-plus@^2.8 @antv/g6@^5

# === Docker（Neo4j）===
docker run -d --name neo4j \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/password \
  neo4j:5
```

---

## 版本策略

| 标记 | 含义 | 示例 |
|:---|:---|:---|
| `>=X.Y.0` | 最低功能版本，同大版本内向前兼容 | `langgraph>=1.0.0` |
| （自动安装） | 由主包自动拉取，无需手动声明 | `pydantic-core` |
| （已测版本） | 团队验证可用的具体版本，遇到问题时回退至此版本 | `1.2.5` |
