# KMatch·知链 — BUG 决策日志

> 记录开发过程中遇到的所有技术问题、根因分析和解决决策。
> 每个问题标注影响范围、决策人和解决状态。
>
> **⚠️ 历史存档**（2026-06-23 起）：新 BUG 一律开 GitHub Issue（见 [docs/agents/issue-tracker.md](../agents/issue-tracker.md)），本文件不再新增。下方为既有 76 条记录。新发现的 F1–F15 脆弱点与解耦 candidates 已全部转 Issue，见 [重构方案_解耦.md](../架构与设计/重构方案_解耦.md)。

---

## BUG-001: 知识节点格式规范不一致

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-16 |
| **发现阶段** | 前置数据准备 |
| **严重程度** | 🔴 高 — 若不解决，所有数据需返工 |
| **影响范围** | schema.json、validate_data.py、import_knowledge_base.py、所有已编写节点 |
| **决策人** | A（后端负责人） |

### 问题描述

`项目开发计划书.md` 中隐含的节点格式与 `前置数据准备指南.md` 中明确定义的格式不一致：

| 字段 | 计划书 Schema v1 | 指南 Schema v2 | 迁移状态 |
| :--- | :--- | :--- | :---: |
| ID | `node_id` | `id` | ✅ |
| 名称 | `title` | `name` | ✅ |
| 概要 | `content.summary` (嵌套) | `summary` (顶层) | ✅ |
| 要点 | `content.key_points` (嵌套) | `key_points` (顶层) | ✅ |
| 练习题 | 无 | `practice_questions` (顶层数组) | ✅ |
| 常见误区 | `content.common_mistakes` | 不强制 | ✅ |
| 学习时长 | `learning_time` (字符串) | `estimated_minutes` (整数) | ✅ |

### 根因

- 计划书由多人在不同阶段编写，数据模型迭代后未全局同步
- 指南是后来由 C 专门编写的详细规范，比计划书中的表格式定义更落地

### 决策

**采用指南 v2 格式作为唯一标准。** 理由：
1. 指南由数据负责人 C 统筹，字段定义更贴近实际导入需求
2. `practice_questions` 是赛题刚性要求（需交付分阶测试题），v1 缺失此字段
3. 顶层字段结构更易于 Neo4j Cypher 查询（无需嵌套解析）
4. 指南中已明确列出全部 92 个节点的 ID/名称/难度/前置依赖

### 执行

1. 重写 `schema.json` — 使用 v2 字段 ✅
2. 删除旧模板 PY-001.json / PY-012.json — 格式已过期 ✅
3. 重写 `validate_data.py` v2 — 校验 id/name/summary/practice_questions/estimated_minutes ✅
4. 重写 `import_knowledge_base.py` v2 — Neo4j 导入适配 v2 字段 ✅
5. 按 v2 格式编写全部 92 个节点（含 estimated_minutes 整数字段） ✅

### 验证

```bash
python backend/scripts/validate_data.py data/knowledge_base/
# ✅ 92 节点，0 错误，0 引用错误，0 循环依赖
```

所有 92 个节点均包含 `estimated_minutes`（整数），最小值 15，最大值 45，符合 schema.json 定义的 5–240 范围。

---

## BUG-002: Docker Hub 拉取超时

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-16 |
| **发现阶段** | 环境搭建 |
| **严重程度** | 🟡 中 — 阻塞环境启动，但有替代方案 |
| **影响范围** | Neo4j 服务启动 |
| **决策人** | A |

### 问题描述

```bash
docker pull neo4j:5-community
# Error response from daemon: Get "https://registry-1.docker.io/v2/":
# net/http: request canceled while waiting for connection
# (Client.Timeout exceeded while awaiting headers)
```

Docker Hub 默认 registry 在国内网络环境下不稳定，首次拉取容易超时。

### 根因

- 国内网络对 `registry-1.docker.io` 的访问存在间歇性阻断
- 未配置 Docker 镜像加速器

### 决策

**直接重试而非切换镜像源。** 理由：
1. 该网络问题是间歇性的，并非永久不可达
2. 镜像源（DaoCloud/阿里云）的同步延迟可能导致下载到旧版本
3. 第二次重试成功拉取（耗时约 30 秒）

### 执行

直接重新执行 `docker pull neo4j:5-community`，拉取成功。

### 后续建议

长期方案：在 Docker Desktop Settings → Docker Engine 中配置镜像加速器：

```json
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://dockerhub.icu"
  ]
}
```

---

## BUG-003: FastAPI 启动时模块找不到

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-16 |
| **发现阶段** | 后端启动 |
| **严重程度** | 🟢 低 — 路径问题，即刻修复 |
| **影响范围** | FastAPI 启动命令 |
| **决策人** | A |

### 问题描述

```bash
cd d:/Origin_jerry/KMatch
uvicorn app.main:app --host 0.0.0.0 --port 8000
# ModuleNotFoundError: No module named 'app'
```

### 根因

`app` 包在 `backend/` 目录下，但命令在项目根目录执行。Python 在根目录中找不到 `app` 模块。

### 决策

**从 backend/ 目录启动。** 同时在 `backend/app/main.py` 中已预留 `sys.path.insert` 逻辑（第 9-10 行），脚本启动时可自动添加路径。

### 执行

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
# ✅ Application startup complete
```

### 后续改进

- `docker-compose.yml` 中已正确配置工作目录为 `/app`（即 backend/）
- 可在项目根目录添加 `Makefile` 或 `.vscode/tasks.json` 统一启动命令

---

## BUG-004: docker-compose.yml version 属性警告

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-16 |
| **发现阶段** | Docker Compose 启动 |
| **严重程度** | 🟢 低 — 仅为警告，不影响运行 |
| **影响范围** | docker-compose.yml |
| **决策人** | A |

### 问题描述

```
WARNING: "version" attribute is obsolete, it will be ignored
```

Docker Compose V2（docker compose，无连字符）不再识别 `version` 字段。

### 根因

`docker-compose.yml` 顶部写了 `version: "3.8"`，这是 Compose V1 的遗留语法。环境中运行的 `docker compose` 是 V2 版本。

### 决策

**移除 version 字段。** 这是 Docker 官方推荐做法，且 V2 已全面替代 V1。

### 执行

已编辑 `docker-compose.yml` 删除 `version: "3.8"` 行（2026-06-16）。

---

## BUG-005: npm 依赖安全漏洞

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-16 |
| **发现阶段** | 前端环境搭建 |
| **严重程度** | 🟢 低 — 开发环境，不暴露公网 |
| **影响范围** | frontend/node_modules |
| **决策人** | B（前端负责人） |

### 问题描述

```bash
npm install
# 2 high severity vulnerabilities
# eslint 8.x deprecated
```

### 根因

`package.json` 中 `eslint` 锁定在 `^8.57.0`，该版本已停止维护。

### 决策

**当前不处理。** 理由：
1. ESLint 仅在开发时使用，不进入生产构建产物
2. 两个高危漏洞均为开发依赖中的间接依赖，实际风险低
3. 升级到 ESLint 9.x 需要迁移配置格式（扁平化配置），投入/产出比低

### 后续

第 5-6 周前端功能稳定后，统一升级 ESLint 9.x。

---

## BUG-006: 零基础画像 JSON 序列化兼容

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-16 |
| **发现阶段** | 数据准备 |
| **严重程度** | 🟢 低 — 不影响当前功能 |
| **影响范围** | 后端读取用户画像 |
| **决策人** | C（数据负责人） |

### 问题描述

`profile_beginner.json` 中 `known_topics` 为空数组 `[]`。后端学情检测 Agent 需处理空画像的边界情况：当没有已知节点时，图谱组装逻辑应从最基础节点（difficulty=1, prerequisites=[]）开始推荐。

### 根因

这是预期行为（零基础 = 无已知节点），但后端图谱组装逻辑需要显式处理此边界情况。

### 决策

**在第 2 周实现学情检测 Agent 时添加空画像处理逻辑：**
1. `known_topics` 为空 → 从所有 `prerequisites: []` 且 `difficulty: 1` 的节点开始推荐
2. `target_direction` 未指定 → 默认覆盖 difficulty 1-2 的前 10 个互连节点
3. `weak_topics` 为空 → 跳过语义向量检索阶段，纯图遍历推荐

### 执行

待第 2 周编码实现。`engine.py` 中 `assemble_learning_path()` 已内置零基础处理（第 350-352 行）。

---

## BUG-007: Neo4j 5.x 不允许参数化变长路径

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-16 |
| **发现阶段** | 核心开发 |
| **严重程度** | 🟡 中 — 阻塞图遍历查询 |
| **影响范围** | `engine.py` 中 `get_reachable()` 和 `assemble_learning_path()` |
| **决策人** | A |

### 问题描述

```python
# 这样写会在 Neo4j 5.x 中报 CypherSyntaxError
s.run("MATCH (start)-[:REQUIRES*1..$depth]->(n) ...", depth=3)
# Parameter maps cannot be used in `MATCH` patterns
```

Neo4j 5.x 不允许在 `MATCH` 的变长路径范围中使用参数化变量。

### 根因

Neo4j 5.x 的 Bolt 协议对变长路径 `*min..max` 的语法限制，范围值必须是 Cypher 字面量，不能是参数。

### 决策

**使用 Python f-string 拼入 depth 值。** 理由：`max_depth` 来自内部代码常量（1-4），不接收用户输入，不存在注入风险。对 `assemble_learning_path` 中的硬编码 `*1..4` 保持不变。

### 执行

```python
# 修复前
s.run("MATCH ... -[:REQUIRES*1..$depth]-> ...", depth=max_depth)

# 修复后
s.run(f"MATCH ... -[:REQUIRES*1..{max_depth}]-> ...")
```

### 验证

`get_reachable()` 和 `assemble_learning_path()` 正常返回结果。

---

## BUG-008: 导入脚本缺少 sys.path 导致 app 模块找不到

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-16 |
| **发现阶段** | 核心开发 |
| **严重程度** | 🟢 低 — 一行修复 |
| **影响范围** | `import_knowledge_base.py` 向量步骤 |
| **决策人** | A |

### 问题描述

```
⚠️  缺少依赖，跳过向量步骤: No module named 'app'
```

导入脚本直接运行时，Python 找不到 `app.graph.engine` 模块。

### 根因

`import_knowledge_base.py` 位于 `backend/scripts/`，运行时工作目录在 `backend/`，但脚本没有将 `backend/` 加入 `sys.path`。`main.py` 已有这条逻辑（第9行），导入脚本遗漏了。

### 决策

**在脚本顶部添加 `sys.path.insert`。** 与 `main.py` 保持一致的做法。

### 执行

```python
sys.path.insert(0, str(Path(__file__).parent.parent))
```

### 验证

重新执行导入脚本，向量索引创建和 embedding 生成均成功。

---

## BUG-009: 图遍历方向取反——REQUIRES 边方向误用

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-16 |
| **发现阶段** | 核心开发 |
| **严重程度** | 🔴 高 — 学习路径和可达节点查询结果完全错误 |
| **影响范围** | `engine.py` 中 `get_reachable()` 和 `assemble_learning_path()` |
| **决策人** | A |

### 问题描述

`get_reachable()` 查询零基础用户（`known_ids=['PY-001']`）时返回空集。根因是 Cypher 遍历方向反了。

图谱中 `REQUIRES` 边的方向是 `(child)-[:REQUIRES]->(parent)`——从较难知识点指向前置依赖。这意味着：
- 顺着边方向 = 找前置（已知 A → A 依赖于什么）
- 逆着边方向 = 找后继（已知 A → 什么依赖于 A，即接下来可学什么）

原代码使用 `(start)-[:REQUIRES*1..N]->(n)`，是顺着边找前置。学习路径组装需要用 `(start)<-[:REQUIRES*1..N]-(n)` 找后继。

### 根因

边方向语义理解错误。`REQUIRES` = "依赖于"，A REQUIRES B 表示 A 依赖 B，即 B 是 A 的前置。这个方向在编写节点数据时是正确的，但在图遍历查询中用反了。

### 决策

**将 `get_reachable` 和 `assemble_learning_path` 中的遍历方向改为反向（`<-`）。**

### 执行

```cypher
-- 修复前（错误：找前置）
MATCH (start)-[:REQUIRES*1..4]->(n)

