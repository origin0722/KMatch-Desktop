# A 端后端对接文档（W2-W4）

> **面向**: B（前端）、C（数据）端协作者
> **更新**: 2026-06-18（第4周 content_generator 接入后）
> **目的**: 让 B/C 端对接后端 API、理解 Agent 间数据契约，无需读后端源码

---

## 一、后端服务概览

| 项 | 值 |
|:---|:---|
| 框架 | FastAPI ≥0.137 |
| 入口 | `http://localhost:8000` |
| API 文档 | `http://localhost:8000/api/docs`（Swagger）|
| 健康检查 | `GET /api/health`（含 Neo4j / LLM 连通性）|
| 全局单例 | lifespan 启动时创建 KG + OpenAI + Workflow 单例，路由共享 |

**启动依赖**：Neo4j 5.x（7474/7687）+ LLM API（DeepSeek）+ Embedding API（千问）。
任一未就绪不阻塞启动，对应路由返回 503 或降级。

---

## 二、多 Agent 工作流（无项目场景全流程）

```
diagnostics ──→ reviewer ──┬─(画像通过)→ graph_controller ──→ content_generator ──→ reviewer ──┬─(内容通过)→ finish
  学情检测      画像审核   │                              组装路径          生成资源     内容审核   │
                            ├─(不通过&未超限)→ diagnostics 打回                                      ├─(不通过&未超限)→ content_generator 打回
                            └─(超限)→ finish 降级                                                    └─(超限)→ finish 降级
```

**关键设计**：
- `reviewer` 是**双模式**节点：state 无 `generated_content.resources`（或为空列表）时审画像；有非空 resources 时审生成内容（BUG-016 审核对象迁移）。同一节点复用。
- 打回目标由"是否进入内容阶段"决定：画像阶段打回 `diagnostics`，内容阶段打回 `content_generator`。
- 阈值 `REVIEW_PASS_THRESHOLD=0.85`，`max_retries` 默认 3（请求可配 1-5）。
- ⚠️ **retry 预算跨阶段共享**：画像审核与内容审核共用同一个 `retry_count`，总计不超过 `max_retries` 次。即画像打回 2 次后，内容阶段只剩 1 次预算。这是当前实现，B 端展示重试进度时注意。
- 超限降级：返回最终状态，`review_results.verdict="reject"`，标记待人工审核。

---

## 三、API 契约

### 3.1 学情测评 — assess

**`POST /api/diagnostics/assess`** — 按 `mode` 分流

**请求体**:
```json
{
  "target_direction": "Python 基础语法入门",
  "mode": "demo",
  "known_topics": [],
  "scene": "no_project",
  "max_retries": 3
}
```
- `mode`:
  - `demo`（默认）= LLM 自动作答跑通完整工作流（学情检测→画像审核→图谱→生成→内容审核），返回完整 `AssessResponse`。推荐联调/演示用。
  - `interactive` = **仅出题**，不走工作流。返回 `InteractiveAssessResponse`（只有 `session_id` + `assessment.questions`）。前端答题后调 `POST /submit` 判分（见 §3.3）。
- `known_topics`: 用户自报已学节点 `[{node_id, mastery}]`，可空

**demo 模式响应** `AssessResponse`:
```json
{
  "session_id": "uuid",
  "profile": { /* 用户画像 v3，见 §4.1 */ },
  "review_results": { /* 审核报告，见 §4.2 */ },
  "assessment": { /* 测评明细，见 §4.3 */ },
  "knowledge_graph": { /* 学习路径，见 §4.4；画像未通过/未进入内容阶段时为 {} */ },
  "generated_content": { /* 学习资源，见 §4.5；画像未通过时为 {}；内容审核失败时仍含已生成的(被拒)资源 */ },
  "orchestration_log": ["[时间] 🔧 学情检测: 开始 ...", ...]
}
```

**interactive 模式响应**（同样返回 `AssessResponse`，仅 `session_id` + `assessment` 填充，其余为空）:
```json
{
  "session_id": "uuid",
  "profile": {},
  "review_results": {},
  "assessment": {
    "questions": [ /* 见 §4.3 questions 结构，前端逐题作答 */ ],
    "answers": [],
    "per_node": {},
    "correct_count": 0,
    "total_count": 10
  },
  "knowledge_graph": {},
  "generated_content": {},
  "orchestration_log": []
}
```
> demo 与 interactive 共用 `AssessResponse` 结构（单一响应类型，OpenAPI schema 准确）。B 端据 `assessment.answers` 是否为空判阶段：出题阶段 `answers=[]`，提交后（submit 响应）含判分。
> ⚠️ **出题阶段 `questions` 不含 `answer` 字段**（防正确答案提前泄露，BUG-033）。submit 响应的 questions 才含 `answer` 供复盘。
> interactive 模式题目缓存到后端内存（按 `session_id`，上限 100 条 LRU）。B 端需保存 `session_id` 供 submit 使用。

