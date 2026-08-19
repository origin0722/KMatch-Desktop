# 轻量化改造方案 — 端用户免 Docker（嵌入式存储替代 Neo4j sidecar）【细化版】

> 状态：**已实施（2026-08-19 · v1.0.0 · issue #50–#56 · ADR-0008）**
> 落地：`EmbeddedGraphStore`（`backend/app/graph/embedded.py`）+ `GRAPH_STORE` 开关 + 前端 StatusBar 状态点；后端 651 测 / 前端 434 测全绿。devlog：[docs/devlogs/A_后端/2026-08-19_端用户免Docker_嵌入式存储.md](../devlogs/A_后端/2026-08-19_端用户免Docker_嵌入式存储.md)。
> 本文件为**方案文档**（含实施后的偏差说明，末节）；实施细节以代码与 ADR 为准。
> 日期：2026-08-19
> 提出理由：用户诉求「将项目打包成安装包，有没有可以轻量化应用的地方，不想让用户使用应用的时候还要开 docker」，并要求「细化方案、确保功能不受影响、用户使用丝滑流畅不卡顿、UI 设计符合设计师眼光思维」。
> 关联：`docs/架构与设计/重构方案_解耦.md`、`docs/adr/0006-chat-store-decoupling.md`
> 本文件为**方案**，不含具体代码改动；实施按项目约定推进（每阶段 commit，记 ADR-0008）。

---

## 0. 默认决策（本版已拍板）

| 项 | 决策 |
|---|---|
| 端用户默认后端 | `EmbeddedGraphStore`（进程内，无 Docker / JVM / 端口） |
| Neo4j 地位 | 保留为可选后端（`GRAPH_STORE=neo4j`），dev/演示/赛题技术栈展示用 |
| 模式开关 | `GRAPH_STORE=embedded\|neo4j\|auto`；**打包（frozen）默认 `embedded`**，**dev/测试默认 `neo4j`**（实现偏差：为保现有 700+ 集成测试零漂移——大量测试 `TestClient(main.app)` 直跑 lifespan，`auto` 默认会把无 Neo4j 的测试环境切嵌入式改变行为；端用户侧由 `run_server.py` frozen 兜底，不受影响） |
| 向量语义检索 | **自动回填 + 降级**：首启无向量且有 embedding key → 后台异步回填（不阻塞启动）；无 key/离线 → 降级纯图。诚实语义：查询仍需云端编码 query，故无客户端时缓存向量也不启用检索 |
| 前端 / 现有测试 | **零改动**；嵌入式独立类 + 独立单测 |
| M5 覆盖率口径 | `assemble_learning_path` 全逻辑逐行对齐，`_WEAK_PATCH_LIMIT=8` / `difficulty_cap=level+2` 常量原样保留 |

---

## 1. 背景与目标

### 1.1 现状

KMatch-Desktop 已做到 Electron 自启 `KMatchBackend.exe`（PyInstaller FastAPI sidecar）。但 **Neo4j 仍要求端用户 `docker-compose up -d neo4j` + `import_knowledge_base.py`**，是上手唯一硬门槛，也是「用户觉得要开 docker 很重」的根因。

### 1.2 目标

1. **开箱即用**：装完 `.exe` 双击即跑，无 Docker / 无 JVM / 无端口抢占 / 秒级冷启动。
2. **功能零回退**（§5 保全矩阵逐项对照）：场景一/二闭环、学情测评、图谱、AI 助手 6 工具、KB 管理、动态建域、M5 质量链路、Runs 复盘全部可用。
3. **丝滑不卡顿**（§6）：量化启动/查询/渲染基准，去除 Neo4j 引入的端到端延迟。
4. **UI/UX 符合设计师水准**（§7）：首启引导、状态可视化、语义降级的优雅兜底，配套 IDE 设计规范审计。
5. 安装包**不增反减**，无新增运行时依赖。

---

## 2. 现状审计（全部经代码核实）

