# B 端契约冻结 + 修复与联调指引

> **面向**: B（前端）开发者
> **来源**: A 端审查 + 联调支持，2026-06-18
> **目的**: B 端照此文档可放心对接已冻结接口、修复 BUG-027~030、对接 W5 新接口，无需读后端源码。所有行号基于当前 main 分支真实代码。
> **配套**: 环境怎么起见 [B-C端环境准备清单.md](B-C端环境准备清单.md)；响应样本见 [B端联调用例集.md](B端联调用例集.md)

---

## §0 契约冻结声明（2026-06-18 起）

A 端已超前完成 W3~W5（图谱查询 / 内容生成 / interactive 答题闭环）。现冻结已交付接口契约，B 可放心对接。

### 冻结范围

| 接口 | 状态 |
|:---|:---|
| `POST /api/diagnostics/assess`（demo + interactive） | ✅ 冻结 |
| `POST /api/diagnostics/submit` | ✅ 冻结 |
| `POST /api/diagnostics/feedback` | ✅ 冻结 |
| `GET /api/graph/*`（10 个图谱查询路由） | ✅ 冻结 |

### 冻结规则

- 字段结构、字段名、嵌套形态**不再做 breaking change**
- 如需扩展，**只加可选字段**，不删不改现有字段
- 真有不可逆的 breaking change，A 会**提前在 BUG 决策日志记一笔 + 群内通知**，不静默改
- 后续若要解除冻结（如 W6+ 架构调整），A 会发更新通知

### B 端最易踩的契约坑（对接前先看一眼）

| 坑 | 正确做法 |
|:---|:---|
| `recommended_path` 是**对象** `{current_node, next_nodes[], ...}`，非字符串 | 别按旧 `recommended_start_node` 取 |
| `per_node[node_id]` 元素是**对象** `[{question_index, correct}]` | 判对错用 `g.correct === true`，别 `filter(Boolean)` |
| `assess(interactive)` 下发的 questions **不含 `answer`**（BUG-033 防泄露） | answer 只在 submit 响应里，前端别本地判分 |
| `/api/graph/path` 返回键是 `nodes`，**不是** `learning_path` | 取 `.nodes` |
| `knowledge_graph` / `generated_content` 顶层对象**始终含固定 key** | 判空用**内层数组长度**（`learning_path?.length` / `resources?.length`），别用 `Object.keys().length` |

完整字段契约见 §三。

---

## §一 待修复 BUG（4 条，均有可直接 copy 的补丁）

### BUG-027: el-alert 错误原因被插槽覆盖不显示

**文件**: `frontend/src/views/Assessment.vue:98-113`

**根因**: `el-alert` 的 `#default` 插槽就是描述内容插槽，提供后会**替换** `:description` prop。当前插槽里只有按钮，所以 `store.error` 永远不渲染，用户只看到"测评失败"标题 + 按钮。

**修复**（把错误文案放进插槽，按钮置于其下）:

```html
<!-- 替换 98-113 行 -->
<el-alert
  v-if="store.error && !store.loading"
  title="测评失败"
  type="error"
  show-icon
  :closable="true"
  @close="store.error = null"
  style="margin-bottom: 16px;"
>
  <template #default>
    <p style="margin: 0 0 8px;">{{ store.error }}</p>
    <el-button size="small" type="primary" @click="retry">重新测评</el-button>
  </template>
</el-alert>
```

> 注意：删掉 `:description="store.error"` 这行 prop（改由插槽渲染）。

---

### BUG-028: 后端降级空画像时前端静默失败

**文件**: `frontend/src/stores/assessment.js:120-141`（`startAssessment` 的 try 块）

**根因**: 后端 LLM 未配置/异常时返回 HTTP 200 + 空 `profile={}`，工作流耗尽重试后正常结束。前端 `hasResults`（59-64 行）因空对象守卫返回 false、`error` 保持 null → 四状态分支全落空，用户等十几秒后静默回到输入表单。后端已在 `review_results.retry_hint` 给出原因，前端没消费。

**修复**（成功后检测空画像，把 `retry_hint` 转成 error）:

```js
// 替换 stores/assessment.js 的 128-133 行（try 块内的赋值部分）
sessionId.value = data.session_id
profile.value = data.profile
assessment.value = data.assessment
reviewResults.value = data.review_results
orchestrationLog.value = data.orchestration_log || []

// BUG-028: 空画像 = 后端降级，转成错误反馈给用户
if (!data.profile || Object.keys(data.profile).length === 0) {
  error.value = data.review_results?.retry_hint
    || '学情检测未产出有效画像（后端 LLM 可能未配置），请检查后端配置后重试'
  profile.value = null  // 清空，避免 hasResults 误判
  return
}
```

