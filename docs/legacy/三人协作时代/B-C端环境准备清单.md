# B/C 端环境准备清单

> **用途**: B/C 照着一步步把环境起起来。分两种模式，按阶段选。
> **维护**: A 端（后端）。问题找 A。
> **基准**: main 分支，2026-06-18

---

## 〇、先选模式

| 模式 | 起什么 | 谁用 | 何时用 |
|:---|:---|:---|:---|
| **精简模式** | Neo4j + 后端 + 前端（LLM 不配） | B 日常、C 数据阶段 | W3~W6 开发期 |
| **全栈模式** | Neo4j + 后端 + 前端 + LLM + Embedding | 全员 | W7~W9 冲刺联调 |

> B 写前端日常用 mock 即可，**每周一次切精简模式验证降级/session**。LLM Key 要钱且慢，不必每天配。

---

## 一、精简模式（推荐 B 日常 + C 数据阶段）

### 步骤 1：拉代码

```bash
git pull
```

### 步骤 2：配 Docker 镜像源（国内必做，否则拉不下 neo4j 镜像）

```bash
# Windows PowerShell（管理员）
powershell -ExecutionPolicy Bypass -File scripts/setup_docker_mirror.ps1

# Git Bash / Linux / macOS
bash scripts/setup_docker_mirror.sh
```

⚠️ 跑完**重启 Docker Desktop** 生效。

### 步骤 3：起 Neo4j（只需这一个容器）

```bash
docker-compose up -d neo4j
```

验证：浏览器开 http://localhost:7474 ，账号 `neo4j` / 密码 `kmatch2026` 能登录即成功。

### 步骤 4：配 `.env`

```bash
cp .env.example .env
```

精简模式下 `.env` 关键项：
- `NEO4J_PASSWORD=kmatch2026`（已默认，别改）
- `LLM_API_KEY=sk-placeholder`（**故意留占位** → 触发降级，正好测 BUG-028）
- `EMBEDDING_API_KEY=`（留空 → 向量检索降级，图遍历仍可用）

> ⚠️ `.env` 不入库（已 gitignore），各人填各人的，**别提交**。

### 步骤 5：装后端依赖 + 启动后端

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 步骤 6：导入知识库（图谱查询非空的前提）

**新开一个终端**：

```bash
cd backend
python scripts/validate_data.py ../data/knowledge_base/
python scripts/import_knowledge_base.py ../data/knowledge_base/
```

> 不导入 → `/api/graph/*` 全是空，`assess` 也组不出路径。**必做**。

### 步骤 7：启动前端（仅 B）

```bash
cd frontend
npm install
npm run dev
```

访问 http://localhost:5173 ，Vite proxy 已把 `/api/*` → 8000，直连后端。

### 步骤 8：验证环境就绪

浏览器或 curl 访问健康检查：

```bash
curl http://localhost:8000/api/health
```

期望返回（精简模式）：
```json
{"status": "ok", "neo4j": "ok", "llm_api": "sk-placeholder", ...}
```

- `neo4j: ok` → Neo4j 通了 ✅
- `llm_api` 显示占位 → LLM 降级中（预期）

---

## 二、全栈模式（冲刺联调期）

在精简模式基础上，**只改 `.env`**：

```bash
# .env 填真实 Key
LLM_API_KEY=sk-你的真实DeepSeek密钥
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-v4-pro

EMBEDDING_API_KEY=sk-你的真实千问密钥
EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_MODEL=text-embedding-v2
EMBEDDING_DIMENSIONS=1536
```

> ⚠️ DeepSeek **不提供 embedding API**，embedding 必须用千问（DashScope）。两个 Key 是分开的。

改完重启后端（`uvicorn --reload` 会自动重载），再验证：

```bash
curl http://localhost:8000/api/health
```

期望 `llm_api` 显示真实 Key 前缀、不再降级。然后 `assess`(demo) 能跑出真实画像 + 学习路径 + 生成内容。

---

## 三、C 端数据阶段（最轻量）

C 写知识库/画像/prompts 时**不需要 Neo4j**，只要 Python 校验脚本：

```bash
git pull
cd backend
pip install -r requirements.txt

# 校验数据 Schema（不连 Neo4j）
python scripts/validate_data.py ../data/knowledge_base/
```

校验通过即可提交数据。**只有想看数据导入图谱后的效果**（路径组装、向量检索）时，才按上面「精简模式」起 Neo4j + 导入。

---

## 四、真实环境必跑的降级测试（mock 测不出）

精简/全栈模式起好后，**专门造一次降级**验证前端处理（B 重点）：

| 造降级的方式 | 操作 | 期望响应 | 验证点 |
|:---|:---|:---|:---|
| Neo4j 挂了 | `docker-compose stop neo4j` | assess → 503 `知识图谱引擎未就绪` | 拦截器 toast |
| LLM 未配 | `.env` 留 `sk-placeholder` | assess → 200 + `profile={}` | BUG-028 修复后显示 retry_hint |
| Embedding 未配 | `.env` 留空 `EMBEDDING_API_KEY` | `/api/graph/search` → 503 | 图遍历查询仍可用 |
| session 失效 | 答完 interactive 后**重启后端**，再 submit | submit → 404 session 不存在 | 拦截器 404 分支 |

> 这四组是 mock 永远测不出来的，**真实联调必跑**。前端正确处理降级是验收硬指标。

---

## 五、常见问题

| 现象 | 原因 / 解决 |
|:---|:---|
| `docker-compose up` 拉镜像超时 | 没配镜像源。回到步骤 2。 |
| Neo4j 登录密码不对 | 密码固定 `kmatch2026`，别改 `.env` 里的 `NEO4J_PASSWORD`。 |
| `/api/health` 返回 `neo4j: error` | Neo4j 容器没起来或没 healthy。`docker-compose ps` 看状态，等 healthcheck 通过（约 30s）。 |
| 图谱查询全空 | 没导入知识库。回到步骤 6。 |
| assess 卡很久才返回 | LLM 真实调用 15~30s 属正常；前端 timeout 60s（`api/index.js`）。频繁超时找 A。 |
| interactive submit 报 404 | 后端重启过，内存 session 丢了。重新 assess(interactive) 拿新 session_id。开发期正常。 |
| `pip install` 慢/失败 | 国内换源：`pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt` |
| `npm install` 慢 | 换淘宝源：`npm config set registry https://registry.npmmirror.com` |

---

## 六、各端起环境的最小集合速查

| 端 | 最少要起 | 何时升全栈 |
|:---|:---|:---|
| **B** | Neo4j(docker) + 后端(uvicorn) + 前端(npm) | 冲刺期加 LLM Key |
| **C** | Python + requirements.txt（跑脚本） | 看图谱效果时加 Neo4j |
| **A** | 全栈（一直在跑） | — |

> 三人不必都全栈。B/C 按需起，省钱省时，冲刺期再统一全栈联调。