| 项 | 结论 | 出处 |
|---|---|---|
| 唯一硬 Docker 依赖 | **Neo4j**。compose 的 backend/frontend 服务仅 dev/CI 编排 | `docker-compose.yml` |
| 代码测试沙箱 | `SANDBOX_MODE=auto`：无 Docker 自动回退 `SubprocessSandboxExecutor` | `sandbox.py` |
| APOC | compose 配了 `["apoc"]`，全仓 grep **无任何调用**，是摆设；向量索引是 5.x 核心能力 | grep 空结果 |
| 知识库真相源 | `kb_store.py`：**JSON 为源，Neo4j 为派生缓存** | `kb_store.py` docstring |
| 知识库体量 | **1.7 MB / 459 文件**；222 节点 + 648 题 | `Get-ChildItem data` |
| Neo4j 独占数据 | ① 节点 `embedding`② `:ProjectEntity` 项目图 ③ `mastery_status` ④ 风险标注 | `engine.py` |
| **关键契约：`kg.embedding_client` 被外部读取** | `api/graph.py:108`、`domain_bootstrap.py:202/219` 用它做语义可用性守卫——嵌入式必须保持该属性语义 | grep `embedding_client` |
| 503 存量路径 | `api/diagnostics.py` 多处 `kg is None → 503`；`graph.py` 全部路由 `_get_kg` 无 kg 即 503 | grep `_get_kg` |

**推论**：Neo4j 只是 1.7MB JSON 的派生缓存，且端用户为它付出的成本（Docker、JVM、端口、冷启动）远超其价值。进程内重构完全可行。

---

## 3. 方案总览

```
调用方（Routes / Agents）── 只依赖 GraphStore 接口（方法签名 + 形状契约不变）
        │
        ▼
 GraphStore（抽象层，本版重点：契约 = 现有 KnowledgeGraph 方法签名 + 字段形状 + 属性语义）
  ┌──────────────────────┬───────────────────────┐
  ▼                      ▼
 Neo4jGraphStore    EmbeddedGraphStore
（现有实现原样保留）     （新模块 embedded.py，纯 Python + 可选 numpy）
        │
        └── 由 GRAPH_STORE 选择；frozen → embedded
```

**核心不变量（评审时的验收护栏）**
1. **方法签名**：`EmbeddedGraphStore` 逐一对齐 `KnowledgeGraph` 全部公有方法（§4.2 表）。
2. **返回值形状**：`node_id` 归一（`id→node_id`）、`options` list 兜底、`node_id=source_node_id` 注入、`_source/_score/_similarity` 字段，一个不差。
3. **属性语义**：`embedding_client`（可空，供守卫读取）+ 新增 `semantic_ready`（向量是否就绪）。
4. **状态值域**：`{mastered, in_progress, unlearned, difficult}` 不变。

---

## 4. 嵌入式存储设计（`backend/app/graph/embedded.py`）

### 4.1 数据模型与落盘

| 数据 | 来源/落盘 | 说明 |
|---|---|---|
| 知识节点 | `data/knowledge_base/nodes/*.json`（只读） | 与 `kb_store` 共享真相源，无需导入 |
| 题目 | `data/knowledge_base/questions/*.json`（只读） | 同上 |
| REQUIRES 边 | 节点 `prerequisites` 派生，内存双索引：`child→parents` 与 `parent→children` | 等价 `(child)-[:REQUIRES]->(parent)`；双索引让「正向查前置」「反向扩散可达」都 O(1) 邻接 |
| HAS_QUESTION | 题目 `source_node_id` 派生 | `(n)-[:HAS_QUESTION]->(q)` |
| BELONGS_TO | 节点 `category` 派生 | `(n)-[:BELONGS_TO]->(:Category{name})` |
| mastery_status | `data/local/mastery_status.json` | 原 Neo4j 属性迁移 |
| 项目图谱/风险/RELATED_TO | `data/local/projects/<project_id>.json` | `params/external_calls` 保持 JSON 字符串序列化 |
| 向量 | `data/local/embeddings.json` | 见 §4.4 |

- 只读资源与可变数据分离：`knowledge_base` 随包只读分发，`data/local` 首启自动创建。
- **原子写**：临时文件 + `os.replace`（先生成临时文件全量写、成功后原子替换），保住 B3「写入不半残」事务语义；写失败不删旧文件。
- **并发**：单进程 sidecar，per-file `threading.Lock`（沿用 `kb_store` 模式），跨文件并行。
- **数据加载**：启动时惰性一次性载入（1.7MB 全量进内存 < 1s），后续查询零 IO；项目图按 `project_id` 读时 parse（懒加载），不在内存常驻。