> 此修复依赖 BUG-027 已修（否则 error 文案仍不在 alert 显示）。

---

### BUG-029: AssessmentReport 未作答题目渲染空白

**文件**: `frontend/src/components/AssessmentReport.vue:152`（`questionList`）+ `:58`（模板）

**根因**: `answer: answers[idx] ?? ''` 把 `undefined` 强制转成空字符串 `''`。模板 `{{ q.answer ?? '（未作答）' }}` 的 `??` 对空字符串不触发（空串非 nullish）→ 未作答题显示空白。interactive 模式（W5 启用）下全部未作答时会暴露。

**修复**（二选一，推荐第一个，保留 null 语义清晰）:

```js
// 方案A: AssessmentReport.vue:152，保留 null 让 ?? 生效
answer: answers[idx] ?? null,
```

或

```html
<!-- 方案B: AssessmentReport.vue:58，改用 || 兜底 -->
<span :class="answerClass(q.grade?.correct)">{{ q.answer || '（未作答）' }}</span>
```

---

### BUG-030: store 未消费 knowledge_graph / generated_content 字段

**文件**: `frontend/src/stores/assessment.js:129-133`（字段映射）+ state 声明区

**根因**: 后端 `/assess`(demo) 响应含 `knowledge_graph`（学习路径）和 `generated_content`（学习资源），store 只映射了 5 个字段，这两个被丢弃。W3 图谱页、W4 资源页要用。

**修复**:

1. state 声明区（约 49 行 `orchestrationLog` 后）加：
```js
/** 学习路径图谱 (graph_controller 产出) */
const knowledgeGraph = ref(null)
/** 生成的学习资源 (content_generator 产出) */
const generatedContent = ref(null)
```

2. `startAssessment` try 块（128-133 行）补映射：
```js
knowledgeGraph.value = data.knowledge_graph || null
generatedContent.value = data.generated_content || null
```

3. `reset()`（145-152 行）补清空：
```js
knowledgeGraph.value = null
generatedContent.value = null
```

4. return 对象（155-173 行）补导出：
```js
return {
  // ...原有
  knowledgeGraph,
  generatedContent,
  // ...
}
```

> 结构见 `docs/A端后端对接文档.md` §4.4 / §4.5。判空用内层数组长度（`knowledgeGraph.learning_path?.length`），勿用 `Object.keys`（顶层对象始终含固定 key）。

---

## §二 W5 新接口对接（B 端尚未封装）

后端 W5 新增 `submit` / `feedback` 两个接口，B 端 `api/diagnostics.js` 目前只有 `submitAssessment`（调 `/assess`）。需补封装。

### interactive 三步流程

```
1. POST /assess (mode=interactive) → session_id + assessment.questions (无 answer)
2. POST /submit  ({session_id, answers}) → profile + assessment(含判分) + feedback.strategy
3. POST /feedback ({session_id, strategy, profile}) → 针对性再生 resources
```

### 在 `frontend/src/api/diagnostics.js` 补充

```js
/**
 * 提交 interactive 答题 (W5)
 * @param {string} sessionId - assess(interactive) 返回的 session_id
 * @param {string[]} answers - 逐题作答，顺序与 questions 一致
 * @returns {Promise<{session_id, profile, assessment, feedback}>}
 */
export function submitAnswers({ sessionId, answers }, signal) {
  return http.post('/api/diagnostics/submit', {
    session_id: sessionId,
    answers,
  }, signal ? { signal } : undefined)
}

/**
 * 动态反馈内容再生 (W5)
 * @param {string} sessionId
 * @param {'advance'|'remediate'|'scaffold'} strategy - 来自 submit 响应的 feedback.strategy
 * @param {Object} profile - 来自 submit 响应的 profile
 * @returns {Promise<{session_id, strategy, resources[], node_count}>}
 */
export function requestFeedback({ sessionId, strategy, profile }, signal) {
  return http.post('/api/diagnostics/feedback', {
    session_id: sessionId,
    strategy,
    profile,
  }, signal ? { signal } : undefined)
}
```

### 关键契约提醒

- **assess(interactive) 返回的 questions 不含 `answer` 字段**（BUG-033 已修，防泄露）。判分/复盘的 answer 只在 submit 响应里。
- **assess 响应统一是 `AssessResponse`**（demo 全填充，interactive 仅 session_id + assessment），按 `assessment.answers` 是否为空判阶段。
- **feedback.strategy** 三档：`advance`(进阶题)/`remediate`(降维讲义)/`scaffold`(补基础讲义)，B 端据此渲染不同 UI。
- **submit/feedback 的 session_id 必须来自 assess(interactive)**，后端内存缓存（上限 100 条 LRU），服务重启会失效。