> **降级约定**：demo 模式任一阶段失败/降级时，对应字段为空对象 `{}` 或内层数组为 `[]`，不会缺失 key。判空方式见 §6.5（注意 `knowledge_graph`/`generated_content` 顶层对象始终含固定 key，需判内层数组长度）。

### 3.2 知识图谱查询 API（`/api/graph`，B 端 W3 图谱组件对接）

| 方法 | 路径 | 参数 | 说明 |
|:---|:---|:---|:---|
| GET | `/node/{node_id}` | — | 按节点 ID 查询，404 不存在 |
| GET | `/category/{category}` | — | 按分类（基础语法/面向对象编程/...）|
| GET | `/difficulty` | `?min_d=1&max_d=5` | 按难度区间 |
| GET | `/tags` | `?tags=基础语法,循环` | 按标签（任一命中）|
| GET | `/prerequisites/{node_id}` | — | 前置依赖节点 |
| GET | `/dependents/{node_id}` | — | 依赖该节点的后继 |
| GET | `/search` | `?q=&top_k=5&difficulty_max=` | 语义向量检索（embedding 未配→503）|
| POST | `/hybrid` | body: `{known_ids,weak_ids,level,top_k}` | 图遍历+向量混合检索 |
| POST | `/path` | body: `{known_ids,weak_ids,level,max_nodes}` | 组装学习路径 |
| PUT | `/status/{node_id}` | body: `{status}` | 更新节点状态 |

**节点状态合法值**: `mastered` / `in_progress` / `unlearned` / `difficult`

**节点对象结构**（GET 返回，已统一 `id`→`node_id`）:
```json
{
  "node_id": "PY-005",
  "name": "循环结构",
  "category": "基础语法",
  "difficulty": 2,
  "tags": ["循环", "控制流"],
  "summary": "...",
  "key_points": ["for 循环", "while 循环"],
  "prerequisites": ["PY-001"],
  "estimated_minutes": 60,
  "practice_questions": [...]
}
```

> ⚠️ **`common_mistakes` 字段当前未填充**：prompt 04/05 与 content_generator 代码引用了 `common_mistakes`，但 92 个知识节点 JSON 与 schema.json 均未定义此字段（C 端待补）。运行时 `GET /node/{id}` 返回的节点**不含** `common_mistakes`，B 端访问需用 `node.common_mistakes ?? []` 兜底。content_generator 已用 `.get(..., [])` 安全降级。

**查询类响应结构**：

| 端点 | 响应结构 |
|:---|:---|
| `/node/{id}` | 节点对象（404 不存在）|
| `/category` `/difficulty` `/tags` `/prerequisites` `/dependents` | `[节点对象, ...]`（数组）|
| `/search` | `{"query": str, "count": int, "nodes": [节点对象]}`（节点含 `_similarity`）|
| `/hybrid` | `{"count": int, "nodes": [节点对象]}`（节点含 `_source`/`_score`）|
| `/path` | `{"path_length": int, "estimated_total_hours": float, "nodes": [节点对象]}` |
| `/status/{id}` | `{"node_id": str, "status": str, "updated": true}` |

> ⚠️ **`/path` 返回键是 `nodes`**，与 `/assess` 响应里 `knowledge_graph.learning_path` 的键名不同（后者是 `learning_path`）。B 端注意区分。

**错误码**：503=引擎未就绪，404=节点不存在，400=参数非法。

### 3.3 答题提交 — submit（interactive 模式判分）

**`POST /api/diagnostics/submit`** — 提交 interactive 模式答题，判分 + 画像 + 动态反馈

**请求体** `SubmitRequest`:
```json
{
  "session_id": "assess(interactive) 返回的 session_id",
  "answers": ["A", "对", "B", ...]
}
```
- `answers`: 逐题作答，**顺序与 questions 一致**；选择题给选项内容或字母（如 `"A"`），判断题给 `"对"`/`"错"`
- 答案数 ≠ 题数时自动对齐（缺失补空串判错，多余截断）