### 4.2 方法映射表（25+ 方法 → Python 实现，标注真实调用方）

| 类别 | 方法 | 调用方（已核实） | 嵌入式实现 |
|---|---|---|---|
| 基础查询 | `get_node` | graph API、8 个 Agent、kb API、quality_judge/regen | dict O(1) |
| 基础查询 | `get_by_category` / `get_by_difficulty` / `get_by_tags` | graph API; `diagnostics.assemble_learning_path`、`domain_bootstrap` 兜底 | 内存过滤 + 难度排序（契约：全量返回或 limit 截断） |
| 图遍历 | `get_prerequisites` / `get_dependents` | graph API、`content_generator`、`report_builder`、`graph_controller` | 邻接表 O(边数) |
| 图遍历 | `get_reachable(known_ids, max_depth=3)` | `hybrid_retrieve` | **反向 BFS**（沿 parent→children），逐层记录距离，首达即最短 |
| 题目 | `get_questions` / `get_questions_for_nodes` / `get_question` / `get_questions_by_node` | `diagnostics` 抽题（`BANK_TYPES` 过滤 + 每节点配额）、kb API | 读 `kb_store` + 内存过滤/排序；每节点配额用按类型过滤→难度排序→slice |
| 题目 | `upsert_question` / `delete_question` | kb API（JSON 先写已存在） | `kb_store.save_question/delete_question` |
| 路径 | `assemble_learning_path` | graph API、`graph_controller`、`diagnostics` | Python 逐段复刻：零基础入口→BFS 分层（min distance 用 BFS 天然成立）→难度升序→`difficulty_cap=min(5,max(1,level+2))`→弱项补丁 `_WEAK_PATCH_LIMIT=8`（前置入路径→弱项本身入路径）→`max_nodes` 截断 |
| 检索 | `semantic_search` | graph API、`code_reviewer`、`code_tester`、`domain_bootstrap` | numpy 余弦（1536 维 × 300 节点 ≈ 0.4M ops，< 5ms）；向量无 → `[]` |
| 检索 | `hybrid_retrieve` | graph API | 图遍历候选 ∪ 语义候选 → 去重 → `(难度 asc, -_score desc)` → 排除 known → top_k |
| 项目图 | `write_project_graph` / `get_project_graph` / `delete_project_graph` | `project.py`（解析落库）、`project_analyzer` | 本地 JSON 原子替换；`parsed_at` 时间戳、三批 label（Module/Class/Function）、CONTAINS/CALLS/INHERITS、params/external_calls 序列化形状不变；`get_project_graph` 归一 G6 结构（`{project_id,nodes,edges}`）与原实现逐字段对齐 |
| 项目图 | `annotate_risk` / `link_entity_to_knowledge` | `code_tester` 失败用例聚合 | 写回 project JSON（`risk_level/risk_reason/risk_annotated_at`；`related_to` 列表） |
| KB 同步 | `upsert_knowledge_node` / `delete_knowledge_node` | kb API、`domain_bootstrap` | JSON 即库 → `kb_store.save_node/delete_node`（幂等保留）；Neo4j 支路同步 no-op |
| 向量 | `generate_embeddings` | kb API（单节点）、`domain_bootstrap`（批量 ≤20） | 调云端 embedding API → 写 `embeddings.json`（追加合并，幂等） |
| 状态 | `update_node_status` / `get_node_status` | graph API、`graph_controller` | `data/local/mastery_status.json` |
| 生命周期 | `test_connection` / `close` | `main.py` lifespan | `test_connection` 恒 `True`（本地就绪）；`close` no-op |

### 4.3 既有契约保持项（评审重点）