-- 修复后（正确：找后继/依赖者）
MATCH (start)<-[:REQUIRES*1..4]-(n)
```

### 验证

修复后 `assemble_learning_path(known_ids=['PY-001'])` 正确返回依赖于 PY-001 的后续知识点（PY-002 基本IO、PY-003 字符串 等），而非空集。

---

## BUG-010: 用户画像 Schema 与文档不一致

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-17 |
| **发现阶段** | 前置数据准备 |
| **严重程度** | 🔴 高 — 后端 Agent 运行时将读取到错误字段名 |
| **影响范围** | 4个画像JSON、3个Agent Prompt、前置数据准备指南、validate_data.py |
| **决策人** | A |

### 问题描述

`前置数据准备指南.md` 第2.2节中定义的画像格式与实际磁盘文件使用完全不同的字段名和数据结构：

| 维度 | 指南格式 | 磁盘格式 | 后果 |
|:---|:---|:---|:---|
| ID | `user_id` | `profile_id` | Agent 读不到画像ID |
| 理论水平 | `theoretical_level` | `theory_level` | 学情检测输出字段名不匹配 |
| 已知节点 | `known_node_ids` (string[]) | `known_topics` (object[] 含 mastery) | **数据类型完全不同** |
| 薄弱节点 | `weakness_areas` (string[]) | `weak_topics` (object[] 含 error_patterns) | **数据类型完全不同** |

此外 `validate_data.py` 完全没有画像校验逻辑，导致此不一致无法被自动检测。

### 根因

与 BUG-001 同根因——指南由 C 编写规范（理论设计），实际 JSON 文件由 A 代理制作时自然演化出了更好的结构（含 mastery 分数和 error_patterns），但两处未同步。磁盘格式功能更强：`known_topics` 带 mastery 分数可实现更精准的难度匹配，`weak_topics` 带 error_patterns 可让内容生成 Agent 针对性讲解。

### 决策

**以磁盘格式为基础，吸收指南优点，统一为 v3。** 理由：
1. 磁盘格式已被 3 个 Agent Prompt 和 LangGraph Demo 引用，改动面更小
2. `known_topics` 的 mastery 分数是 personalized learning 的核心需求
3. `weak_topics` 的 error_patterns 让生成 Agent 能做针对性教学
4. 补回指南中缺失的 `name`、`preferred_pace`、`weakness_areas`（自然语言描述）

### 执行

1. 4 个画像 JSON 重写为 v3 ✅
2. 3 个 Agent Prompt 输出格式更新 ✅
3. `前置数据准备指南.md` 全部章节对齐 v3 ✅
4. 新建 `profile_schema.json` v3 规范 ✅
5. `validate_data.py` 新增阶段2画像校验 ✅
6. 本 BUG 记录 ✅

### 验证

```bash
python backend/scripts/validate_data.py data/knowledge_base/ data/user_profiles/
# ✅ 全部通过！知识节点 92 + 画像 4，0 错误
```

---

## BUG-011: 健康检查每次创建新 Neo4j 连接

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-17 |
| **发现阶段** | 环境搭建 |
| **严重程度** | 🟢 低 — 当前调用量极低，无实际性能影响 |
| **影响范围** | `main.py` `/api/health` 端点 |
| **决策人** | A |

### 问题描述

`main.py` 第 56-63 行，每次 `GET /api/health` 请求都执行 `GraphDatabase.driver()` → `verify_connectivity()` → `driver.close()`，创建后立即销毁。虽然 `close()` 保证了不泄漏，但生产中高并发时会浪费连接资源。

### 根因

项目处于骨架阶段，只有一个 health check 路由用到 Neo4j。没有引入 FastAPI lifespan 或依赖注入机制来复用连接。

### 决策

**推迟到第 2 周修复。** 理由：
1. 当前开发环境日调用量 <10 次，实际影响为零
2. 正确修法是引入 FastAPI lifespan + `KnowledgeGraph` 单例，而非在 health check 里打补丁
3. 第 2 周 A 实现 Agent 节点时会自然需要全局图谱实例，在那时一步到位

### 执行

待第 2 周实现第一个真正的 API 路由时：
1. 在 `main.py` 中添加 `@app.on_event("startup")` 或 lifespan context
2. 创建全局 `KnowledgeGraph` 实例供所有路由共享
3. 健康检查复用该实例

---

## BUG-012: docker-compose 漏配 Embedding 环境变量 + 默认模型名不一致

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-17 |
| **发现阶段** | 第一周审查 → 联调前 |
| **严重程度** | 🟡 中 — 阻塞 B/C 一键 Docker 启动的语义检索能力，且无报错难排查 |
| **影响范围** | docker-compose.yml、.env.example、config.py、week1_demos |
| **决策人** | A |

### 问题描述

第一周审查发现三个会拖累 B/C 联调的配置/字段不一致问题：

1. **docker-compose.yml 漏配 Embedding 环境变量**：backend service 只传了 `LLM_API_KEY/BASE_URL/MODEL`，没有 `EMBEDDING_*`。B/C 用 `docker-compose up` 一键启动时，`create_embedding_client()` 会 fallback 到 DeepSeek 的 key/URL，而 DeepSeek 不提供 embedding API → 返回 None → 语义检索静默降级为纯图模式，无报错。
2. **默认模型名不一致**：`.env.example` 和 `config.py` 默认 `EMBEDDING_MODEL=text-embedding-3-small`，但实际 `.env` 和 devlog 7.2 用的是千问 `text-embedding-v2`。C 复制 .env.example 后若不改，调千问却用 OpenAI 模型名 → 报错。
3. **week1_demos 用 v1 字段名**：两个 demo 的模拟节点用 `title`/`node_id`（v1），但正式 schema v3 是 `name`/`id`（BUG-001 已统一）。B/C 若照 demo 字段名写对接代码会踩空。

### 根因

- 第1周引擎开发追加时，A 本地 `.env` 配对了千问，本地跑没问题，但 Docker 编排和共享模板未同步追加 `EMBEDDING_*`
- `text-embedding-3-small` 是早期从 OpenAI 默认值沿用，未随千问方案落地而更新
- demo 脚本早于 schema v2/v3 统一，字段名停留在 v1

### 决策

**全部对齐千问 v2 + v3 字段。** 理由：

1. DeepSeek 不提供 embedding，千问 v2 是已验证的方案，应作为默认值降低 B/C 配置成本
2. demo 字段名应与正式 schema 一致，避免误导

### 执行

1. `docker-compose.yml` backend service 补 5 个 `EMBEDDING_*` 环境变量，默认对接千问 DashScope ✅
2. `config.py` 默认 `EMBEDDING_MODEL` → `text-embedding-v2` ✅
3. `.env.example` 默认 `EMBEDDING_MODEL` → `text-embedding-v2`，`EMBEDDING_BASE_URL` 填上千问 ✅
4. `week1_demos/langgraph_demo/main.py` 模拟节点 `title`→`name` ✅
5. `week1_demos/neo4j_demo/main.py` 测试节点 `node_id`→`id`、`title`→`name` ✅

### 验证

```bash
# 1. demo 字段无 v1 残留
grep -rn "node_id\|\.title" week1_demos/   # No matches found
# 2. langgraph demo 实跑通过（字段改名后逻辑未破坏）
python week1_demos/langgraph_demo/main.py  # ✅ 2节点+条件分支+3轮循环
# 3. config 默认值正确
python -c "from app.config import settings; print(settings.EMBEDDING_MODEL)"
# → text-embedding-v2
```

---

## 决策汇总

| 编号 | 问题 | 决策 | 影响 |
|:---|:---|:---|:---|
| BUG-001 | 格式不一致 | 统一采用指南 v2 格式 | 全局 |
| BUG-002 | Docker Hub 超时 | 重试（非切换镜像） | Neo4j |
| BUG-003 | 模块找不到 | 从 backend/ 目录启动 | FastAPI |
| BUG-004 | version 警告 | 移除 version 字段 | docker-compose |
| BUG-005 | npm 漏洞 | 暂不处理，第5周升级 | 前端 |
| BUG-006 | 空画像处理 | 第2周编码时处理边界 | 后端 |
| BUG-007 | 参数化变长路径 | f-string 拼入内部整数 | 图谱引擎 |
| BUG-008 | 脚本 sys.path | 添加 Path 注入 | 导入脚本 |
| BUG-009 | 图遍历方向反 | 反向箭头 `<-REQUIRES-` | 图谱引擎 |
| BUG-010 | 画像Schema不一致 | 统一为v3（磁盘格式+指南优点） | 全局 |
| BUG-011 | 健康检查连接反复创建 | ✅ 已解决（lifespan 全局 KG 单例 + OpenAI 客户端 + workflow） | 后端 |
| BUG-012 | Docker漏配Embedding+默认模型名不一致+demos用v1字段 | 全部对齐千问v2+v3字段 | docker-compose/共享配置/demos |
| BUG-013 | Neo4j容器启动失败(usage report设置名5.x无效) | 删除该环境变量行 | docker-compose/Neo4j |
| BUG-014 | diagnostics 生成 profile_id 格式不符合 Schema | 放宽 Schema → hex + UUID 生成 | profile_schema/validate_data/diagnostics |
| BUG-015 | health check + API 路由反复创建连接/编译图 | lifespan 全局单例模式延伸（OpenAI客户端+workflow） | main.py/api |
| BUG-016 | reviewer prompt 审"生成内容"但代码实际审"画像" | ✅ 双模式 reviewer 已实现（画像+内容） | reviewer prompt/code |
| BUG-017 | hasResults 空画像误判进入报告模式 | 检查 Object.keys(profile).length > 0 | 前端 store |
| BUG-018 | 日志时间戳硬编码切片导致显示错位 | 正则为 `] ` 分割 | 前端 Assessment |
| BUG-019 | 未判分题目错误显示为"答错" | 三态判断（true/false/null） | 前端 AssessmentReport |
| BUG-020 | parse_llm_json 兜底 json.loads() 无异常保护 | 提取公共工具 json_utils.py，失败返回 {} | 后端 agents |
| BUG-021 | 审核阈值前后端不同步 | 后端透传 threshold，前端动态读取 | 后端+前端 |
| BUG-022 | per_node 判分结构依赖隐式顺序 | 改 question_index 显式关联 | 后端+前端 |
| BUG-023 | AssessmentReport nodeCorrect 新结构下永远满分 | filter(Boolean) → filter(g => g.correct === true) | 前端 |
| BUG-024 | CLAUDE.md Embedding 模型名错误 | text-embedding-3-small → text-embedding-v2 | 文档 |
| BUG-025 | recommended_path 字段三方错配 | 统一为 object 结构，废弃 string 字段 | diagnostics+prompt+schema |
| BUG-026 | _grade question_index 仍依赖 LLM grades 隐式顺序 | LLM 显式回写 question_index，后端边界校验 | diagnostics |
| BUG-027 | Assessment.vue el-alert 错误原因被插槽覆盖不显示 | 错误文案放插槽，按钮置其下 | 前端 |
| BUG-028 | 后端降级空画像时前端静默失败无反馈 | 空画像检测 + retry_hint 写 error | 前端 store |
| BUG-029 | AssessmentReport 未作答题目渲染空白 | `?? ''` → `?? null` 保留 null 语义 | 前端 |
| BUG-030 | B 端 store 未消费 knowledge_graph 字段 | 新增 knowledgeGraph/generatedContent ref | 前端 store |
| BUG-031 | 工作流无限循环（画像通过+内容空资源） | content_phase_entered 标志位 + over_limit 守卫 | orchestrator |
| BUG-032 | _grade 判分两个静默正确性隐患 | bool("false")→True + seen_q_idx 去重 | diagnostics |
| BUG-033 | interactive 出题下发正确答案 + 畸形 known_topics | 剥离 answer + isinstance 守卫 | api/diagnostics |
| BUG-034 | recommended_path.next_nodes 推荐已掌握节点 | _suggest_next_nodes 加 known_ids 排除 | diagnostics |
| BUG-035 | theory_level 与正确率不自洽 | 保守分段映射 `_derive_theory_level` | diagnostics |
| BUG-036 | weak_topics.error_patterns 笼统/与错题不符 | 引用实际错题 + common_mistakes 回退 | diagnostics |
| BUG-037 | reviewer 内容模式漏传 profile 致 TypeError | 内容模式 llm_arg = (resources, profile) | reviewer |
| BUG-038 | 全掌握画像逻辑矛盾（起点已掌握+4周） | 改 recommended_start + estimated_weeks 逻辑 | diagnostics |
| BUG-039 | mastery 阈值与 prompt 三段制不一致 | mastery≥0.8→known（对齐 prompt 权威定义） | diagnostics+graph_controller |
| BUG-040 | reviewer 误读 last_test_score 占位字段 | 审核 prompt 补字段说明 | reviewer |
| BUG-041 | content_generator LLM 偶发返回数组致 ValueError | list→首 dict/空降级防御 | content_generator |
| BUG-042 | assemble_learning_path 只插弱项前置、漏弱项本身 | 弱项节点追加 + difficulty_cap 保护 | engine |
| BUG-043 | content_generator LLM 自填 difficulty_level | 系统强制赋值节点难度（setdefault→直接=） | content_generator |
| BUG-044 | feedback 再生路径漏修 BUG-043 | 反馈路径同步强制赋值 difficulty_level | content_generator |
| BUG-045 | useAgentStatus diagnostics+graph_controller 恒 idle | emoji 扩充 + ⚠️ 降级兜底 | 前端 AgentView |
| BUG-046 | MarkdownViewer v-html 无 XSS 过滤 | 引入 DOMPurify 消毒 | 前端 MarkdownViewer |
| BUG-047 | KEYWORD_MAP /图谱组装/ 不匹配实际日志 | → /知识图谱\|图谱组装/ | 前端 AgentView |

---

## BUG-013: Neo4j 容器启动失败 — usage report 配置项在 5.x 无效

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-17 |
| **发现阶段** | 第二周端到端验证 |
| **严重程度** | 🔴 高 — Neo4j 容器直接 crash-loop 退出，全栈无法启动 |
| **影响范围** | docker-compose.yml neo4j service |
| **决策人** | A |

### 问题描述

`docker-compose up -d neo4j` 后容器 `Exited (1)` 反复重启。日志：

```
Failed to read config: Unrecognized setting. No declared setting with name:
dbms.usage.report.enabled. Cleanup the config or disable 'server.config.strict_validation.enabled'
```

### 根因

`docker-compose.yml` 中 neo4j service 设了环境变量：

```yaml
NEO4J_dbms_usage_report_enabled: "false"
```

Neo4j 环境变量映射规则为 `NEO4J_` 前缀 + 下划线转点，故此行翻译成配置项 `dbms.usage.report.enabled`。但 **Neo4j 5.x 已移除/改名该配置项**，strict validation 默认开启时直接拒绝启动。第一周埋下的配置错误，当时未触发（可能用别的方式起过或未真正走 Docker 路径）。

### 决策

**直接删除该环境变量行。** 理由：
1. 遥测上报关闭与否对开发/演示零影响
2. 5.x 没有干净的等价环境变量名，保留只会持续踩 strict validation 的坑
3. 删除最简单稳定

### 执行

删除 `docker-compose.yml` neo4j service 的 `NEO4J_dbms_usage_report_enabled: "false"` 行 ✅

### 验证

```bash
docker-compose up -d neo4j
# 容器进入 healthy，bolt://localhost:7687 可连通
```

---

## BUG-014: diagnostics 生成的 profile_id 格式不符合 Schema 规范

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-17 |
| **发现阶段** | 核心开发 |
| **严重程度** | 🟡 中 — 校验不通过，并发场景可能重复 |
| **影响范围** | profile_schema.json、validate_data.py、diagnostics.py |
| **决策人** | A |

### 问题描述

`diagnostics.py` 的 `_build_profile` 生成 `profile_id` 为 `UP-ASM-{HHMMSS}`（如 `UP-ASM-143025`），两个问题：

1. **格式不匹配 Schema**：HHMMSS 是 6 位数字，`profile_schema.json` 的 pattern 为 `^UP-[A-Z]{3}-\\d{3}$`，仅允许 3 位数字，校验会报错
2. **并发冲突**：同秒内多次调用生成相同 ID，三人协作或多轮测评时会覆盖

### 根因

1. Schema 最初设计的 `\d{3}` 仅支持 1000 个画像，低估了实际使用量
2. 时间戳用作唯一标识，并发安全性不足

### 决策

**两步修复：放宽 Schema + 改用 UUID。** 理由：

1. Schema `\d{3}` → `[0-9a-f]{3,8}`：支持 hex 字符（如 `a1b2c3`），容量从 1000 扩展到百万级，兼容存量画像的纯数字格式
2. `profile_id` 来源标识从 `ASM`（含义模糊）改为 `DIA`（DIagnostics Agent），语义清晰
3. 生成规则：`UP-DIA-{uuid4().hex[:6]}`，碰撞概率 ~1/1600万，三人并发安全

### 执行

1. `profile_schema.json` pattern → `^UP-[A-Z]{3}-[0-9a-f]{3,8}$` ✅
2. `validate_data.py` 同步正则 ✅
3. `diagnostics.py` `import uuid` + 生成逻辑改为 `f"UP-DIA-{uuid.uuid4().hex[:6]}"` ✅

### 验证

```bash
python backend/scripts/validate_data.py data/knowledge_base/ data/user_profiles/
# ✅ 全部通过！知识节点 92 + 画像 4，0 错误