**响应体** `SubmitResponse`:
```json
{
  "session_id": "uuid",
  "profile": { /* 用户画像 v3，见 §4.1 */ },
  "assessment": {
    "questions": [...],
    "answers": ["A", "对", ...],
    "per_node": { "PY-005": [{"question_index": 0, "correct": true}, ...] },
    "correct_count": 7,
    "total_count": 10
  },
  "feedback": {
    "strategy": "advance|remediate|scaffold",
    "accuracy": 0.7,
    "description": "..."
  }
}
```

**动态反馈策略** `feedback.strategy`（对齐 orchestrator prompt 规则2）：

| 正确率 | strategy | 含义 |
|:---|:---|:---|
| ≥ 0.8 | `advance` | 掌握良好，进入下一节点或生成进阶挑战 |
| 0.5 ~ 0.8 | `remediate` | 部分掌握，触发降维解释（换角度重讲）|
| < 0.5 | `scaffold` | 掌握不足，标记困难节点，补充前置基础知识 |

**错误码**：404=session 不存在或已过期（缓存上限 100 条 LRU），503=引擎未就绪，500=判分失败。

> interactive 流程不经过 reviewer 审核（用户已亲自答题，画像由真实作答产出，无需审画像合理性）。如需对生成内容审核，可后续用 demo 模式或单独触发。

### 3.4 动态反馈内容再生 — feedback（W5 闭环）

**`POST /api/diagnostics/feedback`** — 按 `submit` 返回的 `feedback.strategy` 针对性再生学习内容

**请求体** `FeedbackRequest`:
```json
{
  "session_id": "assess(interactive) 返回的 session_id",
  "strategy": "remediate",
  "profile": { /* submit 返回的画像，含 weak_topics/theory_level */ }
}
```

**响应体** `FeedbackResponse`:
```json
{
  "session_id": "uuid",
  "strategy": "remediate",
  "resources": [
    {
      "content_type": "lecture",
      "target_node_id": "PY-005",
      "source_nodes": ["PY-005.key_points[0]", "PY-005.summary"],
      "content": "markdown 正文 (降维讲解/补基础/进阶题)",
      "generated_at": "2026-06-18T...Z"
    }
  ],
  "node_count": 1
}
```

**策略→内容映射**（对齐 §3.3 feedback.strategy）：

| strategy | 再生内容 | 目标节点 |
|:---|:---|:---|
| `remediate` | 降维讲义（换角度/类比重讲）| 弱项节点本身 |
| `scaffold` | 入门讲义（补前置基础）| 弱项节点的前置依赖节点 |
| `advance` | 进阶挑战题（跨知识点推理）| 学习路径中弱项之后的下一节点 |

> `resources` 元素结构与 `generated_content.resources` 一致（见 §4.5），`content` 为 markdown。无目标节点（如弱项不在路径中、scaffold 无前置）时 `resources=[]`、`node_count=0`，不报错。

**错误码**：422=无效 strategy（Pydantic Literal 校验），404=session 不存在，503=LLM 未配置，500=再生失败。

**W5 完整三步流程**：
```
1. POST /assess (mode=interactive) → session_id + questions
2. POST /submit ({session_id, answers}) → profile + assessment(判分) + feedback.strategy
3. POST /feedback ({session_id, strategy, profile}) → 针对性再生内容 resources
```

---

## 四、数据契约（Agent 间 + API 响应字段）

### 4.1 `profile`（用户画像 v3）

对齐 `data/user_profiles/profile_schema.json`。关键字段：

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| `profile_id` | str | `UP-DIA-{hex6}` |
| `theory_level` | int 1-5 | 理论水平 |
| `practical_level` | int 1-5 | 实操水平（W4 暂固定 1）|
| `learning_style` | str | VARK（W5 暂固定 read_write）|
| `known_topics` | list | `[{node_id, mastery, last_test_score}]` |
| `weak_topics` | list | `[{node_id, mastery, error_patterns}]` |
| `weakness_areas` | list[str] | 弱项自然语言描述 |
| `recommended_path` | **object** | `{current_node, next_nodes[], estimated_completion_weeks}` |

> ⚠️ `recommended_path` 是**对象**（非旧的 `recommended_start_node` 字符串，BUG-025 已统一）。B 端画路径组件按 `profile.recommended_path.current_node` 取值。

### 4.2 `review_results`（审核报告）