| 契约 | 现状 | 嵌入式要求 | 处理 |
|---|---|---|---|
| `kg.embedding_client` 属性守卫 | `graph.py:108`、`domain_bootstrap:202/219` 读它判语义可用 | 属性必须存在且语义一致 | 嵌入式暴露 `embedding_client`（配置的 API client 或 None）；`graph.py:108` 改一行 `if not kg.semantic_ready:`（语义 = 向量已就绪 或 可回填），domain_bootstrap 的守卫保持（读属性不崩） |
| 503 语义 | 无 kg / 无语义 → 503 | 嵌入式下 kg 恒就绪 → 503 面大幅收窄，**只保留真实的不可用**（LLM 未配、语义不可用） | 正向改善，不回归 |
| `test_connection` | Neo4j 通断 | 恒 True | `main.py` health 增加 `graph_store` / `data_source` 字段，替代「neo4j: connected/unavailable」 |
| workflow 编译 | 仅 kg 就绪才编译 → Neo4j 没起则诊断 503 | kg 恒就绪 → **workflow 恒编译** | 正向改善：端用户首次打开即全功能可用 |

### 4.4 向量语义检索：自动回填 + 降级（已定策，细化时序）

```
启动
 ├─ 读 data/local/embeddings.json
 │    ├─ 存在且覆盖全部节点 → semantic_ready=True（离线也可语义搜索）
 │    └─ 缺/部分 → 视为需回填
 └─ 需回填 且 embedding API 有效
      └─ 后台线程：读全部节点 → 批量(batch≤20)调 API → 写 embeddings.json（原子替换）
           ├─ 成功 → semantic_ready=True（后台就绪，无需重启）
           └─ 失败/取消 → 记日志，semantic_ready=False（降级纯图，主流程不受影响）
      无 key/离线 → semantic_ready=False（纯图降级，行为与现状 503 一致）
```

- **不阻塞启动**：回填线程 daemon，不参与 uvicorn 就绪门。
- **守卫统一**：`semantic_ready` 一个信号源，`graph.py` 守卫、Agent 侧 `semantic_search` 内部 `[]` 双保险。
- **可选增强**：开发/演示态导出 Neo4j 已有向量为 `embeddings.json` 种子打进安装包 → 端用户首跑即语义可用、零 token。

---

## 5. 功能保全矩阵（逐功能对照，验收依据）

> 原则：任何「当前在 Neo4j 模式下可用的用户功能」，在嵌入式模式下**同行为可用**；有差异的仅限 §5.4，且是正向改善。

### 5.1 用户场景一（无项目技能训练）

| 功能 | 依赖链（已核实调用点） | 嵌入式等价 | 影响 |
|---|---|---|---|
| 学情测评 interactive 三阶段 | `diagnostics`：抽题 `get_questions_for_nodes`（BANK_TYPES + 每节点配额）→ LLM 判分 → 画像 | §4.2 题目族 | 无 |
| 学习路径组装 → 图谱渲染 | `assemble_learning_path` + graph API | §4.2 路径 | 无（算法逐行对齐） |
| 资源生成 → 审核 → 交付 → 反馈 | `content_generator`（`get_prerequisites`）、`reviewer`（`get_node` 校验）、反馈 | §4.2 | 无 |
| M5 质量链路 | `quality_judge`（`get_node`）→ `quality_regen`（`get_node`）→ `quality_metrics` | §4.2 | 无 |
| 动态建域（未收录领域） | `domain_bootstrap`：`semantic_search`/`get_by_difficulty` 就近选点 → `upsert_*` → `generate_embeddings` | §4.2 + §4.4 | 语义可用性取决于向量就绪；建域本身不依赖语义（有 `get_by_difficulty` 兜底） |
| 画像跨次进化 / Runs 复盘 | `profile_store`、`run_store`（纯文件，不碰 Neo4j） | 不动 | 无 |
| 联网搜索 | `search.py`（Tavily），不碰 kg | 不动 | 无 |

### 5.2 用户场景二（有项目二次开发）

| 功能 | 依赖链 | 嵌入式等价 | 影响 |
|---|---|---|---|
| 项目解析 → 项目图谱 | `project_analyzer` → `write_project_graph` → `get_project_graph` | §4.2 项目图族（原子写 + 懒加载） | 无 |
| 代码审查 | `code_reviewer`：`get_node`（语义就近）→ `semantic_search` | §4.2 | 语义不可用时降级纯图（与现状无 key 行为一致） |
| 代码测试 | `code_tester`：`get_node`→`semantic_search`→沙箱→**`annotate_risk` + `link_entity_to_knowledge` 回写** | §4.2 风险标注落回 project JSON | 无 |