cd backend && python -m pytest tests/ -v
# 12 passed
```

---

## BUG-015: health check 每次新建 LLM 连接 + API 路由重复编译 LangGraph 图

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-17 |
| **发现阶段** | 核心开发 |
| **严重程度** | 🟡 中 — 低调用量无实际性能影响，但第3-4周加节点后成为瓶颈 |
| **影响范围** | main.py、api/diagnostics.py |
| **决策人** | A |

### 问题描述

1. **health check LLM 连接**：`GET /api/health` 第 98-99 行每次请求都 `OpenAI(...)` 创建新客户端 → `models.list()` → 丢弃。与 BUG-011（Neo4j 连接）完全同类问题。
2. **workflow 重复编译**：`POST /api/diagnostics/assess` 每次调用都 `build_workflow(kg)` → `StateGraph.compile(checkpointer=MemorySaver())`，导致每次请求的 checkpoint 状态不互通，后续跨请求查询历史状态时会失败。

### 根因

BUG-011 修复时仅扩展了 lifespan 管理 KG 单例，但忽略了同类模式同样适用于 OpenAI 客户端和 LangGraph 编译结果。

### 决策

**将 lifespan 全局单例模式系统化延伸。** 理由：
1. 三者共享同一模式：启动时创建一次 → 存 `app.state` → 所有路由复用
2. workflow 预编译后 `MemorySaver` 跨请求共享，第 3 周 `graph_controller` 接入后可查询历史 checkpoint
3. 第 3-4 周加节点时无需改 API 层

### 执行

1. `main.py` lifespan：新增 OpenAI 客户端单例 `app.state.openai_client` ✅
2. `main.py` lifespan：新增 workflow 预编译 `app.state.workflow` ✅
3. `health_check`：复用 `app.state.openai_client` ✅
4. `api/diagnostics.py` `assess`：复用 `app.state.workflow`，移除 `build_workflow(kg)` ✅
5. `main.py` 清理重复注释块 ✅

### 验证

```bash
python -c "from app.main import app"  # ✅ 模块加载成功
cd backend && python -m pytest tests/ -v  # 12 passed
```

---

## BUG-016: reviewer prompt 审"生成内容"但代码实际审"画像"

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-17 |
| **发现阶段** | 核心开发 |
| **严重程度** | 🟢 低 — 设计阶段已知时间差，不影响当前功能 |
| **影响范围** | reviewer prompt 注释 / reviewer.py |
| **决策人** | A |
| **状态** | ✅ 已解决（2026-06-18 第4周 content_generator 接入，reviewer 双模式审核） |

### 问题描述

`data/prompts/05_content_reviewer_agent.txt` 的审核对象是"领域知识生成Agent产出的学习资源"，但当前代码 `reviewer.py` 实际审核的是"学情检测 Agent 产出的用户画像"。两者审核对象不同：prompt 设计审内容，代码实现审画像。

### 根因

设计阶段时间差——领域知识生成 Agent 第4周才实现。第2周只有 diagnostics + reviewer 两个节点串联，审核对象暂时复用为画像合理性审核（画像 node_id 真实性 / known-weak 交叉 / theory_level 与答题自洽）。第4周生成 Agent 就位后切换审核对象，reviewer 节点的硬规则+LLM结合框架可复用。

### 决策

**已按双模式 reviewer 解决。**

理由：

1. 画像审核和内容审核共用同一四维加权框架，但硬规则与 LLM prompt 分开实现
2. state 无 `generated_content.resources` 时 reviewer 审画像；有资源时审生成内容
3. orchestrator 第4周工作流中 content_generator 之后再次进入 reviewer，自动切到内容模式

### 执行

- ✅ `content_generator.py` 已实现三类资源生成（lecture/practice_guide/test）+ source_nodes 溯源
- ✅ `reviewer.py` 已实现双模式：画像模式 + 内容模式（_hard_check_content_sources / _llm_review_content）
- ✅ `orchestrator.py` 已接入生成→审核→打回循环（内容不通过打回 content_generator）
- ✅ 单测覆盖 content_generator、reviewer 内容硬规则、W4 orchestrator 全流程

---

## BUG-017: hasResults 空画像误判进入报告模式

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-17 |
| **发现阶段** | 核心开发（前端第2周） |
| **严重程度** | 🟡 中 — 后端 LLM 降级时前端展示异常 |
| **影响范围** | `frontend/src/stores/assessment.js` — `hasResults` 计算属性 |
| **决策人** | B（前端负责人） |

### 问题描述

```js
const hasResults = computed(() => !!profile.value)
```

后端在 LLM 未配置时返回 `user_profile: {}`（空对象）。`!!{}` 为 `true`，页面切换至"报告模式"但所有区域显示空数据（无雷达图、无知节点、无审核报告），用户体验差且无提示。

### 根因

`!!` 不能区分空对象与有内容对象。`diagnostics_node` 在 LLM 降级时返回 `{user_profile: {}}` 作为安全值，但前端按 truthy 判断进入了报告展示模式。

### 决策

**改为检查 `Object.keys(profile).length > 0`。** 理由：
1. 空对象 `{}` → `hasResults = false` → 停留在输入表单，不会展示空报告
2. 后端只要产出了任何画像字段（哪怕只有一个 `profile_id`），就进入报告模式
3. 不依赖后端特别标记"降级状态"，前端自愈

### 执行

- `stores/assessment.js:56`: `hasResults` 增加空对象检查 ✅

### 验证

- 编译通过（`npm run build`）
- 场景1: `profile = {}` → `hasResults = false` → 表单页
- 场景2: `profile = {profile_id: "UP-DIA-a1b2c3", ...}` → `hasResults = true` → 报告页

---

## BUG-018: 日志时间戳硬编码切片导致显示错位

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-17 |
| **发现阶段** | 核心开发（前端第2周） |
| **严重程度** | 🟢 低 — 仅影响日志时间线显示美观度 |
| **影响范围** | `frontend/src/views/Assessment.vue` — Agent 执行日志区域 |
| **决策人** | B（前端负责人） |

### 问题描述

```html
:timestamp="entry.slice(0, 25)"
{{ entry.slice(26) }}
```

后端日志格式为 `[2026-07-01T12:00:00.123456] 🔧 消息`，ISO 时间戳部分含微秒，实际长度约 28 字符。硬编码 `slice(0, 25)` 会切进 `]` 内部（显示为 `2026-07-01T12:00:00.12345`），`slice(26)` 从 `]` 开始截消息（前面多 `] `，显示为 `]  🔧 消息`）。

### 根因

`datetime.utcnow().isoformat()` 输出长度不固定（含可变微秒位数），模板中用了固定切片偏移量。

### 决策

**用正则 `] ` 分割。** `parseLogTimestamp` 匹配 `[...]` 内容，`parseLogMessage` 取 `] ` 之后的部分。

### 执行

- `Assessment.vue`: 新增 `parseLogTimestamp()` / `parseLogMessage()` 辅助函数，模板中替换硬编码切片 ✅

### 验证

- 编译通过
- `[2026-07-01T12:00:00.123456] 🔧 学情检测: 开始` → timestamp=`2026-07-01T12:00:00.123456`，message=`🔧 学情检测: 开始`

---

## BUG-019: 未判分题目错误显示为"答错"

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-17 |
| **发现阶段** | 核心开发（前端第2周） |
| **严重程度** | 🟡 中 — 误报答题结果，误导用户 |
| **影响范围** | `frontend/src/components/AssessmentReport.vue` — 题目明细折叠列表 |
| **决策人** | B（前端负责人） |

### 问题描述

```html
<el-tag :type="q.grade?.correct ? 'success' : 'danger'">
  {{ q.grade?.correct ? '✓' : '✗' }}
