# ADR-0008: 图存储后端策略 — 默认嵌入式，Neo4j 可选

- 状态：Accepted
- 日期：2026-08-19
- 关联：issue #50–#56，方案 `docs/架构与设计/轻量化改造方案_免Docker_嵌入式存储.md`
- 版本：1.0.0

## 背景

安装包已做到 Electron 自启 FastAPI sidecar（PyInstaller），但 **Neo4j 仍要求端用户 `docker-compose up -d` + 手动导入**，是上手唯一硬门槛。审计结论：Neo4j 是端用户开 Docker 的唯一理由，而它只是 1.7MB JSON 的派生缓存（`kb_store.py` 明确"JSON 为源，Neo4j 派生缓存"）；沙箱本就有无 Docker 降级；compose 里的 `apoc` 插件从未被调用。用户诉求：端用户使用应用不要开 Docker，且功能不受影响、体验丝滑。

## 决策

- 新增 `EmbeddedGraphStore`（`backend/app/graph/embedded.py`）：以 `data/knowledge_base` JSON 为真相源，进程内载入节点/题目/邻接表，查询零网络往返；可变数据（项目图谱 / 掌握状态 / 风险标注 / 向量）落 `data/local/`，原子写（临时文件 + `os.replace`）+ per-file 锁。
- 图存储后端由 `GRAPH_STORE=neo4j|embedded|auto` 选择：
  - `embedded`：安装包端用户默认（`run_server.py` 在 PyInstaller frozen 态 `setdefault` 强制，零配置）。
  - `neo4j`：**开发/测试默认**（当前 `config.py` 默认值，保证现有 700+ 测试零行为漂移——大量集成测试直接 `TestClient(main.app)` 跑 lifespan）。
  - `auto`：探测 Neo4j 可达用 neo4j，否则 embedded（零配置开发，未设为默认是为避免测试漂移）。
- 方法签名 / 返回值形状 / `embedding_client` 属性 / `semantic_ready` 属性与 Neo4j 后端完全一致（契约保持项）。`graph.py` 语义守卫由 `embedding_client` 字段切到 `semantic_ready`（唯一 1 行契约改动）。
- 向量语义检索：本地缓存向量（`data/local/embeddings.json`）+ 无矩阵且配了 embedding key 时后台 daemon 自动回填；无客户端 / 无向量降级纯图。**诚实语义**：每次查询仍需云端 embedding 编码 query，故无客户端时即使有缓存向量也不提供检索（与 Neo4j 后端一致）。
- 前端仅 StatusBar 增加「本地存储 / 纯图模式」状态点，Docker 引导弹层在嵌入式下自动隐藏，无视觉回退。

## 理由

- 端用户零 Docker / 零 JVM / 零端口：安装包体积不增，冷启动秒级（去 JVM 10–30s）。
- 数据形态（222 节点 / 648 题 / 每用户项目图）完全适配进程内存储；BFS 等价 Cypher 变长路径，最短距离天然成立。
- 保留 Neo4j 后端保赛题技术栈呈现与 dev 演示体验；`GRAPH_STORE=embedded` 是安装包侧能力，不影响 `docker-compose up -d neo4j` 老流程。
- 诚实的 `semantic_ready` 三态避免"离线声称可用"的过度承诺。

## 后果

- 新增：`backend/app/graph/embedded.py`（~700 行）、`backend/tests/test_engine_embedded.py`（14 测）。
- 修改：`config.py`（GRAPH_STORE）、`main.py`（lifespan 建 store + health 字段 `graph_store`/`semantic_search`）、`run_server.py`（frozen → embedded）、`graph.py:108`（语义守卫 1 行）、`frontend/src/stores/backendHealth.js` + `StatusBar.vue`（状态点）。
- 测试：后端 651（含嵌入式 14）全绿，前端 434 全绿；等价性胶水测试待 Neo4j 环境可选补。
- 行为差异（均为正向）：嵌入式下 kg 恒就绪 → 多 Agent workflow 恒编译，原"Neo4j 未起即 503"面大幅收窄；health 新增 `graph_store`/`semantic_search` 字段。
- 已知边界：语义检索需云端 embedding（query 编码）；旧 Neo4j 上的项目图/状态数据不自动迁移（可重新解析 / 重置 / 回填）。