### 5.3 全局功能

| 功能 | 依赖 | 影响 |
|---|---|---|
| AI 助手 6 工具（`search_knowledge`/`get_learning_path`/`query_project_graph` 等） | graph API / project API / chat SSE | 无（API 形状不变） |
| 学习会话/图谱视图/项目图谱视图/Dashboard/PathFinder(最短路径) | graph/learning/project API | 无 |
| KB 管理 CRUD（节点+题目，JSON 为源） | `kb.py` 先写 `kb_store` 再 `kg.upsert_*`（Neo4j 同步） | 嵌入式：JSON 即库，同步 no-op，返回形状与警告语义不变 |
| 分阶测试/报告组件 | `learning.py`、`report_builder`（`get_prerequisites`） | 无 |
| 设置页（API/Agent key/厂商/代理） | 纯前端 + `backend-sidecar` env 注入，不碰 kg | 无 |
| 后台任务页 Runs / 重跑 | `run_store` 纯文件 | 无 |

### 5.4 有意的行为差异（全部为正向）

| 差异 | 现状（Neo4j） | 目标（embedded） |
|---|---|---|
| 后端就绪 | Neo4j 未起 → `kg=None` → 图谱/诊断 503，workflow 不编译 | kg 恒就绪 → 全功能默认可用，无「Docker 没开」类报错 |
| 首次启动 | 需 docker pull + 导入 | 装完即用 |
| 语义检索在线与否 | 依赖 Neo4j 向量 + API key | 有缓存向量则离线可用；否则可自动回填或降级纯图 |
| health | `neo4j: connected/unavailable` | `graph_store: embedded` + `data_source` |

---

## 6. 性能设计 — 丝滑流畅不卡顿

### 6.1 目标基准（验收用，量化）

| 指标 | 现状（Neo4j 容器） | 目标（embedded） | 达成手段 |
|---|---|---|---|
| 装后首启 → 后端就绪 | Docker 拉镜像不确定 + Neo4j JVM 10–30s + 导入 | **< 3s** | 无 JVM；JSON 全量载入 <1s；sidecar 顺序：DB 载入 → 启动 uvicorn → 健康门 |
| 后续热启 → 后端就绪 | JVM 冷启动重复 | **< 2s** | 内存载入即用 |
| 图谱/节点查询 API | Cypher + Bolt 往返 ~ms 级 | **< 5ms** 典型 | 进程内 dict/邻接表，无网络往返 |
| `get_reachable` / `assemble_learning_path` | 变长路径 Cypher + 聚合 | **< 5ms** | Python BFS，逐层记录距离（天然等价 Cypher 两次聚合的最短距离） |
| 语义检索（1536 维） | Neo4j 向量索引 + Bolt | **< 5ms** | numpy 余弦 ~300×1536 矩阵运算 |
| 知识图谱视图打开 | 依赖 API 往返 + 渲染 | **无回退** | 数据量不变（≤ 数百节点），G6 已有 rAF 节流 |
| 大项目解析 | 已让主线程 + 过期丢弃（既有优化） | **保持** | 不因迁移回退；嵌入式写库原子替换不再等 Bolt 事务 |
| SSE 对话流式 | 后端逐 token | **保持** | 迁移不触碰 chat/SSE 链路 |
| 内存占用（后端进程） | Neo4j 容器单独 ~1GB+ | **< 100MB** | 1.7MB JSON + 邻接表 + numpy 向量（可选） |

### 6.2 后端性能关键设计