```json
{
  "passed": true,
  "overall_score": 0.92,
  "threshold": 0.85,
  "dimensions": {
    "factual_accuracy": {"score": 0.95, "issues": []},
    "hallucination": {"score": 0.90, "issues": []},
    "logic_consistency": {"score": 0.90, "issues": []},
    "teaching_appropriateness": {"score": 0.85, "issues": []}
  },
  "verdict": "pass",
  "retry_hint": "",
  "reviewed_at": "2026-06-18T...Z"
}
```
- `issues` 元素: 硬规则产出 `{severity, dimension, problem, source_node}`；LLM 产出 `{severity, problem, source_node}`。`location`/`suggestion` 当前代码不产出（prompt 设计字段，保留预留）。
- `dimensions` 始终返回四维度（含空画像/异常降级场景），B 端可安全访问 `dimensions.<维度>.score`，不会缺失 key。空画像降级时四维度满分但 `overall_score=0`、`passed=false`。

### 4.3 `assessment`（测评明细）

```json
{
  "questions": [{"type":"choice","node_id":"PY-005","question":"...","options":[...],"answer":"A","difficulty":2}],
  "answers": ["A", "错", ...],
  "per_node": {
    "PY-005": [{"question_index": 0, "correct": true}, {"question_index": 1, "correct": false}]
  },
  "correct_count": 7,
  "total_count": 10
}
```
> ⚠️ `per_node[node_id]` 元素是**对象** `[{question_index, correct}]`（非旧的 `[bool]`，BUG-022）。B 端 `nodeCorrect` 用 `filter(g => g && g.correct === true)`。

### 4.4 `knowledge_graph`（学习路径，W3）

```json
{
  "learning_path": [ /* 节点对象列表，按依赖拓扑+难度排序，已剥离 _source/_score */ ],
  "path_node_ids": ["PY-005", "PY-008", ...],
  "estimated_total_hours": 2.5,
  "node_status_updates": {"PY-005": "difficult", "PY-008": "in_progress"},
  "assembled_at": "2026-06-18T...Z"
}
```

### 4.5 `generated_content`（学习资源，W4）

```json
{
  "resources": [
    {
      "content_type": "lecture",          // lecture | practice_guide | test
      "target_node_id": "PY-005",
      "difficulty_level": 2,
      "adaptation_profile": "beginner",   // beginner | intermediate | advanced
      "source_nodes": ["PY-005.key_points[0]", "PY-005.summary"],  // 溯源标记
      "content": "# 循环\n\nfor 循环用于遍历...",  // markdown 正文
      "generated_at": "2026-06-18T...Z"
    }
    // ... 每节点 3 种资源 (lecture/practice_guide/test)
  ],
  "node_count": 3,                         // 实际生成覆盖的节点数 (≤3)
  "content_types": ["lecture", "practice_guide", "test"],
  "generated_at": "2026-06-18T...Z"
}
```

**生成范围**：默认对学习路径**前 3 个节点**各生成 3 种资源（控量，避免全路径 LLM 调用过久）。`MAX_NODES_TO_GENERATE=3` 可调。

**溯源标记**：每段 `source_nodes` 引用图谱节点，格式 `PY-xxx.key_points[0]` / `PY-xxx.summary`。reviewer 内容模式硬规则会校验这些引用的真实性。

---

## 五、状态码与降级矩阵

| 场景 | HTTP | 表现 |
|:---|:---|:---|
| Neo4j 未连接 | 503 | `detail: "知识图谱引擎未就绪（Neo4j 未连接）"` |
| LLM 未配置（sk-placeholder）| 200 | demo 模式降级：`profile={}`，`review_results.passed=false`，`retry_hint` 含"LLM 未配置"；详细原因见 `orchestration_log` |
| Embedding 未配置 — `/search` | 503 | `detail: "语义检索不可用（Embedding 客户端未配置）"` |
| Embedding 未配置 — `/assess` | 200 | 工作流正常跑通，`hybrid_retrieve` 降级纯图模式（不影响 assess 主流程）|
| 工作流异常 | 500 | `detail: "测评流程执行失败: ..."` |
| 审核超 max_retries | 200 | `review_results.passed=false, verdict=reject`，标记待人工审核 |

---

## 六、B 端对接要点（W3-W5）