</el-tag>
```

后端 `per_node` 判分以 `node_id` 为 key，前端按题目在数组中的位置索引匹配。当某题 `node_id` 不在 `per_node` 中（如 LLM 出题时引用了非候选节点的 `node_id`），`correct` 为 `null`。模板中 `null` 走 falsy 分支显示为 `✗` + 红色 danger 标签，用户看到"答错"实际是"未判到"。

### 根因

- 判分匹配逻辑有偏差时 `correct` 为 `null`，JS 三元表达式将 `null` 与 `false` 等同处理
- 模板未区分"错误"和"无评分数据"两种状态

### 决策

**三态判断：`true` → 正确(绿色) / `false` → 错误(红色) / `null` → 未评分(灰色 `?`)。**
同等对待 `null` 和 `undefined`（都是"无评分数据"）。

### 执行

- `AssessmentReport.vue`: 新增 `gradeTagType()` / `gradeLabel()` / `answerClass()`，模板替换所有 `q.grade?.correct ? ... : ...` 为三态函数 ✅
- 用户答案高亮：`null` 时不加删除线（`.ungraded` class，灰色） ✅
- 正确答案显示条件：`correct === false` 才显示（`correct === null` 时不显示"正确答案是xxx"） ✅

### 验证

- 编译通过
- `correct=true` → 绿色 `✓` / `correct=false` → 红色 `✗` + 显示正确答案 / `correct=null` → 灰色 `?` + 不显示正确答案

---

## BUG-020: parse_llm_json 兜底 json.loads() 无异常保护

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-18 |
| **发现阶段** | 代码审查（A/B 端联审） |
| **严重程度** | 🔴 高 — LLM 胡言乱语时 JSON 解析异常冒泡导致整个测评流程 500 |
| **影响范围** | `backend/app/agents/diagnostics.py` `_parse_json_response()`、`reviewer.py` `_parse_json()` |
| **决策人** | A（后端负责人） |

### 问题描述

两个 Agent 节点各自实现了几乎相同的 JSON 解析函数，兜底逻辑 `json.loads(text)` 无 try/except。若 LLM 返回完全非法文本（raw_decode 对所有起始字符都失败），`json.loads(text)` 抛出 `JSONDecodeError` 且未被捕获，异常冒泡到 workflow 层导致整个测评返回 500。

### 根因

- 两个 `_parse_json` 函数独立维护，代码重复
- `json.loads(text)` 兜底假设了 LLM 响应"至少是合法 JSON"，但 LLM 可能完全胡言乱语

### 决策

**提取公共工具 `app/utils/json_utils.py` → `parse_llm_json()`，兜底 `json.loads` 加 try/except，失败返回 `{}`。**

### 执行

- 新建 `backend/app/utils/json_utils.py` — 统一 `parse_llm_json()` ✅
- `diagnostics.py` / `reviewer.py` 删除各自 `_parse_json*`，改为 `from app.utils.json_utils import parse_llm_json` ✅
- 修复 `[` / `{` 检测顺序：按最早出现位置尝试 raw_decode，确保嵌套数组/对象正确从最外层解析 ✅
- `_hard_check_overlap` 加固：非 dict 元素安全跳过 ✅

### 验证

- 全部 47 个单测通过（含新增 30 个）
- `parse_llm_json` 覆盖 11 个场景：纯对象/数组/markdown/多对象拼接/尾部文本/嵌套/前缀文本/完全非法/空字符串

---

## BUG-021: 审核阈值前后端不同步

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-18 |
| **发现阶段** | 代码审查（A/B 端联审） |
| **严重程度** | 🟡 中 — 前端硬编码阈值与后端环境变量不一致，运维调整后用户看到的结果矛盾 |
| **影响范围** | 后端 `reviewer.py` 响应体 + 前端 `ReviewReport.vue` 显示 |
| **决策人** | A（后端）+ B（前端）联合 |

### 问题描述

后端 `config.py` 已将 `REVIEW_PASS_THRESHOLD` 环境变量化（`os.getenv("REVIEW_PASS_THRESHOLD", "0.85")`），但 `review_results` 响应中不含 `threshold` 字段。前端 `ReviewReport.vue` 硬编码 `PASS_THRESHOLD = 0.85`。若运维将阈值调为 0.80，后端判定逻辑生效但前端仍显示"阈值 85%"，用户困惑。

### 根因

- 响应模型设计时未考虑将阈值透传给前端
- 前端组件开发时直接硬编码了默认值

### 决策

**后端 `review_results` 增加 `threshold` 字段，前端从响应读取。** A 先改，B 后适配。

### 执行

- 后端 A-3: `reviewer.py` 两处返回 `review_results` 均增加 `"threshold": settings.REVIEW_PASS_THRESHOLD` ✅
- 前端 B-1: `ReviewReport.vue` 改为 `props.reviewResults?.threshold`，同步动态 `scoreColor` ✅（commit `15f5a52`，2026-06-18）

### 验证

- 后端 47 单测全通过
- 前端 30 单测全通过（含 `review-report.test.js` 阈值场景）

---

## BUG-022: per_node 判分结构依赖隐式顺序

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-18 |
| **发现阶段** | 代码审查（A/B 端联审） |
| **严重程度** | 🔴 高 — LLM 交错出题时判分可能张冠李戴 |
| **影响范围** | 后端 `diagnostics.py` `_grade()` + 前端 `AssessmentReport.vue` `questionList` |
| **决策人** | A（后端）+ B（前端）联合 |

### 问题描述

后端 `per_node` 结构为 `{node_id: [true, false, ...]}`，前端用计数器按题目在 `questions` 数组中的出现顺序依次消费判分结果。如果 LLM 出题时针对不同节点交错出题（如 PY-001→PY-003→PY-001），`nodeCounters` 的"第 N 次出现"对齐可能错位，把 PY-001 第一题的判分标到 PY-003 上。

### 根因

- 判分结果与题目的关联方式脆弱，依赖"出题顺序 = 判分顺序且同节点题目连续出现"的隐含假设
- 数据契约缺少显式的 `question_index` 关联

### 决策

**后端 `per_node` 值从 `[bool]` 改为 `[{question_index, correct}]`，前端按 `question_index` 直接索引。** A 先改数据结构，B 后适配。

### 执行

- 后端 A-4: `_grade()` 判分结果带 `question_index` + `_build_profile()` 适配新结构 ✅
- 前端 B-2: `AssessmentReport.vue` `questionList` 改为按 `question_index` 匹配 ✅（commit `15f5a52`，2026-06-18）

### 验证

- 后端 47 单测全通过（含 9 个 `_build_profile` 场景覆盖新 per_node 结构）
- 前端 30 单测全通过（`assessment-report.test.js` 覆盖新结构匹配 + 无匹配 fallback）

### 后续（已发现的链路问题）

- 见 BUG-023: 本次修复漏改 `nodeCorrect`，导致"按知识点汇总"显示错误
- 见 BUG-026: 后端 `question_index` 仍来自 grades 数组下标，治标未治本

---

## BUG-023: AssessmentReport `nodeCorrect` 在 per_node 新结构下永远满分

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-18 |
| **发现阶段** | W1-2 ABC 三端审查 |
| **严重程度** | 🔴 高 — "按知识点汇总"标签永远显示满分绿色，演示时会被发现 |
| **影响范围** | 前端 `frontend/src/components/AssessmentReport.vue` |
| **决策人** | B（前端） |

### 问题描述

BUG-022 修复中 B-2 把 `questionGrades` computed 改为按新对象结构 `[{question_index, correct}]` 索引，但**漏改了 `nodeCorrect` 函数**：

```js
function nodeCorrect(results) {
  return (results || []).filter(Boolean).length  // ❌
}
```

新结构每个 grade 是对象（无论 `correct=true` 还是 `false`，对象本身都是 truthy），`filter(Boolean)` 完全不过滤，导致每个知识点的 `<el-tag>` 永远显示 `node_id — N/N 正确` 且永远是 `success` 绿色。

`nodeTagType` 同链路依赖 `nodeCorrect`，也始终判为 `success`。

### 根因

- B-2 适配时只看了 `questionList` 单一计算属性，未全文搜索 `per_node` 的所有消费点
- B-6 vitest 单测未覆盖 `nodeCorrect` / `nodeTagType` 函数

### 决策

**改为按 `g.correct === true` 显式过滤。** 同时补 4 条回归测试覆盖：满分/全错/部分对/空数组场景。

### 执行

- `AssessmentReport.vue:113-115`: `filter(Boolean)` → `filter(g => g && g.correct === true)` ✅
- `assessment-report.test.js`: 新增 `nodeCorrect — per_node 新结构语义` describe 块（4 用例）✅

### 验证

- 30/30 vitest 用例全通过（commit `91a965e`）
- 旧实现下新增的 4 条用例会全部失败（验证回归覆盖有效）

---

## BUG-024: CLAUDE.md 中 Embedding 模型名错误

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-18 |
| **发现阶段** | W1-2 ABC 三端审查 |
| **严重程度** | 🟡 中 — 文档与代码事实不一致，误导新协作者 |
| **影响范围** | `CLAUDE.md` |
| **决策人** | B（前端，顺手修） |

### 问题描述

`CLAUDE.md:97` 写：

```
| LLM Embedding | 千问 text-embedding-3-small | 1536维 |
```

但 `text-embedding-3-small` 是 OpenAI 的模型名。千问的实际模型名是 `text-embedding-v2`（[backend/app/config.py](../../backend/app/config.py) 默认值已正确）。

BUG-012 修复时改了 `.env.example` 与 `config.py`，但漏改 `CLAUDE.md`。新协作者读项目第一文档就被误导。

### 根因

- 跨文件同步遗漏（BUG-012 的执行清单未列入 CLAUDE.md）

### 决策

**改 CLAUDE.md L97 为 `text-embedding-v2`。**

### 执行

- `CLAUDE.md:97` 已改 ✅（commit `91a965e`）

### 验证

- 与 `config.py:34` `EMBEDDING_MODEL` 默认值一致
- 与 `项目开发计划书.md:345` 一致

---

## BUG-025: `recommended_path` 字段三方错配（Schema vs diagnostics 输出 vs prompt）

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-18 |
| **发现阶段** | W1-2 ABC 三端审查 |
| **严重程度** | 🔴 高 — 数据契约不一致，前端真要画"推荐路径"会拿到 undefined |
| **影响范围** | 后端 `diagnostics.py` + `data/prompts/01,02_*.txt` + `data/user_profiles/profile_schema.json` + 前端 `stores/assessment.js` 注释 |
| **决策人** | A 主导，C 同步 prompt + Schema 校验 |
| **状态** | ✅ 已解决（2026-06-18 A 端修复；prompt + validate_data 由 A 一并同步） |

### 问题描述

字段错配矩阵：

| 位置 | 字段名 | 类型 | 状态 |
|:---|:---|:---|:---|
| `data/user_profiles/profile_schema.json:167-178` | `recommended_path` | object | ✅ 标准 |
| `data/user_profiles/profile_*.json`（3 个样本）| `recommended_path` | object | ✅ 与 schema 一致 |
| `backend/app/agents/diagnostics.py:221` 实际产出 | `recommended_start_node` | string | ❌ 字段名错、类型错 |
| `data/prompts/01_orchestrator_agent.txt:44` | `recommended_start_node` | string | ❌ |
| `data/prompts/02_diagnostics_agent.txt:58` | `recommended_start_node` | string | ❌ |
| `frontend/src/stores/assessment.js:29` JSDoc | `recommended_path` | （未消费）| 🟡 |

### 根因

- diagnostics.py 实现时未对照 profile_schema.json 与样本画像，自创了 `recommended_start_node` 字符串字段
- `validate_data.py` 的画像校验 required 列表中无 `recommended_*`，错误无法被脚本捕获
- A 越界改 prompts 时未同步发现 schema 偏差

### 决策

**方案 A（采纳）: 扩展 diagnostics 输出为 object 结构，废弃 string 字段。**

理由：现有 schema + 3 个样本画像已用 object 结构，object 表达力更强（含 next_nodes / weeks 信息），diagnostics 是新代码，应让代码迁就稳定的数据契约。

### 执行（待 A/C 认领）

- ✅ A: `diagnostics.py:_build_profile` 改输出 `recommended_path: { current_node, next_nodes, estimated_completion_weeks }`，废弃 `recommended_start_node`；新增 `_suggest_next_nodes` 纯函数从候选 nodes 顺序取后继
- ✅ A: 同步 `data/prompts/01_orchestrator_agent.txt` + `02_diagnostics_agent.txt` 的输出 schema 段（A 历史维护此二 prompt，C 未动，无冲突）
- ✅ A: `validate_data.py` 画像校验增加 `recommended_path` 结构校验 + `recommended_start_node` 废弃提示
- ✅ A: `test_diagnostics_unit.py` `_build_profile` 用例改断言新结构 + 新增 `next_nodes` 序列用例

### 验证

- `pytest tests/` 51 passed（含 4 个 `_grade` 新用例 + 1 个 `recommended_path` 序列用例）
- `validate_data.py` 校验 92 节点 + 4 画像 0 错误
- 前端无需改（store 注释已是 `recommended_path`，KnowledgeGraph 主图组件按 object 消费即可）

### 详见

[docs/legacy/三人协作时代/W1-2_ABC三端审查报告_2026-06-18.md](../legacy/三人协作时代/W1-2_ABC三端审查报告_2026-06-18.md) §二·#2

---

## BUG-026: `_grade` 的 `question_index` 仍依赖 LLM grades 数组隐式顺序

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-18 |
| **发现阶段** | W1-2 ABC 三端审查 |
| **严重程度** | 🔴 高 — BUG-022 治标未治本，LLM 漏题/乱序时仍会指错题目 |
| **影响范围** | 后端 `backend/app/agents/diagnostics.py:_grade()` |
| **决策人** | A 认领 |
| **状态** | ✅ 已解决（2026-06-18 A 端修复） |

### 问题描述

BUG-022 想根除"前端顺序依赖"，把 `per_node` 升级为 `[{question_index, correct}]`。但后端实现：

```python
# backend/app/agents/diagnostics.py:149-155
for idx, g in enumerate(grades):     # idx 是 grades 数组下标
    correct_by_node.setdefault(nid, []).append({
        "question_index": idx,        # ❌ 直接当成 questions 索引使用
        "correct": ok,
    })
```

`idx` 是 LLM 返回的 grades 数组下标，**仍假设 grades 顺序 == questions 顺序**。LLM 漏题/乱序时：
- 旧前端：错位（红绿混乱）
- 新前端：用错位的 `question_index` 索引 `questions[idx]` → **依然错位**

治标未治本。

### 根因

- 判分 prompt 未要求 LLM 显式回写 `question_index`
- 后端轻信 LLM 返回数组的隐式顺序

### 决策

**修判分 prompt 让 LLM 显式回写题目在原 questions 数组中的真实下标，后端用 LLM 提供的 `question_index` 取值，并加边界 fallback。**

### 执行（待 A 认领）

- ✅ `_grade` system 消息加上：`{"question_index": <题目在原 questions 数组中的下标，从 0 开始>, "node_id": ..., "correct": ...}`
- ✅ 后端取值：`q_idx = g.get("question_index", idx)`，并校验 `0 <= q_idx < len(questions)`，越界/非 int 时 fallback 到 `idx`；非 dict 元素跳过
- ✅ `test_diagnostics_unit.py` 增加 3 个用例：乱序显式回写、缺 question_index 回退、越界回退

### 验证

- `pytest tests/` 51 passed
- 用例 `test_grade_disordered_question_index` 验证：LLM 乱序返回 grades（先 q2 再 q0 再 q1）但显式回写正确 `question_index` 时，`per_node` 正确归位、`correct_count` 正确

### 详见

[docs/legacy/三人协作时代/W1-2_ABC三端审查报告_2026-06-18.md](../legacy/三人协作时代/W1-2_ABC三端审查报告_2026-06-18.md) §二·#4

---

## 2026-06-18 A 端代码审查修复批次（F1~F7）

> 审查人：A + Claude（全量后端代码审查）。A 端 6 条已修复，B 端 4 条移交 B 认领。

### 已修复（A 端）

| # | 严重度 | 位置 | 问题 | 修复 |
|:---|:---|:---|:---|:---|
| F1 | 🔴 | `main.py` lifespan | 运行时 KG 单例从未接入 embedding 客户端，`/search` 恒 503、`hybrid_retrieve` 向量阶段恒跳过 | lifespan 调 `create_embedding_client()` 注入 `from_settings`；探测失败自动降级纯图模式 |
| F2 | 🔴 | `reviewer.py` | LLM 审核 JSON 非 conforming（扁平 score/缺 issues/返回数组）时 `_merge_issues`/`_weighted_score` 崩溃，且不在声称的 try/except 内 | 新增 `_normalize_dims` 归一化为 `{dim:{score,issues}}`，缺字段补默认；`_merge_issues`/`_weighted_score` 改用 `.get` 防御 |
| F3 | 🟡 | `engine.py:assemble_learning_path` | `level` 参数全程未用，零基础用户可能拿到难度 4-5 节点 | 展平阶段按 `difficulty ≤ level+2` 过滤 |
| F5 | 🟡 | `diagnostics.py:_grade` | `per_node` 以 LLM 回传 `node_id` 为键，漏写/错写时逐节点掌握度全丢 | 用可靠 `question_index` 反查 `questions[q_idx].node_id`，仅反查失败才信任 grade 回传 |
| F6 | 🟡 | `reviewer.py:reviewer_node` | 无顶层 try/except，硬规则 `kg.get_node` 抖动直接 500 | 加与 diagnostics/graph_controller 一致的顶层 try/except，降级为审核不通过 |
| F7 | 🟢 | `graph_controller.py` | 空画像/异常分支 `knowledge_graph` 缺 `node_status_updates`/`assembled_at`，与契约不一致 | 补齐两字段，三分支结构统一 |

测试：pytest 77 passed（+7：normalize_dims 6 + F5 node_id 反查 1）；validate_data 0 错误。

### 移交 B 端认领（BUG-027~030）

以下为 B 端前端审查发现，A 端未改（目录归属 B）。建议 B 按 BUG 编号认领修复。

---

## BUG-027: Assessment.vue el-alert 错误原因被插槽覆盖不显示

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-18 |
| **发现阶段** | W3 A/B 端代码审查 |
| **严重程度** | 🟡 中 — 错误反馈主通道失效，用户看不到失败原因 |
| **影响范围** | `frontend/src/views/Assessment.vue:98-113` |
| **责任方** | B |
| **状态** | ✅ 已解决（commit pending，2026-06-19） |

### 问题描述

`el-alert` 同时设了 `:description="store.error"` 和 `#default` 插槽（插槽内仅一个"重新测评"按钮）。Element Plus 的 `default` 插槽就是描述内容插槽，提供后**替换** `description` prop，导致 `store.error`（如"Neo4j 未就绪""网络错误"）不渲染。用户只看到标题+按钮，看不到原因。

### 决策

把错误文案放进插槽，按钮置于其下：
```html
<template #default>
  <p style="margin: 0 0 8px;">{{ store.error }}</p>
  <el-button size="small" type="primary" @click="retry">重新测评</el-button>
</template>
```

### 执行

- `Assessment.vue:98-113` 删除 `:description` prop，改为 `<template #default>` 内 `<p>{{ store.error }}</p>` + 按钮 ✅
- 配合 BUG-028 一同生效（空画像降级时 retry_hint 经由 store.error 进 alert 展示）

### 验证

- 30 vitest 用例全通过 + 新增 12 例（reset/BUG-028/030/diagnostics-api）共 42 用例全通过

---

## BUG-028: 后端降级空画像时前端静默失败无反馈

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-18 |
| **发现阶段** | W3 A/B 端代码审查 |
| **严重程度** | 🟡 中 — 用户等数秒后静默回到输入表单，无任何提示 |
| **影响范围** | `frontend/src/stores/assessment.js:59-64,120-133` + `Assessment.vue` 状态分支 |
| **责任方** | B |
| **状态** | ✅ 已解决（commit pending，2026-06-19） |

### 问题描述

后端 LLM 未配置/异常时 `diagnostics_node` 返回 `user_profile={}`，工作流耗尽重试后 HTTP 200 结束，响应含 `review_results.retry_hint`。前端 `hasResults` 因空对象守卫返回 false、`error` 保持 null → 四状态分支全落空，静默回输入表单。后端已给出精准 `retry_hint`，前端未消费。

### 决策

`startAssessment` 成功后检测空画像并抛出反馈：
```js
if (!data.profile || Object.keys(data.profile).length === 0) {
  error.value = data.review_results?.retry_hint
    || '学情检测未产出有效画像（后端 LLM 可能未配置），请检查后端配置后重试'
  profile.value = null  // 防 hasResults 误判
  return
}
```
（需配合 BUG-027 修复，否则 error 文案仍不在 alert 显示。）

### 执行

- `stores/assessment.js` try 块成功路径补空画像检测 + 写 retry_hint 到 error + 清 profile ✅
- 与 BUG-027 联动：alert 现可正确显示 retry_hint 文案

### 验证

- 新增 3 条 vitest 用例覆盖：retry_hint / 默认提示 / profile=null 防御 — 全通过
- BUG-027 修复联跑后人工验证 alert 显示 retry_hint（待真实后端联调阶段）

---

## BUG-029: AssessmentReport 未作答题目渲染空白（兜底死代码）

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-18 |
| **发现阶段** | W3 A/B 端代码审查 |
| **严重程度** | 🟢 低 — demo 模式 LLM 全作答，interactive 模式（W5）才暴露 |
| **影响范围** | `frontend/src/components/AssessmentReport.vue:152,58` |
| **责任方** | B |
| **状态** | ✅ 已解决（commit pending，2026-06-19） |

### 问题描述

`questionList` 中 `answer: answers[idx] ?? ''` 把 undefined 强制转空字符串，模板 `{{ q.answer ?? '（未作答）' }}` 的 `??` 对空字符串不触发兜底 → 未作答题显示空白。

### 决策

`answer: answers[idx] ?? null`（保留 null 让 `??` 生效），或模板改 `{{ q.answer || '（未作答）' }}`。

### 执行

- `AssessmentReport.vue:152` `?? ''` → `?? null`（保留 null 语义）✅

---

## BUG-030: B 端 store 未消费 knowledge_graph 字段

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-18 |
| **发现阶段** | W3 A/B 端代码审查 |
| **严重程度** | 🟢 低 — W3 路径展示组件接入时一并处理 |
| **影响范围** | `frontend/src/stores/assessment.js:129-133` |
| **责任方** | B |
| **状态** | ✅ 已解决（commit pending，2026-06-19） |

### 问题描述

后端 `/assess` 响应新增 `knowledge_graph`（含 `learning_path`/`path_node_ids`/`estimated_total_hours`，A 端第3周 graph_controller 组装），store 映射 6 字段中唯独未存 `data.knowledge_graph`，学习路径在前端被丢弃。属 W3 接入项，非阻断。

同样情况：`generated_content`（W4 内容生成产出）也被丢弃。

### 决策

W3 KnowledgeGraph 主图组件开发时，store 补 `knowledge_graph` 字段映射并据此渲染学习路径。一并处理 `generated_content`。

### 执行

- `stores/assessment.js` 新增 `knowledgeGraph` / `generatedContent` 两个 ref ✅
- `startAssessment` 成功路径：`knowledgeGraph.value = data.knowledge_graph || null`、`generatedContent.value = data.generated_content || null` ✅
- `reset()` 清空两字段 ✅
- store return 导出两字段，供 W3 图谱页 / W4 资源页消费 ✅

### 验证

- 新增 2 条 vitest 用例覆盖：成功填充 / 响应缺字段时为 null — 全通过

---

## 2026-06-18 W5 全量代码审查修复批次（BUG-031~033，A 端）

> 审查人：A + Claude（W5 interactive + 动态反馈全量审查）。3 条均 A 端已修复。

## BUG-031: 工作流无限循环（画像通过 + 内容空资源时 retry 预算被绕过）

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-18 |
| **发现阶段** | W5 全量代码审查 |
| **严重程度** | 🔴 高 — demo 模式 500，浪费多轮 LLM/Neo4j |
| **影响范围** | `orchestrator.py:_decide_after_review` + `reviewer.py` 模式判断 + `content_generator.py` 空资源 |
| **责任方** | A |
| **状态** | ✅ 已解决 |

**问题**：画像审核通过 → graph_controller → content_generator 产出空 resources（学习路径空/生成全失败）→ reviewer `bool([])`=False 回退画像模式 → 画像仍通过 → graph_controller…无限循环。retry_count 每轮+1 但画像通过分支不查 over_limit，直到 LangGraph 递归上限抛 GraphRecursionError → 500。

**修复**：
1. state 新增 `content_phase_entered` 标志位，content_generator 三个 return 分支均置 True。
2. reviewer 改用 `content_phase_entered` 判断模式（非 `bool(resources)`）；内容阶段 resources 空 → 直接判不通过（无内容可交付）。
3. orchestrator 画像通过分支加 `over_limit` 守卫（止血双保险）。

## BUG-032: `_grade` 判分的两个静默正确性隐患

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-18 |
| **发现阶段** | W5 全量代码审查 |
| **严重程度** | 🟡 中 — 静默误判分，画像/反馈策略失真 |
| **影响范围** | `diagnostics.py:_grade` |
| **责任方** | A |
| **状态** | ✅ 已解决 |

**问题**：
- `bool(g.get("correct"))` 对字符串 `"false"` 误判为 True（非空字符串恒真）。
- 不按 `question_index` 去重，LLM 多返/重复条目虚增 `correct_count`，accuracy 可超 1.0。

**修复**：correct 区分 bool/str（`"true"`→True）/其他；`seen_q_idx` 集合按 question_index 去重。

## BUG-033: interactive 出题阶段下发正确答案 + 畸形 known_topics 500

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-18 |
| **发现阶段** | W5 全量代码审查 |
| **严重程度** | 🟡 中 — 答案泄露 + 畸形输入崩溃 |
| **影响范围** | `api/diagnostics.py` assess + `diagnostics.py:_fetch_candidate_nodes` |
| **责任方** | A |
| **状态** | ✅ 已解决 |

**问题**：
- assess(interactive) 直接返回含 `answer` 的 questions，正确答案在用户作答前到达前端（测评完整性风险）。
- `_fetch_candidate_nodes` 缺 `isinstance(t, dict)` 守卫，known_topics 含非 dict 元素（如字符串简写）时 AttributeError → interactive 出题 500。

**修复**：assess(interactive) 返回前剥离 `answer`（缓存保留完整题目供 submit 判分）；`_fetch_candidate_nodes` 加 isinstance 守卫，与 graph_controller 对齐。

**测试**：pytest 130 passed（+6：BUG-031 循环防护 / BUG-032 字符串布尔+去重 / BUG-033 answer 剥离+isinstance）。

---

## 2026-06-18 W7①场景一回归发现批次（BUG-034~038，A 端）

> W7①全流程回归测试（真实 Neo4j + DeepSeek V4 Pro）发现画像构建+reviewer 阻塞性 Bug。stream 逐节点定位 + retry_hint 诊断。5 条均 A 端已修复，单测保障。**遗留：demo 模式 LLM 作答随机导致闭环结果不稳定，需继续细调（高优先级）。**

## BUG-034: recommended_path.next_nodes 推荐已掌握节点

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-18 |
| **发现阶段** | W7①场景一回归 |
| **严重程度** | 🟡 中 — 画像 logic_consistency 低分，审核打回循环 |
| **影响范围** | `diagnostics.py:_suggest_next_nodes` |
| **责任方** | A |
| **状态** | ✅ 已解决 |

**问题**：`_suggest_next_nodes` 取 current_node 之后的候选节点，不过滤 known_topics。候选含 mastery=1.0 已掌握节点 → next_nodes 推荐已掌握节点 → reviewer 判 logic_consistency 矛盾打回。

**修复**：`_suggest_next_nodes` 加 `known_ids` 参数，排除已掌握节点。`_build_profile` 调用处传 known_ids。

## BUG-035: theory_level 与正确率不自洽

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-18 |
| **发现阶段** | W7①场景一回归 |
| **严重程度** | 🟡 中 — 画像 factual_accuracy 低分，审核打回 |
| **影响范围** | `diagnostics.py:_build_profile` level 映射 |
| **责任方** | A |
| **状态** | ✅ 已解决 |

**问题**：`theory_level = int(overall*5)+1` 把 0.7 正确率误判 4 级，但 4 级语义应≥0.85（reviewer prompt），reviewer 判 factual_accuracy 不自洽打回。

**修复**：抽 `_derive_theory_level` 纯函数，保守分段映射 `<0.6→1, <0.7→2, <0.8→3, <0.9→4, ≥0.9→5`，使级数与正确率自洽（0.7→3，0.85→4）。

## BUG-036: weak_topics.error_patterns 笼统/与错题不符

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-18 |
| **发现阶段** | W7①场景一回归 |
| **严重程度** | 🟡 中 — 画像 teaching_appropriateness 低分，审核打回 |
| **影响范围** | `diagnostics.py:_build_profile` / `_build_error_patterns` |
| **责任方** | A |
| **状态** | ✅ 已解决 |

**问题**：error_patterns 硬编码 `"{name}相关题目答错"` 笼统；初版改用 key_points[0] 猜知识点，reviewer 批"与实际错题不符/fabricated"。

**修复**：`_build_profile` 接收 questions，构建 node_id→错题列表映射；`_build_error_patterns` 优先引用**实际错题题目**（与错题 100% 对齐），无错题文本回退 common_mistakes/key_points。submit 接口同步传 questions。

## BUG-037: reviewer 内容模式漏传 profile 致 TypeError 降级

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-18 |
| **发现阶段** | W7①场景一回归 |
| **严重程度** | 🔴 高 — 内容审核 LLM 调用失败，降级为仅硬规则（生成内容未被真正校验） |
| **影响范围** | `reviewer.py:reviewer_node` 内容模式 llm_arg |
| **责任方** | A |
| **状态** | ✅ 已解决 |

**问题**：内容模式 `llm_arg = resources`（单值），但 `_llm_review_content(resources, profile)` 需两参。第317行 `llm_review(llm_arg)` 漏传 profile → TypeError → except 降级仅硬规则 → 内容审核形同虚设（硬规则过即满分）。

**修复**：内容模式 `llm_arg = (resources, profile)`，与画像模式 `(profile, assessment)` 一致。加回归测试 `test_reviewer_node_content_mode_calls_llm_with_profile`。

## BUG-038: 全掌握画像逻辑矛盾（起点已掌握+4周）

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-18 |
| **发现阶段** | W7①场景一回归 |
| **严重程度** | 🟡 中 — 全掌握边界画像矛盾，审核打回 |
| **影响范围** | `diagnostics.py:_build_profile` recommended_start/estimated_weeks |
| **责任方** | A |
| **状态** | ✅ 已解决 |

**问题**：全对(10/10)时无弱项，recommended_start 回退 nodes[0]/PY-001（已掌握），BUG-034 修复后 next_nodes 排除全部已知→空，estimated_weeks 固定 4 → reviewer 判"全掌握却安排4周起点已掌握，矛盾"。

**修复**：recommended_start 改为"第一个未掌握候选"（无弱项时），全掌握时取最后节点作巩固方向；estimated_weeks 无弱项时按未掌握节点数（全掌握→1周巩固），不再固定 4。

**测试**：pytest 249 passed（+9：BUG-034 排除已知/空集 + BUG-035 映射 + BUG-036 错题/common_mistakes/key_points 兜底 + BUG-037 内容模式 LLM 回归 + BUG-038 全掌握边界）。

**遗留**：demo 模式 LLM 模拟初学者作答有随机性（_demo_answer），每次跑 assess 作答不同（7/10、10/10 等），闭环结果不稳定。5 个 Bug 修复是确定代码质量提升，但"assess 稳定通过"需继续细调 demo 行为或改用 interactive 固定答案验证。**高优先级，明天继续。**

## BUG-039: mastery 阈值与 prompt 三段制不一致（diagnostics/graph_controller 误判 known）

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-19 |
| **发现阶段** | W7②场景一回归（深挖 BUG-038 遗留的 demo 不稳定） |
| **严重程度** | 🔴 高 — 确定性 bug，画像 known/weak 划分与 prompt 权威定义矛盾，致审核打回 |
| **影响范围** | `diagnostics.py:_build_profile` mastery 分段、`graph_controller.py:_derive_status_updates`、`weakness_areas` 构建 |
| **责任方** | A |
| **状态** | ✅ 已解决 |

**问题**：`data/prompts/02_diagnostics_agent.txt` 第69-71行权威定义三段制——mastery≥0.8 已掌握(known)、0.5-0.8 学习中、<0.5 未掌握/困难(weak)。但 `diagnostics.py:_build_profile` 用 `mastery >= 0.5` 判 known，把"学习中(0.5-0.8)"误判为已掌握；`graph_controller._derive_status_updates` 同样用 0.5。导致：画像 known_topics 混入实际"学习中"节点，与 reviewer 预期（known 应≥0.8）矛盾，content 模式审核打回循环。

**根因**：阈值硬编码 0.5 与 prompt 三段制定义脱节，属代码与 prompt 契约不一致的确定性 bug（非 LLM 随机性）。前期误判为"demo LLM 作答随机性"，systematic-debugging Phase1 用真实 workflow invoke 复现后确认为确定性。

**决策**：对齐 prompt 三段制权威定义。`_build_profile`：`mastery >= 0.8` → known，否则 → weak（含"学习中"与"困难"）；`graph_controller._derive_status_updates`：known 判定同步改为 `>= 0.8`。0.85 的 `REVIEW_PASS_THRESHOLD`（赛题抗幻觉要求）不降。

**执行**：
- `diagnostics.py` mastery 分段改 0.8 阈值；`weakness_areas` 复用 weak_topics（不再独立按 0.5 重算，避免"weakness_areas 说无明显弱项但 weak_topics 有3个"自相矛盾），<0.5 标"掌握不足"、0.5-0.8 标"尚需巩固"。
- `graph_controller.py` `t.get("mastery",0) >= 0.8` 判 known→mastered。
- 单测 `test_build_profile_mastery_boundary` 改三段制断言（1.0→known, 0.5→weak, 0.0→weak）；`test_status_updates_known_mastered`/`test_status_updates_known_below_threshold_not_mastered` 对齐。

## BUG-040: reviewer 误读 last_test_score 占位字段致画像误打回

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-19 |
| **发现阶段** | W7②场景一回归（BUG-039 修复后 run1/run2 仍打回） |
| **严重程度** | 🟡 中 — reviewer LLM 误判占位/换算字段为"事实矛盾"，画像审核偶发误打回 |
| **影响范围** | `reviewer.py:_llm_review` 审核要点文案 |
| **责任方** | A |
| **状态** | ✅ 已解决 |

**问题**：BUG-039 修复后画像 known/weak 正确，但 run1/run2 仍打回。retry_hint 显示 reviewer 把 `last_test_score=10.0`（实为 mastery×10 的 0-10 分制掌握分）误读为"答对10题"；又把 `learning_style/practical_level/preferred_pace/time_per_week` 等未测评字段的默认占位值当作"事实矛盾"扣分。

**根因**：画像字段语义（last_test_score 是掌握分非答对数；部分字段是待采集占位值）未在审核 prompt 说明，reviewer LLM 凭字段名猜测语义致误判。

**决策**：在 `_llm_review` 审核要点补字段说明，明确 last_test_score 是 0-10 分制掌握分（mastery×10，满分10）非答对题数；learning_style 等为未测评字段默认占位值不作事实审核；mastery 三段制 ≥0.8 known / <0.8 weak。不改阈值、不改画像字段。

**执行**：`reviewer.py:_llm_review` user message 追加"字段说明(勿误判)"段。

## BUG-041: content_generator LLM 偶发返回数组致 ValueError 中断

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-19 |
| **发现阶段** | W7②场景一回归（BUG-039/040 修复后 run3 内容生成崩） |
| **严重程度** | 🔴 高 — 内容生成抛异常中断工作流，场景一无内容产出 |
| **影响范围** | `content_generator.py:_generate_one` parse_llm_json 结果处理 |
| **责任方** | A |
| **状态** | ✅ 已解决 |

**问题**：run3 `ValueError: 生成响应非对象: <class 'list'>`——LLM 偶发把多资源放进 JSON 数组返回，`parse_llm_json` 返回 list，`_generate_one` 直接当 dict 用崩。该异常经 `_safe_generate` 计为失败拖累整体（9段全失败则无内容）。

**根因**：`_generate_one` 未防御 list 返回，与 `_generate_feedback_one`（已有 dict 校验）不一致。

**决策**：`_generate_one` 防御 list——取首个 dict 元素；无可用 dict → 降级空资源 dict（setdefault 补全字段），不抛异常。与现有降级策略一致（不中断工作流）。

**执行**：`content_generator.py:_generate_one` 加 list→首 dict / 空降级 分支。单测 `test_generate_one_list_response_takes_first_dict` + `test_generate_one_list_no_dict_degrades_gracefully`。

**验证**：pytest 252 passed（249→+3：BUG-039 阈值边界 + BUG-041 list 两例）。

**遗留**：剩余"不稳定"经系统排查确认为 LLM 内容生成事实幻觉（如"int 内部用30/15位数组"等图谱外技术细节），被 reviewer 抓到打回重生成——**此为赛题(4)①"辩论与交叉验证消除幻觉"机制的预期行为（加分项），非 bug**。4次跑3次通过。后续 W7②层次1减幻觉方案（强化 content_generator prompt 禁止图谱外事实 + reviewer 审核要点对齐）继续提升通过率。

## BUG-042: assemble_learning_path 只插弱项前置、漏弱项节点本身 (覆盖率 33%)

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-19 |
| **发现阶段** | W7②赛题M5质量检测首轮（run_quality_test.py 跑3画像） |
| **严重程度** | 🔴 高 — 赛题(2)"精准锚定盲区"+M5覆盖率≥90%不达标，路径漏掉2/3弱项 |
| **影响范围** | `engine.py:assemble_learning_path` 弱项补丁逻辑 |
| **责任方** | A |
| **状态** | ✅ 已解决 |

**问题**：质量检测首轮覆盖率 33.3%（3弱项仅1入路径），且3个差异极大的路径（4/12/12节点）全是精确1/3——跨规模一致性暗示非真实覆盖缺口而是逻辑缺陷。

**根因**：`assemble_learning_path` 注释称"弱项前置依赖链优先插入"，但 F8 patch 只 `get_prerequisites(wid)` 插入前置依赖，从不把弱项节点本身纳入路径。弱项节点除非恰好落在 BFS 扩散（known 后继）范围内否则不入路径 → 3弱项仅1命中。

**决策**：F8 patch 之后追加弱项节点本身（前置先入、弱项紧随），受 `difficulty_cap` 保护（零基础 level=1 不直推难度4-5弱项避免挫败，其前置已先入路径），去重（known_set/path_ids）。

**执行**：`engine.py:assemble_learning_path` 弱项补丁段重写。单测 `test_engine_learning_path.py` 6例。

**验证**：真实集成覆盖率 33.3%→100%，3画像全达标。

## BUG-043: content_generator LLM 自填 difficulty_level 覆盖节点难度 (适配率 52%)

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-19 |
| **发现阶段** | W7②赛题M5质量检测首轮 |
| **严重程度** | 🟡 中 — M5适配率≥85%不达标，资源难度与知识点难度错位 |
| **影响范围** | `content_generator.py:_build_generation_prompt` + `_generate_one` |
| **责任方** | A |
| **状态** | ✅ 已解决 |

**问题**：质量检测首轮适配率 51.9%，资源难度与节点难度 |gap|>1 偏多。

**根因**：`_build_generation_prompt` 让 LLM 输出 `"difficulty_level": 1-5`，`_generate_one` 用 `setdefault`——LLM 自填值（讲义倾向填偏高）覆盖节点难度，gap 错位。难度本应由图谱事实决定（"组装而非生成"理念），非 LLM 臆造。

**决策**：① prompt 去掉 difficulty_level 字段、注明"由系统统一赋值"；② `_generate_one` 把 `setdefault` 改为强制赋值 `data["difficulty_level"] = node.difficulty`，LLM 若仍返回也覆盖。资源难度严格对齐节点 → gap=0。

**执行**：`content_generator.py` 两处改动。单测 +2例（强制覆盖/节点无难度兜底）。

**验证**：真实集成适配率 51.9%→100%，3画像全达标。

## BUG-044: content_generator 反馈再生路径漏修 BUG-043 (难度仍 LLM 自填)

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-19 |
| **发现阶段** | W7②运行时 prompt 对齐审查 (比对初稿/运行时发现) |
| **严重程度** | 🟡 中 — 反馈再生内容 (POST /api/diagnostics/feedback) 难度漂移, 适配率在反馈路径破 |
| **影响范围** | `content_generator.py:_generate_feedback_one` prompt + 难度赋值 |
| **责任方** | A |
| **状态** | ✅ 已解决 |

**问题**：BUG-043 修复主生成路径 `_generate_one` 强制 difficulty_level=节点难度, 但反馈再生路径 `_generate_feedback_one` (动态反馈 remediate/scaffold/advance) 的 prompt 仍含 `"difficulty_level": 1-5` 且用 setdefault — LLM 自填难度漂移问题在反馈路径复现, 适配率指标在动态反馈内容上失效。

**根因**：BUG-043 修复时只覆盖主路径, 未同步反馈路径 (两路径 prompt 各自硬编码, 无共享)。运行时/初稿 prompt 分离维护导致漏洞。

**决策**：反馈路径同步修复 — prompt 去掉 difficulty_level 字段+注明系统赋值; `_generate_feedback_one` setdefault 改强制赋值节点难度。两路径一致。

**执行**：`content_generator.py` 两处改动。单测 `test_generate_feedback_one_forces_difficulty_to_node`。

**验证**：314 测试通过 (313→+1)。

**教训**：运行时 prompt 与初稿分离维护会漂移 + 同源 bug 易漏修。本次顺带补入初稿 5 级脚手架到运行时 (主生成路径 practice_guide 原只到第1级) + 补 code_reviewer 初稿 (交付缺口)。

---

## 2026-06-19 C 端全量代码审查批次（BUG-045~047）

> 审查人：C（数据端全量代码审查）。3 条发现，涉及 useAgentStatus emoji/关键字匹配 + MarkdownViewer XSS。

### BUG-045: useAgentStatus — diagnostics 与 graph_controller 状态恒显示 idle

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-19 |
| **发现阶段** | 数据端C全量审查 |
| **严重程度** | 🔴 高 — AgentView 页面两个 Agent 永远显示"空闲"，前端演示时可见 |
| **影响范围** | `frontend/src/composables/useAgentStatus.js` |
| **决策人** | C（数据端审查发现，C 修复） |
| **状态** | ✅ 已解决 |

**问题**：`useAgentStatus.js` 通过 emoji 正则 `/📚|🔍|📊/` 和关键字映射推导各 Agent 状态，与后端实际日志不匹配：

| Agent | 后端日志 | 关键字匹配 | emoji 匹配 | 结果 |
|:---|:---|:---|:---|:---|
| diagnostics | `🔧 学情检测: 开始` | ✅ `学情检测` | ❌ `🔧` 不在 `/📚\|🔍\|📊/` | 恒 idle |
| graph_controller | `🗺️ 知识图谱管控: 开始组装学习路径` | ❌ `/图谱组装/` 不匹配 | ❌ `🗺️` 不在模式 | 恒 idle |

**根因**：
1. diagnostics: 后端使用 emoji `🔧`（扳手），前端只匹配 `📚|🔍|📊`（书籍/放大镜/图表），漏了 `🔧`
2. graph_controller: 关键字 `/图谱组装/` 需要连续出现，但实际日志是 `知识图谱管控: 开始组装学习路径`（"图谱"和"组装"之间有 `管控: 开始`）

**决策**：emoji 模式 `📚|🔍|📊` → `📚|🔍|📊|🔧|🗺️`；关键字 `/图谱组装/` → `/知识图谱|图谱组装/`；orchestrator 额外处理 `⚠️ 流程结束` 也判为 done。

**执行**：`useAgentStatus.js` emoji 扩充 + KEYWORD_MAP 修正 + ⚠️ 降级兜底 ✅

---

### BUG-046: MarkdownViewer `v-html` 无 XSS 过滤

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-19 |
| **发现阶段** | 数据端C全量审查 |
| **严重程度** | 🟢 低 — 内容由自有 LLM 生成，非用户输入，XSS 风险极低 |
| **影响范围** | `frontend/src/components/MarkdownViewer.vue:2` |
| **决策人** | C（数据端审查发现，C 修复） |
| **状态** | ✅ 已解决 |

**问题**：`MarkdownViewer.vue` 使用 `v-html="renderedHtml"` 直接渲染 `marked.parse()` 输出。`marked` 默认不消毒 HTML 标签。若 LLM 生成的 markdown 中包含恶意标签（概率极低但非零），会被浏览器执行。

**决策**：引入 DOMPurify 消毒（一行代码），`marked.parse()` → `DOMPurify.sanitize(marked.parse())`。

**执行**：`npm install dompurify` + `MarkdownViewer.vue` 消毒 ✅

---

### BUG-047: KEYWORD_MAP 缺 `graph_controller` 匹配 → Agent 状态无法推导

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-19 |
| **发现阶段** | 数据端C全量审查 |
| **严重程度** | 🔴 高 — 同 BUG-045，是根因之一 |
| **影响范围** | `frontend/src/composables/useAgentStatus.js:55-62` |
| **决策人** | C（数据端审查发现，C 修复） |
| **状态** | ✅ 已解决（与 BUG-045 一并修复） |

**问题**：`KEYWORD_MAP` 中 graph_controller 匹配规则为 `/图谱组装/`，但后端日志为 `🗺️ 知识图谱管控: 开始组装学习路径`。`图谱组装` 不连续出现 → 正则不命中 → graph_controller 状态永不被更新。

**决策**：与 BUG-045 一并修复，改为 `/知识图谱|图谱组装/`。

---

## 2026-06-19 B 端第3-4周代码审查批次（BUG-048~056，B 端）

> 审查人：Claude（B 端全量代码审查 + A/B 兼容性交叉审查）。9 条 B 端 Bug。

### BUG-048: KnowledgeGraph G6 图谱无边——`prerequisites` 字段在 Neo4j 节点中不存在

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-19 |
| **发现阶段** | B 端第3周代码审查（A/B 兼容性） |
| **严重程度** | 🔴 高 — G6 图谱只渲染孤立节点，零条边，核心功能完全不可用 |
| **影响范围** | `frontend/src/composables/useGraphData.js:52-53` + `KnowledgeGraph.vue` |
| **责任方** | B（前端）+ A（后端可配合） |
| **状态** | ✅ 已解决 |

**问题**：`useGraphData.js` 从 `learning_path[]` 节点读取 `n.prerequisites` 数组来构建 G6 边。Neo4j `KnowledgeNode` 不存储 `prerequisites` 属性（该字段仅在导入时用于创建 `REQUIRES` 关系）。`n.prerequisites` 恒为 `undefined`，边数组始终为空。

**决策**：方案 A（前端自愈）——`KnowledgeGraph.vue` 在 `onMounted` 后 `Promise.all(path_node_ids.map(getPrerequisites))` 批量获取前置依赖，注入 `useGraphData.setPrereqMap()`。

**执行**：`useGraphData` 新增 `prereqMap` ref + `setPrereqMap()`；`KnowledgeGraph.vue` 新增 `fetchPrerequisites()` 在 `onMounted` / store watch 中调用。

---

### BUG-049: 空搜索结果导致全图节点变灰（空 Set 为 truthy）

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-19 |
| **发现阶段** | B 端第3周代码审查 |
| **严重程度** | 🟡 中 — 搜不到结果时图谱全灰，用户困惑 |
| **影响范围** | `KnowledgeGraph.vue:427,273-284` |
| **责任方** | B |
| **状态** | ✅ 已解决 |

**问题**：`handleSearch` 搜索结果为空时，`highlightIds.value = new Set([])`——空 Set 是 truthy，所有节点被设为灰色。**根因**：`new Set([])` 与 `null` 的 truthy/falsy 差异未处理。**决策**：空结果时 `highlightIds = null` + 模板新增 `el-alert` 提示"未找到匹配节点"。

**执行**：`handleSearch` 中 `searchNodes.length===0` 时 `highlightIds=null` + `searchNoResult=true` ✅

---

### BUG-050: 搜索/筛选期间所有边统一变暗（含连接高亮节点的边）

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-19 |
| **发现阶段** | B 端第3周代码审查 |
| **严重程度** | 🟡 中 — 搜索时关系完全不可见 |
| **影响范围** | `KnowledgeGraph.vue:286-291` |
| **责任方** | B |
| **状态** | ✅ 已解决 |

**问题**：高亮分支中所有边标记为 dimmed，无论边两端节点是否高亮。**决策**：仅当边两端节点均不在 `highlightIds` 中时才 dimmed。**执行**：`bothHighlighted = highlightIds.has(e.source) && highlightIds.has(e.target); dimmed: !bothHighlighted` ✅

---

### BUG-051: handleSearch 并发请求竞态——无过期响应丢弃机制

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-19 |
| **发现阶段** | B 端第3周代码审查 |
| **严重程度** | 🟡 中 — 快速连续搜索时展示过期结果 |
| **影响范围** | `KnowledgeGraph.vue:404-434` |
| **责任方** | B |
| **状态** | ✅ 已解决 |

**问题**：快速输入"A"→"B"，若"A"响应晚于"B"到达，图谱展示"A"结果。**决策**：引入递增 `searchSeq` 计数器丢弃过期响应。**执行**：`let searchSeq=0`；`handleSearch` 中 `const currentSeq=++searchSeq`；await 后 `if (currentSeq !== searchSeq) return` ✅

---

### BUG-052: G6 Graph 构造/渲染无异常保护

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-19 |
| **发现阶段** | B 端第3周代码审查 |
| **严重程度** | 🟡 中 — `new Graph()` 或 `graph.render()` 抛异常时组件崩溃 |
| **影响范围** | `KnowledgeGraph.vue:303-360` |
| **责任方** | B |
| **状态** | ✅ 已解决 |

**问题**：`initGraph()` 无 try/catch。**决策**：整体包裹 try/catch + `ElMessage.error`。**执行**：`try{...graph.render();graphReady=true}catch(e){console.error;graph=null}` + `destroyGraph` 也加 try/catch ✅

---

### BUG-053: AgentView reviewer 详情面板可能显示 "NaN%" 

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-19 |
| **发现阶段** | B 端第4周代码审查 |
| **严重程度** | 🟡 中 — 后端返回不完整 reviewResults 时 UI 显示 "NaN%" |
| **影响范围** | `AgentView.vue:115,119` |
| **责任方** | B |
| **状态** | ✅ 已解决 |

**问题**：`(overall_score * 100).toFixed(0)` 当 `overall_score` 为 `undefined` 时产生 NaN。**决策**：`(overall_score ?? 0) * 100`，同类修复 `threshold`。**执行**：两处 `* 100` 前加 `?? 0` ✅

---

### BUG-054: learning_path 节点无 `mastery` 字段——图谱着色依赖仅 `mastery_status`

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-19 |
| **发现阶段** | B 端第3周代码审查（A/B 兼容性） |
| **严重程度** | 🟡 中 — 图谱节点着色丢失细粒度掌握度，70%+ 节点灰色 |
| **影响范围** | `useGraphData.js:32` |
| **责任方** | B（前端可自愈） |
| **状态** | ✅ 已解决 |

**问题**：`useGraphData` 取 `n.mastery`（不存在）→ fallback 到 `mastery_status`（大部分未设置）→ 全灰。**决策**：从 `store.profile.known_topics/weak_topics` 构建 `masteryMap`，优先画像 mastery → 节点 mastery → mastery_status。**执行**：`masteryMap` computed + `g6Nodes` 优先画像 mastery ✅

---

### BUG-055: handleFilterChange 两个 API 均失败时 highlightIds 不变——展示过期高亮

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-19 |
| **发现阶段** | B 端第3周代码审查 |
| **严重程度** | 🟢 低 — 需同时两个 API 失败才触发 |
| **影响范围** | `KnowledgeGraph.vue:445-481` |
| **责任方** | B |
| **状态** | ✅ 已解决 |

**问题**：双 API 均异常时 `sets` 为空数组，`sets.length===0` 分支缺失。**决策**：加 `sets.length===0` → `highlightIds=null`。**执行**：`handleFilterChange` 中加 else 分支 ✅

---

### BUG-056: MarkdownViewer 使用已弃用的 `marked.setOptions()` 全局突变

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-19 |
| **发现阶段** | B 端第4周代码审查 |
| **严重程度** | 🟢 低 — marked v5+ 已弃用，污染全局状态 |
| **影响范围** | `MarkdownViewer.vue:20-23` |
| **责任方** | B |
| **状态** | ✅ 已解决 |

**问题**：`marked.setOptions()` 全局突变 + v5+ 已弃用。**决策**：per-call `marked.parse(content, {breaks, gfm})`。**执行**：移除 `setOptions`，改为 computed 内传参 ✅

## 2026-06-20 W7③ 全量代码审查批次（BUG-057~073，A 端）

> 4 路并行审查 (agents / 引擎+API / 数据脚本 / 文档一致性) 发现 17 项, 演示前 A 档 4 项 + 真实 bug B 档 13 项, 逐项系统调试法修复 + 回归测试。314→341 passed。

### BUG-057: code_tester annotate_failed_entities 误传 entities 致 AttributeError 中断测试接口 (🔴高)

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-20 |
| **发现阶段** | W7③ 代码审查 |
| **严重程度** | 🔴 高 — 场景二代码测试接口 500 |
| **影响范围** | `code_tester.py:annotate_failed_entities` + `run_tests` |
| **责任方** | A |
| **状态** | ✅ 已解决 |

**问题**：`annotate_failed_entities` 调 `_build_failed_tests(..., knowledge_nodes, knowledge_nodes)` 把领域节点 dict 列表当 entities 第3参数; 失败用例 metadata 缺 related_node (LLM 元数据不可靠常态) 时走 `_infer_related_node(case, entities)` → 对 dict 取 `.kind` → AttributeError。`build_test_report` 已成功却因这行崩溃丢报告。

**根因**：签名缺 entities 参数, 误用 knowledge_nodes 顶替; 测试全填 related_node 未覆盖该路径。

**决策**：`annotate_failed_entities` 加 entities 参数 (默认空向后兼容), run_tests 传 parsed.entities。

**执行**：`code_tester.py` 两处。回归 `test_annotate_missing_related_node_uses_entities_not_dict_attrerror` + `test_annotate_missing_related_node_no_entities_no_crash`。

---

### BUG-058: diagnostics demo 路径仍用 judge + 纯 LLM 造题, 未走题库 (🟠中-高, 赛题减幻觉卖点)

**问题**：`prepare_questions` (题库驱动) 仅 interactive `/assess` 用, `diagnostics_node._node` demo 路径走 `_generate_questions` (judge 题型 + 纯 LLM)。赛题"层次1减幻觉/题库驱动出题"在 demo 全流程 (评委看的、run_quality_test 走的) 未生效, 与 devlog"题库驱动已对齐"矛盾。

**根因**：题库驱动改造 (W7②) 只接了 interactive API, 未同步工作流 demo 节点。

**决策**：`prepare_questions` 加可选 nodes 入参; demo/interactive 统一走它; 删除 `_generate_questions`/`_build_question_prompt` 死代码 (judge 题型已无来源)。

**执行**：`diagnostics.py`。回归 `test_diagnostics_node_demo_uses_bank_not_judge` (demo 出题全 choice/fill 无 judge)。判断题作为题型整体放弃 (信息量低, 题库设计已统一 choice/fill)。

---

### BUG-059: main.py Neo4j 连接失败时 driver 泄漏 (🟠中)

**问题**：`test_connection()` False 时 `app.state.kg=None` 但局部 kg 的 driver 从未 close, shutdown 分支也不跑, 每次启动失败泄漏一个连接池。

**决策**：连接失败时 `kg.close()` 再置 None。

---

### BUG-060: async 处理器内同步阻塞 LLM/workflow 卡死并发 (🟠中)

**问题**：assess/submit/feedback/learning_report (及 graph/project 全部 handler) `async def` 内直接同步调 LLM/workflow.invoke, 跑事件循环上阻塞所有并发请求。

**决策**：全部 `async def` 改普通 `def` (FastAPI 自动丢 threadpool, 不阻塞事件循环)。语义不变。

---

### BUG-061: engine 弱项前置补丁不受 difficulty_cap (🟠中, BUG-042 遗留)

**问题**：`prereq_patch.append(pr)` 无难度检查, 而 weak_patch/BFS 有。level=1 用户可能被塞难度4前置。

**决策**：prereq_patch 追加前加 cap 判断 (超 cap 跳过, 其更基础前置通常已在 BFS 路径)。回归 `test_weak_prereq_above_difficulty_cap_skipped`。

---

### BUG-062: generate_common_mistakes 并发写同文件丢更新 (🟠中)

**问题**：节点按文件分组 (一文件 20 节点), 8 线程并发 read→改→write 整文件, 同文件两节点并发→后写覆盖先写, 部分 common_mistakes 静默丢失。validate 不报错 (只校验非空)。

**决策**：per-file 锁 (defaultdict(threading.Lock)) 串行化同文件写, 跨文件仍并发。验证 20 节点并发写无丢失。

---

### BUG-063: write_project_graph 非原子 (🟠中)

**问题**：DETACH DELETE + 多次 CREATE 分独立 auto-commit 事务, 中途失败留半残图谱无回滚。

**决策**：`execute_write(_tx_fn)` 单写事务包全部写, 任一失败整体回滚保留旧图。fake session 加 execute_write mock。

---

### BUG-064: validate_data 循环检测有环+入边崩溃 (🟠中)

**问题**：检出环 return True 早退未置 BLACK/未 pop, 环上节点残留 GRAY; 环外节点依赖环内时 `path.index(prereq)` 找不到 → ValueError 崩溃 (有环+入边场景反而炸)。

**决策**：后向边判定改 `prereq in path` (path 成员即后向边, 标准 DFS); 不早退, 正常 pop/置 BLACK。回归 4 例 (无环/简单环/环+入边不崩/自环)。

---

### BUG-065: validate_data key_points 校验与 Schema 不符 (🟠中)

**问题**：校验器 `< 2`, Schema `minItems: 3`。2 条 key_points 过校验却违反 Schema 静默入库。

**决策**：改 `< 3` 对齐 Schema。真实数据 92 节点全 ≥3, 改严安全。

---

### BUG-066: generate 脚本先 LLM 后判 skip 空转 (🟠中)

**问题**：不带 --force 重跑先烧 92 次 LLM 再全部 skip (common_mistakes + practice_questions 两脚本)。

**决策**：`_task` 入口先判 skip (已有 common_mistakes / 题目文件存在) 再调 LLM。

---

### BUG-067: 题目 source_node_id 无引用完整性校验 (🟠中)

**问题**：`validate_question` 只查 source_node_id 非空, 不校验是否对应真实节点; import 时 MATCH 0 行不报错 → 孤儿题 (PY-999) 静默入库无 HAS_QUESTION 边。

**决策**：`validate_question`/`validate_questions_dir` 加 known_node_ids 参数校验引用完整性, main 传 nodes.keys()。真实数据 276 题无孤儿。

---

### BUG-068: orchestrator _in_content_phase 与 reviewer 标志不一致 (🟠中)

**问题**：orchestrator 用 resources 非空判内容阶段, reviewer 用 content_phase_entered。空路径 (resources=[] + content_phase_entered=True) 时 reviewer 内容模式判不通过, 路由却误判画像阶段 → diagnostics 重试 (每轮 3 次 LLM, 修不了空路径) 直到 retry 上限。

**决策**：`_in_content_phase` 改用 content_phase_entered 标志; 拆 `_has_delivered_content` (文案用, 看 resources) 区分空路径。空路径改路由 content_generator (不调 LLM) 比 diagnostics 廉价。现有 `test_w4_empty_content_does_not_loop_back_to_profile` 仍过。

---

### BUG-069: code_reviewer _has_break 下钻嵌套致 while-True 假阴性 (🟡低-中)

**问题**：`ast.walk` 递归遍历所有后代, 内层 for/while/嵌套函数的 break 被误算外层 while 的 → `while True: for x: break` (真无限循环) 漏放。有 timeout 兜底故低危。

**决策**：改限定作用域遍历 (遇 FunctionDef/ClassDef/嵌套循环不下钻 break), 仅本层 break 算。回归 6 例 (本层 if break / 无 / 内层 for / 嵌套函数 / 内层 while / 混合)。

---

### BUG-070: ast_parser Jedi column 字节偏移非字符偏移 (🟡低-中)

**问题**：AST col_offset 是 UTF-8 字节偏移, Jedi infer column 期望字符偏移。中文注释/字符串代码 → Jedi 定位错位 → infer 失败回退语法名匹配 (resolved=False)。示例项目英文不触发, 用户中文代码触发。

**决策**：`jedi_resolver` 加 `_byte_col_to_char_col` (按行源码字节切片解码得字符数), 转换后传 Jedi。回归 4 例。

---

### BUG-071: loader 多文件 entity_id 碰撞 (🟡低-中, 防御性)

**问题**：entity_id 不含 module_name, 多模块同名 qualified_name 撞 → Neo4j 重复节点边连错。单文件示例不触发。

**决策**：保守防御 (不改 entity_id 格式, 改格式破坏 20+ 测试断言且单文件不触发) — `parse_project` 多文件撞名去重保留首个并警告, 避免静默重复。彻底修复 (entity_id 纳 module 前缀) 演示后做。回归 2 例。

---

### BUG-072: reviewer/code_reviewer _merge_issues 双重惩罚 (🟡低-中)

**问题**：`_merge_issues` 对所有"有 issues"维度封顶 0.6, 含 LLM 已带 issues 且已降分的维度 → 二次封顶双重惩罚, otherwise 合格内容因一条轻微 LLM issue 跌破 0.85 误打回。

**决策**：仅对 hard_issues 命中的维度封顶, LLM 维度保留原 score。reviewer + code_reviewer 两处同修。回归 3 例。

---

### BUG-073: 边角瑕疵批 (🟢低, 5 项)

- **report_builder**: mastery=0 (已测全错 weak) 被 `if m` 当 falsy 误判 unlearned → 改按"是否在 mastery_by_node"判已测。
- **validate_data**: summary 空串 (旧 `if summary` 假值漏报) + name (minLength:2) 校验补全; mastery 非数值 (旧 `0<="high"` 抛 TypeError) 加 isinstance 守卫。
- **validate_data.load_knowledge_nodes**: 显式跳过 questions/ 目录 (与 import 脚本一致, 旧靠"题目无 id"incidental 过滤)。
- **engine.annotate_risk**: 加 risk_level 白名单校验 (high|medium|low, 旧任意字符串可写)。
- **engine.assemble_learning_path**: weak_ids 切片统一常量 _WEAK_PATCH_LIMIT=3 (旧 entry 用 [:5] 补丁用 [:3] 不一致)。

---

**批次验证**：341 passed (314→+27 回归测试)。真实数据 validate_data 全过 (92 节点 + 276 题 + 4 画像, 0 错误)。文档同步: CLAUDE.md 计数 (6→7 Agent/prompt, 56 已含 B/C 端 045-056, 本批 057-073 → 共 73)、计划书版本头 (V1.6→V1.7, M5 进行中→已交付)、7 个初稿对齐运行时 (沙箱/mastery/字段/纯编排标注)。

**教训**：并行审查 (4 路独立维度) 比单线审查发现更全; 每项修复配回归测试是防止回退的唯一可靠手段; 防御性方案 (B11 去重告警而非改格式) 在破坏性改动回归风险高时是务实选择。

---

## 模板

```markdown
## BUG-XXX: 标题

| 字段 | 值 |
|:---|:---|
| **发现日期** | |
| **发现阶段** | 前置准备 / 环境搭建 / 核心开发 / 联调 |
| **严重程度** | 🔴高 / 🟡中 / 🟢低 |
| **影响范围** | |
| **决策人** | |

### 问题描述

### 根因

### 决策

### 执行

### 验证
```

---

## BUG-074: Learning 视图收编进 IDE 时漏挂载 (赛题断点 S7)

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-20 |
| **发现阶段** | IDE 化 (阶段1.5 收编) |
| **严重程度** | 🔴高 |
| **影响范围** | 赛题"个性化资源≥3形态"在 IDE 内不可见 |
| **决策人** | A |

### 问题描述
Learning.vue (讲义/实操指南/分阶测试题三形态 + 溯源) 在收编学习功能进 IDE 侧栏时遗漏挂载, grep 全 frontend/src 零引用。赛题硬性要求"≥3形态个性化资源"在 IDE 内无法查看。

### 根因
收编时 ACTIVITY_ITEMS 只加了 code/graph/assessment/agents/dashboard, 漏了 learning; MainArea 的视图装载分支也无 learning。

### 决策
sidebar.js ACTIVITY_ITEMS 加 learning 入口; MainArea.vue 加 `<Learning v-else-if="sidebar.activeView==='learning'" />`。

### 执行
stores/sidebar.js + ide/MainArea.vue 各加一行。

### 验证
build 通过; 活动栏出现学习资源图标, 点击进主区显示三形态资源 (demo 测评后 generatedContent.resources 有数据时)。

---

## BUG-075: Dashboard M5 指标造假恒绿 (赛题断点 S8)

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-20 |
| **发现阶段** | IDE 化 (Dashboard 收编) |
| **严重程度** | 🔴高 |
| **影响范围** | 赛题 M5 指标可信度, 评委一眼可识破 |
| **决策人** | A |

### 问题描述
Dashboard qualityMetrics 客户端自行派生, 幻觉率写死 `review.passed ? 0 : 0.02` 恒绿; 而后端 assess/assess_stream 已用 compute_quality_metrics 算出真实 learning_report (含真实三项指标), 但前端 store 的 _applyResult 根本没存 learning_report 字段, 真实数据被丢弃。

### 根因
IDE 化重写 Dashboard 时未对接后端 learning_report 数据契约; store 也缺 learningReport 状态。

### 决策
1. assessment store 加 learningReport 状态, _applyResult 存 data.learning_report, startDemoStream/reset 清理;
2. Dashboard qualityMetrics 优先用 store.learningReport.quality_metrics (hallucination/adaptation/coverage 各含 rate), fallback 才客户端派生;
3. 达标/未达标按真实阈值 (<5%/≥85%/≥90%) 着色, 加达标徽章 + 数据来源标识 (后端真实计算/客户端估算), 不再恒绿。

### 执行
stores/assessment.js (learningReport + _resetResult), views/Dashboard.vue (qualityMetrics 重写 + 模板着色)。

### 验证
build + 42 测试通过 (含新 learningReport 映射测试); demo 测评后 Dashboard 显示"后端真实计算"标识 + 真实指标值, 未达标项显红。

---

## BUG-076: interactive 测评一点就报错, 动态反馈前端没接 (赛题断点 S9)

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-20 |
| **发现阶段** | IDE 化 (Assessment 收编) |
| **严重程度** | 🔴高 |
| **影响范围** | 赛题"动态反馈(进阶/降维/补前置)"在 IDE 内不可演示 |
| **决策人** | A |

### 问题描述
Assessment.vue "开始测评" 调 startAssessment(mode=interactive) → 后端 interactive 只返回题目 (profile 空) → store _applyResult 触发 BUG-028 空画像分支报错"学情检测未产出有效画像"。而真正的 interactive 三步闭环 (assess 出题 → 用户答题 → submit 判分 → feedback 动态反馈) 后端路由齐全, 前端完全没接: submitAnswers/requestFeedback 无组件调用, Assessment.vue 无答题 UI。

### 根因
store 把 interactive 出题阶段的空 profile 当 demo 模式的降级错误处理 (BUG-028 逻辑误伤); interactive 闭环 UI 从未实现。

### 决策
1. store 加 interactive 三阶段状态: phase(idle/answering/feedback) + pendingQuestions/userAnswers/feedbackStrategy/feedbackContent;
2. startAssessment 改为出题阶段: 拿到 questions 进 answering, 不再调 _applyResult (避免空 profile 误报); 空题目才报"出题失败";
3. 新增 submitAssessmentAnswers (调 /submit 判分+画像+strategy → feedback 阶段) + fetchFeedback (调 /feedback 按策略再生) + backToInput;
4. Assessment.vue 加答题阶段 (选择题 radio/填空/一键填演示答案) + 反馈阶段 (画像雷达+策略标签+再生资源 MarkdownViewer);
5. 更新 assessment-store.test.js 适配新契约 (interactive 出题/submit/feedback/demo learningReport)。

### 执行
stores/assessment.js (三阶段状态 + 3 个 action), views/Assessment.vue (答题+反馈模板 + 辅助函数 + 样式), __tests__/assessment-store.test.js (重写)。

### 验证
build 通过; 42 测试全过 (含 interactive 出题/submit 判分/feedback 再生/demo learningReport 4 组新测试)。interactive: 选方向→开始测评→答题→提交→画像+策略→获取针对性反馈, 全链路通。
BUG 清单: 76 条 (76 已解决, 含 IDE 化 S7-S9 三断点)。

---

## BUG-077 / 决策: write_file 工具直接落盘缺安全门 (阶段3.1)

| 字段 | 值 |
|:---|:---|
| **发现日期** | 2026-06-21 |
| **发现阶段** | IDE 化 阶段3 (AI 助手工具调用) |
| **严重程度** | 🟡中 (设计决策, 非运行时 Bug) |
| **影响范围** | AI 助手 write_file 工具的安全性 |
| **决策人** | A |

### 问题描述
阶段2 已实现 read_file/list_directory 工具循环。阶段3 要加 write_file, 但 AI 生成代码直接落盘有两个风险: (1) 高危代码 (eval/exec/os.system/pickle 等) 被写入项目; (2) 用户对 AI 改文件无控制权。原 code_reviewer.hard_check_code_safety 已实现 AST 危险调用+无限循环预检, 但它埋在 code_reviewer.py 里, import 会连带拉入 langchain/neo4j, 不适合 chat 等轻量路径复用。

### 决策
1. 抽 `app/agents/code_safety.py` — 纯 Python (仅 ast 标准库), 含 _DANGEROUS_CALLS/_DANGEROUS_BUILTINS/hard_check_code_safety/_has_break 等; code_reviewer.py 改为 re-export (`from app.agents.code_safety import ...`), 保持 tests/外部引用向后兼容;
2. 后端新增 `POST /api/chat/safety-check` — 接 {code, filename}; 仅 .py 真做 AST 检查, 非 .py 跳过; 返回 {issues, safe, checked}; safe = 无 high severity (medium 无限循环仅提示不阻断);
3. 前端 chat.js write_file 走审批门: 调 safety-check → pendingApproval 弹卡 (用户可编辑 content) → 批准则 window.api.fs.writeFile + 刷新文件树 + 打开文件; 拒绝则把"用户拒绝写入"回传 AI 让其调整; 审批期间禁用输入/发送 (防并发 sendMessage);
4. AssistantPanel.vue 审批卡: 安全预检结果 (ok/warn/danger 着色 + 逐条 issue) + 可编辑内容 textarea + 批准/拒绝按钮。

### 执行
backend/app/agents/code_safety.py (新), backend/app/agents/code_reviewer.py (改 re-export, 删 import ast), backend/app/api/chat.py (+SafetyCheckRequest +/safety-check), frontend/src/stores/chat.js (write_file 工具 + pendingApproval 审批门), frontend/src/ide/AssistantPanel.vue (审批卡 UI), backend/tests/test_chat_safety_api.py (新, 端点+模块+re-export 共 11 测试)。

### 验证
前端 vite build 通过; 后端 test_chat_safety_api + test_code_reviewer_unit + test_code_tester_unit + test_sandbox_unit 共 74 测试全过 (re-export 身份断言 + 高危/安全/非py/语法错误分支)。safety-check 端点对 exec/os.system 返回 safe=False, 安全代码 safe=True, .js 跳过 checked=False。

---

## 阶段4: 图谱委派工具 + Monaco 符号联动 (2026-06-21)

| 字段 | 值 |
|:---|:---|
| **日期** | 2026-06-21 |
| **阶段** | IDE 化 阶段4 |
| **类型** | feat (非 Bug, 架构决策记录) |
| **决策人** | A |

### 决策

把后端三项多 Agent 能力 (code_review/code_test/generate_project_graph) 作为"委派工具"暴露给 IDE AI 助手 chat, 并实现项目代码图谱符号与 Monaco 编辑器双向联动。核心约束: 不偏离图谱事实底座 + 多智能体协同。

1. **前端驱动, 零后端改动**: chat 工具循环已在 chat.js (_executeTool 调 IPC), 委派工具延续此模式, 直接调现有 /api/project/parse|review|test 路由。不新建后端委派端点, 避免重复逻辑。
2. **Neo4j 在线要求对题**: code_review/code_test 要求 Neo4j 在线 (复用 _get_kg 503 守卫), 体现"图谱约束抗幻觉"核心创新; generate_project_graph 用 write_to_neo4j=false 轻量入口 (纯 AST+Jedi), 离线可用。503 时 AI 转告用户启动 Neo4j。
3. **长超时**: code_test (LLM 生成 pytest + 沙箱执行) 可达 60s+, 现有 http:request 60s 超时不够 → 给 http:request 加可选 opts.timeoutMs (code_test 传 180s, 默认 60s 不变, 不影响现有调用)。
4. **Monaco 联动基于项目代码图谱 (非领域图谱)**: KnowledgeGraph.vue 只渲染领域学习路径图谱 (场景一, PY-xxx 节点无行号), 与代码符号无关。故 4b 联动基于 generate_project_graph 产出的项目代码实体 (含 line_start/line_end, 已在 /parse 响应 G6 node properties 中, project.py:262-265), 通过 chat 实体列表 + Monaco 跳转实现, 不新建 G6 视图。
5. **双向联动**: 新建 stores/projectGraph.js (graph/revealTarget/activeLine/activeEntityId); chat 实体点击 → requestReveal → MonacoEditor watch revealTarget 跳转+行高亮装饰; Monaco 光标移动 → onDidChangeCursorPosition → setActiveLine → chat 实体列表反查高亮 (activeEntityId computed)。

### 执行

electron/preload/index.js + electron/main/ipc/http-proxy.js (http:request 加 opts.timeoutMs);
frontend/src/stores/chat.js (+3 工具定义/系统提示 +_executeTool 三分支 +_resolveCode +_delegate +结果 summary);
frontend/src/stores/projectGraph.js (新建);
frontend/src/ide/MonacoEditor.vue (revealSymbol + 装饰高亮 + 光标回传 + 全局 .symbol-highlight 样式);
frontend/src/ide/AssistantPanel.vue (委派结果卡: 图谱实体列表/四维度评分/通过率+覆盖率 + 实体点击/反查高亮 + 辅助函数);
CLAUDE.md (阶段4 进度 + 文件索引)。

### 验证

前端 vite build 通过; 后端 test_project_api + test_code_reviewer_unit + test_code_tester_unit + test_chat_safety_api 共 82 测试全过 (零后端改动, 无回归)。
4a: AI 调 generate_project_graph/code_review/code_test → 工具卡按类型渲染; Neo4j 离线时 503 由 AI 转告。
4b: generate_project_graph 后点实体 → 切 code 视图 + 打开文件 + Monaco 滚动高亮行区间; Monaco 移动光标 → chat 实体列表对应项高亮。

---

## 阶段5: PyInstaller 打包 backend sidecar + Windows 安装包 (2026-06-21)

| 字段 | 值 |
|:---|:---|
| **日期** | 2026-06-21 |
| **阶段** | IDE 化 阶段5 (S3) |
| **类型** | feat/build (打包打通) |
| **决策人** | A |

### 决策与踩坑

1. **spec 修复**: 上会话留的 KMatchBackend.spec 用了 `cipher=block_cipher` 参数, PyInstaller 6.x 已废弃 → 构建直接报错 (上次没跑通的真因)。移除 cipher; 加 `scripts.validate_data` hiddenimport (kb.py 模块级 `from scripts.validate_data import ...`, scripts 无 __init__, 不显式收集则打包后启动崩); 改用 `collect_all` 收 langchain/langgraph/neo4j/pydantic/jedi/uvicorn/openai 等重依赖的子模块+二进制+数据。
2. **数据目录**: config.py DATA_DIR 原硬编码 `Path(__file__).parent.parent.parent/data`, 打包后 __file__ 在 exe 内部 → 数据找不到。改为支持 `KMATCH_DATA_DIR` 环境变量 (run_server.py 打包时指向 resources/data), 开发期 fallback 原相对路径。
3. **运行时验证**: 打包 exe 启动 → `/api/health` 200, Neo4j/LLM 未配置时优雅降级 (warning 不崩)。scripts 导入 + 数据目录解析均正常。
4. **NSIS 安装包两个坑**:
   - **winCodeSign 符号链接权限**: winCodeSign.7z 含 macOS `.dyml` 符号链接, Windows 普通账号无权创建 → 开 Windows 开发者模式解决 (非管理员也能建符号链接)。
   - **GitHub 下载超时**: electron / winCodeSign / nsis 从 github.com 下载在国内频繁超时 (dial tcp 20.205.243.166:443 failed)。设 `ELECTRON_BUILDER_BINARIES_MIRROR=https://npmmirror.com/mirrors/electron-builder-binaries/` 走 npmmirror 镜像 (nsis 565ms 下完 vs GitHub 超时)。
5. **产物**: `release/KMatch·知链-0.1.0-x64.exe` (239M NSIS 安装包, 833M unpacked)。backend sidecar + data 已正确打入 resources/。

### 已知优化 (非阻塞)

- langchain_community 拖入 torch → unpacked 833M 偏臃肿。可在 spec `excludes` 加 torch 减肥 (code_test 沙箱打包后本就不可用, torch 无运行时依赖)。
- 打包后 code_test 沙箱 (`sys.executable -m pytest`) 不可用 (exe 非 python 解释器), 属已知限制, 真沙箱强化待 DockerSandboxExecutor。

### 执行

backend/KMatchBackend.spec (重写), backend/app/config.py (KMATCH_DATA_DIR), .gitignore (backend-dist/ + spec 例外), electron-builder.yml (启用 backend-dist→backend 映射), CLAUDE.md (阶段5 进度 + 打包命令小节)。

### 验证

pyinstaller EXIT=0; exe 启动 /api/health 200; electron-builder EXIT=0 → release/KMatch·知链-0.1.0-x64.exe (239M) 生成。