1. **零网络往返**：查询全在进程内，天然消除 Neo4j Bolt 连接池/序列化开销（这是本方案最大的性能红利）。
2. **索引结构**：节点 `dict[id→node]`、`dict[category]`、`dict[difficulty]`、`child→parents` / `parent→children` 双邻接、`node→questions`。查询 O(1)~O(n)，n=222。
3. **惰性加载**：项目图按 `project_id` 读时 parse，不常驻；大项目只在打开对应视图时加载。
4. **向量存储**：numpy 矩阵（node×1536），加载时一次 `np.asarray`；未装 numpy 则纯 Python 余弦（300 节点仍可 < 20ms，可接受降级）。
5. **回填不抢占**：自动回填放 daemon 后台线程 + 低优先级；不阻塞请求线程，不动 uvicorn 事件循环期间的用户请求（FastAPI 同步端点在线程池跑，与 daemon 独立）。
6. **缓存**：请求级结果不做全局缓存（数据小、查询快，避免缓存一致性复杂度）；仅向量与图结构做进程级单例。

### 6.3 前端性能面（既有优化 + 迁移红利）

- **沿用既有 A–G 优化不动**：Monaco 惰性加载、externalChanges 去深、G6 rAF 节流、项目解析主线程外置+过期丢弃、流式去重 Set+窗口上限、Resizable rAF+will-change。
- **迁移红利**：`assemble_learning_path` BFS 更快 → 图谱渲染等待更短；health 恒 ok → StatusBar 不再轮询「Docker 未起」的失败态，避免无效重试噪音。`_get_kg` 503 面收窄 → 前端少处理一类错误分支。

---

## 7. UI/UX 设计规范 — 符合设计师眼光思维

> 目标：本次改造不只「不坏 UI」，而是把「免 Docker」转化为**首启即顺、状态即见、降级不吓人**的设计；并对既有 IDE 做一次设计师视角的规范审计。

### 7.1 设计原则（评审杠杆，全部可核查）

1. **少即是多（Restraint）**：不做新花活，聚焦消除"被 Docker 打扰"的噪音 UI。首启引导 < 3 屏，默认一键「开始学习」。
2. **层级清晰（Hierarchy）**：一屏一主操作；状态区（StatusBar）、导航区（NavSidebar）、主区（MainArea）视觉权重回归主区。
3. **一致（Consistency）**：沿用 Element Plus 设计语言 token（间距/圆角/阴影/字号），不引入第二套视觉系统；深浅主题一套 token 双主题映射。
4. **状态可见（Visibility of system status）**：后端/存储/语义检索三级状态在 StatusBar 以「色点 + 文案」见即所得，不藏不糊。
5. **容错（Forgiveness）**：语义检索不可用时给「纯图模式已生效，功能不影响」的温和提示，而非裸 503 错误码。
6. **动效克制（Motion with purpose）**：动效只服务状态变化（出现/消失/加载），时长 150–250ms，默认 ease，无装饰性动画。
7. **可访问（Accessible）**：对比度 ≥ WCAG AA；焦点态可见；键盘可达所有导航与主操作。

### 7.2 本次改造的 UI 触点（新增/改动，范围小）

| 触点 | 设计内容 | 设计师要点 |
|---|---|---|
| **首启引导（First Run）** | 装后首次打开：< 3 屏 → ①欢迎+一键开始 ②（仅当需要）设置 LLM key ③完成。不再出现「请用 Docker 启动 Neo4j」 | 3 屏覆盖数量、每屏一主操作、进度点、可跳过、「开始」CTA 在第三屏右侧开幕（Button 布局黄金位） |
| **StatusBar 存储/检索状态** | 后端：绿点「后端已就绪」；存储：`嵌入式存储`；语义：绿点「语义检索可用」/ 琥珀「纯图模式」+ tooltip 说明 | 色点统一 8px 半径同色阶；文案用已就绪/降级二分，避免漏洞词；hover 给 tooltip 不给跳转 |
| **语义检索降级 UX** | `graph.py` 守卫返回 503 时 → 前端图谱页显示内联「语义检索暂不可用，已为你切到图谱精准检索」banner；设置页给「启用自动回填」开关 | 用「已为你降级」而非「报错」；banner 可关闭、不打断主流程 |
| **设置页** | 「知识图谱存储」段：只读展示 `嵌入式存储`（端用户无从配置，防误改）；「语义检索」开关 + 回填进度 | 只读字段用禁用态 + 说明文案，不给让用户自己选的暴露感 |
| **加载/空状态** | 图谱视图 loading 骨架屏（G6 节点占位）；空项目/无弱项空状态插画文案 | 骨架屏与最终布局同构（Skeleton 预占位，杜绝跳动/位移） |