1. **W3 图谱页**：`GET /api/graph/node/{id}` 等查节点；`POST /api/graph/path` 组装路径（响应键是 `nodes`）。颜色映射掌握程度用 `node_status_updates`（difficult=红/in_progress=黄/mastered=绿）。
2. **W3 路径展示**：`assess` 响应的 `knowledge_graph.learning_path` 已排序，直接渲染。
3. **W4 资源页**：`generated_content.resources` 按 `content_type` 分三区（讲义/实操/测试）。`content` 是 markdown，用 markdown 渲染器。
4. **W5 答题**（三步闭环流程）：
   - `POST /assess` (`mode=interactive`) → 拿 `session_id` + `assessment.questions`，前端渲染答题组件
   - 用户作答后 `POST /submit` (`{session_id, answers}`) → 拿 `profile` + `assessment`(含判分) + `feedback`(动态反馈策略)
   - 按 `feedback.strategy` 调 `POST /feedback` (`{session_id, strategy, profile}`) → 拿针对性再生内容 `resources`（降维讲义/补基础/进阶题），渲染给用户
   - `advance`→进阶挑战题，`remediate`→降维重讲讲义，`scaffold`→补前置基础讲义。`answers` 顺序必须与 `questions` 一致。
5. **空值处理**：所有响应字段始终存在，降级时为 `{}` 或 `[]`。⚠️ **判空看内层数组长度**，不要用顶层 `Object.keys().length`：
   - `knowledge_graph` 为空 → 判 `knowledge_graph.learning_path?.length === 0`（顶层对象始终含 5 个 key）
   - `generated_content` 为空 → 判 `generated_content.resources?.length === 0`（顶层对象始终含 4 个 key）
   - `profile` 为空 → 判 `Object.keys(profile).length === 0`（profile 无固定 key，可顶层判空）

## 七、C 端对接要点

1. **知识节点 JSON** 用 `id` 字段（非 `node_id`），导入脚本会映射。运行时 engine 统一返回 `node_id`。
2. **画像样本**：`recommended_path` 应为对象结构（含 `current_node`/`next_nodes`/`estimated_completion_weeks`）。`validate_data.py` 对该字段做结构校验（存在则校验格式，并提示废弃 `recommended_start_node`）；建议样本画像都填写以保完整。`common_mistakes` 字段当前 schema 未定义、92 节点未填充，C 端后续补齐可让生成内容更精准。
3. **prompt 同步**：`01/02/03/04/05_*.txt` 当前由 A 维护（C 未动），C 接管前注意已被 A 改动。

---

## 八、待办与遗留

- ✅ `mode=interactive` 的答案提交接口 `POST /api/diagnostics/submit`（W5 已实现，含动态反馈 advance/remediate/scaffold）
- 代码测试 Agent `code_tester`（W6，对 generated_content 中代码题生成 pytest）
- 有项目场景：AST 解析 + 项目图谱（W6）
- ✅ 动态反馈内容再生 `POST /api/diagnostics/feedback`（W5 已实现：remediate 降维讲义 / scaffold 补前置 / advance 进阶题，按 strategy 针对性再生）
- `datetime.utcnow()` 弃用警告全模块待批量迁移（非阻塞）

---

## 九、验证方式

```bash
# 启动后端
cd backend && uvicorn app.main:app --reload

# Postman/curl 触发全流程 (demo)
curl -X POST http://localhost:8000/api/diagnostics/assess \
  -H "Content-Type: application/json" \
  -d '{"target_direction":"Python 基础语法入门","mode":"demo"}'

# interactive 两步答题
curl -X POST http://localhost:8000/api/diagnostics/assess \
  -H "Content-Type: application/json" \
  -d '{"target_direction":"Python 基础语法入门","mode":"interactive"}'
# → 拿到 session_id + questions，前端作答后:
curl -X POST http://localhost:8000/api/diagnostics/submit \
  -H "Content-Type: application/json" \
  -d '{"session_id":"<上一步的session_id>","answers":["A","对","B"]}'
# → 拿到 profile + feedback.strategy，按策略再生内容:
curl -X POST http://localhost:8000/api/diagnostics/feedback \
  -H "Content-Type: application/json" \
  -d '{"session_id":"<session_id>","strategy":"remediate","profile":{"theory_level":2,"weak_topics":[{"node_id":"PY-005","mastery":0.2}]}}'

# 图谱查询
curl http://localhost:8000/api/graph/node/PY-001
curl -X POST http://localhost:8000/api/graph/path \
  -H "Content-Type: application/json" \
  -d '{"known_ids":[],"weak_ids":[],"level":2,"max_nodes":10}'
```

单测：`cd backend && python -m pytest tests/ -q`（130 passed）