---

## §三 字段契约速查（防对接踩坑）

| 字段 | 结构 | 注意点 |
|:---|:---|:---|
| `profile.recommended_path` | `{current_node, next_nodes[], estimated_completion_weeks}` | 是**对象**非字符串（旧 `recommended_start_node` 已废弃） |
| `assessment.per_node[node_id]` | `[{question_index, correct}]` | 元素是**对象**非 bool（BUG-022），`nodeCorrect` 用 `filter(g => g && g.correct === true)` |
| `review_results.dimensions` | `{四维度:{score,issues}}` | 始终含四维度（含降级），不会缺失 key |
| `knowledge_graph` | `{learning_path[], path_node_ids[], ...}` | 判空用 `learning_path?.length`，顶层对象始终含 5 key |
| `generated_content` | `{resources[], node_count, ...}` | 判空用 `resources?.length`，顶层对象始终含 4 key |
| `feedback` (submit 响应) | `{strategy, accuracy, description}` | strategy 决定调哪个 feedback 内容 |

完整契约见 `docs/A端后端对接文档.md`。

---

## §四 真实环境联调补充（能起 Neo4j+LLM 时）

B 已能起后端环境时（见 [B-C端环境准备清单.md](B-C端环境准备清单.md)），优先用真实后端联调，用例集降为备选。真实联调有几点 mock 测不出的，**必跑**：

### 1. 降级验证（造降级测前端处理）

| 造降级 | 期望响应 | 验证点 |
|:---|:---|:---|
| `docker-compose stop neo4j` | assess → 503 `知识图谱引擎未就绪` | 拦截器 toast |
| `.env` 留 `LLM_API_KEY=sk-placeholder` | assess → 200 + `profile={}` | BUG-028 修复后显示 retry_hint |
| `.env` 留空 `EMBEDDING_API_KEY` | `/api/graph/search` → 503 | 图遍历查询仍可用 |
| 答完 interactive 后重启后端再 submit | submit → 404 session 不存在 | 拦截器 404 分支（待补） |

### 2. interactive 流程真实数据注意点

mock 下 session_id 写死，真实联调注意：

- `session_id` 来自 `assess(interactive)`，**必须原样带回** submit/feedback
- session 缓存上限 **100 条 LRU**，并发/长时间挂着可能被挤掉
- **服务重启缓存全失效**——开发期 A 改后端重启频繁，B 的 session 会 404，属正常，重新 assess 即可
- feedback 的 `strategy` **必须用 submit 响应返回的那个**，别前端硬编码

### 3. 真实环境才暴露的性能问题

- LLM 真实调用 15~30s，前端 timeout 60s（`api/index.js:12`）。频繁超时找 A，可考虑流式或调大 timeout。
- 知识库数据缺失导致空路径 → 是 C 端数据问题，A 协助转达。

### 4. mock 何时仍用

真实环境起不来时，用 [B端联调用例集.md](B端联调用例集.md) 的 JSON 样本 mock（axios 拦截器或 msw）。降级场景造不出时也用样本补。

---

## §五 降级场景对照（前端该如何响应）

| 后端场景 | HTTP | 前端应表现 |
|:---|:---|:---|
| Neo4j 未连接 | 503 | 拦截器弹 toast（已支持）|
| LLM 未配置（sk-placeholder）| 200 + profile={} | BUG-028 修复后显示 retry_hint |
| 审核超 max_retries | 200 + review_results.passed=false | 报告区显示"打回"标签（已支持）|
| assess(interactive) 出题 | 200 + assessment.answers=[] | 渲染答题组件 |
| submit session 不存在 | 404 | 拦截器走 else 弹"网络错误"（建议 B 补 404 专属提示）|
| feedback 无效 strategy | 422 | 拦截器弹"参数错误"（已支持）|

> 注：拦截器 `api/index.js:32-55` 对 422/503/500 已有 toast，但 404 走 else 分支显示"网络错误"，语义不准。建议 B 在拦截器补 `else if (status === 404)` 分支，或各业务调用处单独 catch 404。

---

## §六 联调用例

见同目录 [B端联调用例集.md](B端联调用例集.md)，含每个接口的成功/降级/错误响应 JSON 样本，可用作前端 mock 或 Postman 验证。

---

## §七 A 端可配合的后端调整（如 B 需要）

若 B 在修复/对接过程中发现需要后端配合（如某字段名想改、某降级语义想调整），告诉我，A 在后端侧调整——但 B 端代码仍由 B 自己改。当前 4 个 BUG 都是纯前端逻辑/UI，A 侧无需改动。

> 契约冻结期间，A 不会对上述接口做 breaking change。B 放心对接。