### 7.3 既有 IDE 设计规范审计（Audit-first，不动则核）

| 组件 | 审计项 |
|---|---|
| NavSidebar | 图标 16–20px 统一、激活态 2px 左条 + 明暗对比 ≥3:1、宽度 48/56/64 一档 |
| MainArea | 视图切换无硬切跳变（给容器 fade 150ms）；分栏拖拽已有 rAF，拖拽柄 hover 高亮 |
| AssistantPanel | 对话气泡最大宽 760px 居中；输入框 focus 环清晰；工具/审批门用 Element 风格而非裸 alert |
| Monaco | 沿用默认配色映射到主题 token；行高/字号与既有设置一致 |
| StatusBar | 三个状态区对齐基线，色彩语义：绿=正常 / 琥珀=降级 / 红=故障 |
| 深浅主题 | 新触点全部经 `theme.js` token 映射，禁止写死色值；对比度两主题都过 AA |

### 7.4 设计 token 建议（基线，覆盖新触点）

| Token | 建议 | 说明 |
|---|---|---|
| 半径 | 控制 6px / 卡片 8px / 弹窗 10px | 与 Element Plus 一致 |
| 主色 | 沿用现状 branding accent（图谱蓝/学习绿二选一，不新增） | 保持一致 |
| 间距 | 4 网格：8/12/16/24/32 | 对齐栅格 |
| 动效 | 150ms（hover/焦点）/ 220ms（面板展开）/ ease-out | 状态变化专用 |
| 字体 | 12/13/14px 三段，代码区等宽 | 不新增字体族 |
| 色板 | 状态色统一：`#22c55e`正常/`#f59e0b`降级/`#ef4444`故障 + 对应暗色变体 | 同上 |

> 本节约束的是**新触点与审计项**；任何超出清单的重设计需另开「视觉迭代」issue，防止与迁移混为一谈（对应"UI 内容符合设计师眼光"的承诺：迁移不改坏视觉，新视觉有规范可依）。

---

## 8. 影响面清单

**新增**
- `backend/app/graph/embedded.py`（约 500–700 行）
- `backend/app/graph/base.py`（可选接口，纯文档性）
- `backend/tests/test_engine_embedded.py`（约 150–250 行）
- `docs/架构与设计/轻量化改造方案_免Docker_嵌入式存储.md`（本文件）

**修改**
- `backend/app/config.py`：加 `GRAPH_STORE`
- `backend/app/main.py`：lifespan 实例化 + health 字段（`graph_store` / `data_source`）
- `backend/run_server.py`：frozen 时置 `GRAPH_STORE=embedded`
- `backend/app/api/graph.py`：`:108` 语义守卫从 `embedding_client` 改一行 `semantic_ready`（**唯一 1 行契约改动**）

**不改**：`frontend/`、`electron/`、7 个 Agent、`sandbox.py`、`kb.py` 主体、现有 700+ 后端测试（直接构造 `KnowledgeGraph()` 走 neo4j 支路，零改动）。

---

## 9. 测试与验收

### 9.1 新增单测（`test_engine_embedded.py`）

| 组 | 用例 |
|---|---|
| 查询等价 | `get_node/get_by_category/get_by_difficulty/get_by_tags` 与已知结果一致 |
| 遍历 | `get_prerequisites/get_dependents/get_reachable` 深度语义（含多入口、环防御） |
| 路径 | 零基础入口、BFS 分层最短距离、弱项补丁（`_WEAK_PATCH_LIMIT=8`）、`difficulty_cap` 边界、`max_nodes` 截断 |
| 项目图 | 幂等重写不残留、`get/delete`、风险标注 + RELATED_TO 落回、原子写（注入写入失败不产生半残） |
| 状态 | `update/get` 写盘→重载→读回一致 |
| 向量 | `embeddings.json` 载入、numpy 余弦 top_k 正确、缺失降级 `[]` |
| 契约 | `embedding_client` 属性存在、`semantic_ready` 三态（就绪/可回填/降级） |

### 9.2 等价性胶水（可选，Neo4j 不可用自动 skip）

同一 `data/knowledge_base` 下，嵌入式 vs Neo4j 对 `assemble_learning_path` / `hybrid_retrieve` / 题目配额做结果一致性抽验——**专治「Cypher 与 Python 细节分叉」**。

### 9.3 性能验收基准（对 §6.1 逐项打点）

打包后实测：后端就绪 <3s、节点查询 <5ms、路径组装 <5ms、语义 <5ms、内存 <100MB。超阈值则回查索引/加载。

### 9.4 全量验收标准

1. 现有测试全绿（前端 434 + 后端 242+）。
2. 嵌入式单测全绿。
3. 无 Docker 环境手动回归：装包→双击→首启引导→学情测评→图谱→答题→项目解析→代码审查全流程可用。
4. StatusBar 三态与语义降级 banner 表现符合 §7。
5. 性能基准达标（§9.3）。

---

## 10. 打包与环境

- electron-builder extraResources 已含 `resources/data`（`run_server.py` 的 `KMATCH_DATA_DIR` 指向），嵌入式沿用，不改打包配置。
- 打包态自动 `GRAPH_STORE=embedded`；README「首次使用」改为开箱即用，Neo4j 列为可选演示后端。
- 安装包体量不增反减；无新增运行时依赖（numpy 可选）。

---

## 11. 风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| 语义检索离线不可用 | 语义召回退化图检索 | 自动回填 + 降级（§4.4/§7.2 优雅兜底） |
| 现有测试回归 | 700+ 测试 | 独立类 + 显式开关，默认 neo4j 支路零改动 |
| Cypher/Python 细节分叉 | 排序/补丁/配额不一致 | 逐方法等价表（§4.2）+ 等价性胶水（§9.2） |
| 旧 Neo4j 用户数据不迁移 | 项目图/状态/向量 | 可重解析/重置/回填；可选种子向量导出；产品处早期分发阶段 |
| 大项目图内存 | 打开慢 | 懒加载 + 读时 parse（§6.2.3） |
| M5 口径漂移 | 赛题指标 | 常量与算法逐行对齐 + 抽查（§0/§4.2） |
| UI 视觉回退 | 新触点破坏主题 | §7 全 token 经 `theme.js`，禁止写死色值；新旧触点隔离验收 |
| 回填占资源 | 首启卡顿 | daemon + 低优先级 + 不阻塞就绪门（§6.2.5） |

---

## 12. 落地步骤（细化，含保全验证与性能打点）

- **P0 铺垫**：`config.GRAPH_STORE` + 接口 + 测试骨架 + health 字段设计。
- **P1 只读核心**：节点/题目/遍历（§4.2 前 3 类）→ **保全验证点①：graph API 全部路由同一 data 下行为一致**。
- **P2 路径组装**：`assemble_learning_path` + 弱项补丁 + hybrid 图侧 → **验证点②：等价性胶水 + M5 抽查**。
- **P3 可变数据**：项目图/状态/风险/KB 同步（原子写）→ **验证点③：场景二全链路回归**。
- **P4 向量**：embeddings 载入 + numpy 余弦 + 回填 daemon + `semantic_ready` 接线 → **验证点④：语义三态 + 降级 UX**。
- **P5 接线收尾**：main.py + graph.py 1 行守卫 + run_server + 首启引导/StatusBar/settings 触点的前端小改 + 性能基准 + 文档 + 全量回归 → **验证点⑤：无 Docker 全流程 + §9.3 基准**。

> 实施起记 **ADR-0008**：存储后端策略（默认 embedded，Neo4j 可选），沿用 0006 四段式。

---

## 13. 一句话结论

Neo4j 只是 1.7MB JSON 的派生缓存，却是端用户开 Docker 的唯一理由；用**进程内嵌入式存储**替换它为安装包默认后端（保留 Neo4j 可选），可做到**开箱即用、秒开不卡、体积不增、前端与 700+ 测试零改动**；功能按 §5 矩阵逐项保全，性能按 §6 基准验收，UI 新触点按 §7 规范落地——唯一 1 行契约改动在 `graph.py:108` 的语义守卫。
