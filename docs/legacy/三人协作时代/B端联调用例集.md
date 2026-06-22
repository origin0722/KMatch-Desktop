# B 端联调用例集（A 端提供）

> **面向**: B（前端）开发与联调
> **用途**: 每个接口的成功/降级/错误响应 JSON 样本，可作前端 mock 数据或 Postman 验证基准。无需起 Neo4j+LLM 即可开发前端。
> **基准**: 后端 main 分支 `5e922a0`，对齐 `docs/A端后端对接文档.md`

---

## 一、POST /api/diagnostics/assess

### 1.1 demo 模式 · 成功（全流程闭环）

**请求**:
```json
{
  "target_direction": "Python 基础语法入门",
  "mode": "demo",
  "known_topics": [],
  "scene": "no_project",
  "max_retries": 3
}
```

**响应** (200):
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "profile": {
    "profile_id": "UP-DIA-a1b2c3",
    "name": "测评用户",
    "created_at": "2026-06-18T10:00:00Z",
    "type": "学情检测产出",
    "theory_level": 2,
    "practical_level": 1,
    "learning_style": "read_write",
    "target_direction": "Python 基础语法入门",
    "preferred_pace": "normal",
    "time_per_week": 6,
    "known_topics": [
      {"node_id": "PY-001", "mastery": 1.0, "last_test_score": 10.0}
    ],
    "weak_topics": [
      {"node_id": "PY-012", "mastery": 0.0, "error_patterns": ["切片索引混淆"]}
    ],
    "weakness_areas": ["对《列表切片》掌握不足"],
    "recommended_path": {
      "current_node": "PY-012",
      "next_nodes": ["PY-015", "PY-018"],
      "estimated_completion_weeks": 5
    },
    "raw_assessment_data": {"theory_test": {"total_questions": 8, "correct": 5}}
  },
  "review_results": {
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
    "reviewed_at": "2026-06-18T10:00:30Z"
  },
  "assessment": {
    "questions": [
      {"type": "choice", "node_id": "PY-001", "question": "下列哪个是合法的变量名？", "options": ["1var", "_var", "var-name", "class"], "answer": "_var", "difficulty": 1},
      {"type": "judge", "node_id": "PY-012", "question": "lst[-1] 取列表第一个元素", "answer": "错", "difficulty": 2}
    ],
    "answers": ["_var", "错"],
    "per_node": {
      "PY-001": [{"question_index": 0, "correct": true}],
      "PY-012": [{"question_index": 1, "correct": false}]
    },
    "correct_count": 5,
    "total_count": 8
  },
  "knowledge_graph": {
    "learning_path": [
      {"node_id": "PY-012", "name": "列表切片", "difficulty": 2, "summary": "...", "estimated_minutes": 60},
      {"node_id": "PY-015", "name": "字典", "difficulty": 3, "summary": "...", "estimated_minutes": 75}
    ],
    "path_node_ids": ["PY-012", "PY-015"],
    "estimated_total_hours": 2.3,
    "node_status_updates": {"PY-012": "difficult", "PY-015": "in_progress"},
    "assembled_at": "2026-06-18T10:00:31Z"
  },
  "generated_content": {
    "resources": [
      {
        "content_type": "lecture",
        "target_node_id": "PY-012",
        "difficulty_level": 2,
        "adaptation_profile": "beginner",
        "source_nodes": ["PY-012.key_points[0]", "PY-012.summary"],
        "content": "# 列表切片\n\n切片是 Python 提取子序列的语法...",
        "generated_at": "2026-06-18T10:00:35Z"
      },
      {
        "content_type": "practice_guide",
        "target_node_id": "PY-012",
        "difficulty_level": 2,
        "adaptation_profile": "beginner",
        "source_nodes": ["PY-012.key_points[1]"],
        "content": "# 实操：用切片反转列表\n\n任务目标...",
        "generated_at": "2026-06-18T10:00:36Z"
      },
      {
        "content_type": "test",
        "target_node_id": "PY-012",
        "difficulty_level": 2,
        "adaptation_profile": "beginner",
        "source_nodes": ["PY-012.key_points[0]"],
        "content": "# 测试题\n\n1. (基础) lst[1:3] 取哪些元素？",
        "generated_at": "2026-06-18T10:00:37Z"
      }
    ],
    "node_count": 1,
    "content_types": ["lecture", "practice_guide", "test"],
    "generated_at": "2026-06-18T10:00:37Z"
  },
  "orchestration_log": [
    "[2026-06-18T10:00:00] 🔧 学情检测: 开始 (mode=demo)",
    "[2026-06-18T10:00:05] 📖 取得候选节点 4 个",
    "[2026-06-18T10:00:08] 📝 生成理论题 8 道",
    "[2026-06-18T10:00:15] ✅ 画像产出: theory_level=2, known=3, weak=2, 正确率=5/8",
    "[2026-06-18T10:00:20] 🔍 内容审核: 开始审画像 (第1轮)",
    "[2026-06-18T10:00:25] ✅ 画像审核通过: 总分=0.92 (阈值0.85)",
    "[2026-06-18T10:00:26] 🗺️ 知识图谱管控: 开始组装学习路径",
    "[2026-06-18T10:00:28] ✅ 路径组装完成: 5 个节点，预估 2.3h",
    "[2026-06-18T10:00:30] 📚 领域知识生成: 开始",
    "[2026-06-18T10:00:37] ✅ 生成完成: 3 段资源",
    "[2026-06-18T10:00:38] 📝 内容模式: 审核 3 段生成资源",
    "[2026-06-18T10:00:40] ✅ 生成内容审核通过: 总分=0.91",
    "[2026-06-18T10:00:40] ✅ 流程结束 (内容审核通过 + 学习资源已交付)"
  ]
}
```

### 1.2 demo 模式 · LLM 未配置降级

**请求**: 同 1.1

**响应** (200，注意 profile 为空):
```json
{
  "session_id": "...",
  "profile": {},
  "review_results": {
    "passed": false,
    "overall_score": 0.0,
    "threshold": 0.85,
    "dimensions": {
      "factual_accuracy": {"score": 1.0, "issues": []},
      "hallucination": {"score": 1.0, "issues": []},
      "logic_consistency": {"score": 1.0, "issues": []},
      "teaching_appropriateness": {"score": 1.0, "issues": []}
    },
    "verdict": "reject",
    "retry_hint": "LLM 未配置，请检查后端 LLM 配置后重试",
    "reviewed_at": "2026-06-18T10:00:01Z"
  },
  "assessment": {},
  "knowledge_graph": {},
  "generated_content": {},
  "orchestration_log": [
    "[2026-06-18T10:00:00] 🔧 学情检测: 开始 (mode=demo)",
    "[2026-06-18T10:00:00] ⚠️ LLM 未配置，学情检测降级为空画像"
  ]
}
```
> 前端：BUG-028 修复后，检测到 `profile={}` → 显示 `retry_hint`。

### 1.3 interactive 模式 · 出题

**请求**:
```json
{
  "target_direction": "Python 基础语法入门",
  "mode": "interactive"
}
```

**响应** (200，questions **不含 answer**):
```json
{
  "session_id": "660e8400-e29b-41d4-a716-446655440001",
  "profile": {},
  "review_results": {},
  "assessment": {
    "questions": [
      {"type": "choice", "node_id": "PY-001", "question": "下列哪个是合法的变量名？", "options": ["1var", "_var", "var-name", "class"], "difficulty": 1},
      {"type": "judge", "node_id": "PY-012", "question": "lst[-1] 取列表第一个元素", "difficulty": 2}
    ],
    "answers": [],
    "per_node": {},
    "correct_count": 0,
    "total_count": 8
  },
  "knowledge_graph": {},
  "generated_content": {},
  "orchestration_log": []
}
```
> 注意：`questions[*]` 无 `answer` 字段（BUG-033 防泄露）。前端渲染答题组件，保存 `session_id`。

### 1.4 Neo4j 未连接

**响应** (503):
```json
{"detail": "知识图谱引擎未就绪（Neo4j 未连接）"}
```

---

## 二、POST /api/diagnostics/submit

### 2.1 答题提交 · 成功（5/8 正确 → remediate）

**请求**:
```json
{
  "session_id": "660e8400-e29b-41d4-a716-446655440001",
  "answers": ["_var", "错", "B", "对", "A", "错", "C", "对"]
}
```

**响应** (200):
```json
{
  "session_id": "660e8400-e29b-41d4-a716-446655440001",
  "profile": {
    "profile_id": "UP-DIA-d4e5f6",
    "theory_level": 3,
    "known_topics": [{"node_id": "PY-001", "mastery": 1.0}],
    "weak_topics": [{"node_id": "PY-012", "mastery": 0.0, "error_patterns": ["切片索引混淆"]}],
    "recommended_path": {"current_node": "PY-012", "next_nodes": ["PY-015"], "estimated_completion_weeks": 5}
  },
  "assessment": {
    "questions": [
      {"type": "choice", "node_id": "PY-001", "question": "...", "options": [...], "answer": "_var", "difficulty": 1}
    ],
    "answers": ["_var", "错", "B", "对", "A", "错", "C", "对"],
    "per_node": {
      "PY-001": [{"question_index": 0, "correct": true}],
      "PY-012": [{"question_index": 1, "correct": false}]
    },
    "correct_count": 5,
    "total_count": 8
  },
  "feedback": {
    "strategy": "remediate",
    "accuracy": 0.625,
    "description": "部分掌握，触发降维解释——换一个角度重新讲解同一知识点"
  }
}
```
> submit 响应的 questions **含 answer**（复盘用）。`feedback.strategy` 决定下一步调哪个 feedback。

### 2.2 全对 → advance

`feedback`: `{"strategy": "advance", "accuracy": 1.0, "description": "..."}`

### 2.3 全错 → scaffold

`feedback`: `{"strategy": "scaffold", "accuracy": 0.0, "description": "..."}`

### 2.4 session 不存在

**响应** (404):
```json
{"detail": "会话 660e8400-... 不存在或已过期（interactive 题目缓存上限 100）"}
```

### 2.5 LLM 未配置

**响应** (503):
```json
{"detail": "LLM 未配置，无法判分（请配置 LLM_API_KEY）"}
```

---

## 三、POST /api/diagnostics/feedback

### 3.1 remediate · 降维讲义

**请求**:
```json
{
  "session_id": "660e8400-e29b-41d4-a716-446655440001",
  "strategy": "remediate",
  "profile": {
    "theory_level": 3,
    "weak_topics": [{"node_id": "PY-012", "mastery": 0.0}]
  }
}
```

**响应** (200):
```json
{
  "session_id": "660e8400-e29b-41d4-a716-446655440001",
  "strategy": "remediate",
  "resources": [
    {
      "content_type": "lecture",
      "target_node_id": "PY-012",
      "difficulty_level": 2,
      "adaptation_profile": "intermediate",
      "source_nodes": ["PY-012.key_points[0]", "PY-012.summary"],
      "content": "# 换个角度理解切片\n\n想象列表是一排抽屉...",
      "generated_at": "2026-06-18T10:05:00Z"
    }
  ],
  "node_count": 1
}
```

### 3.2 scaffold · 补前置基础

请求 `strategy: "scaffold"`，`resources` 是弱项前置依赖节点的入门讲义。

### 3.3 advance · 进阶挑战题

请求 `strategy: "advance"`，`resources[0].content_type: "test"`（跨知识点推理题）。

### 3.4 无目标节点（弱项不在路径中）

**响应** (200，resources 空):
```json
{
  "session_id": "...",
  "strategy": "remediate",
  "resources": [],
  "node_count": 0
}
```

### 3.5 无效 strategy

**响应** (422，Pydantic Literal 校验):
```json
{"detail": [{"type": "literal_error", "loc": ["body", "strategy"], "msg": "...", "input": "bogus"}]}
```

### 3.6 session 不存在

**响应** (404): 同 2.4

---

## 四、GET /api/graph 系列（W3 图谱页）

### 4.1 GET /node/PY-001

```json
{
  "node_id": "PY-001",
  "name": "变量与赋值",
  "category": "基础语法",
  "difficulty": 1,
  "tags": ["变量", "赋值"],
  "summary": "变量是存储数据的名字，赋值用 = 将值绑定到变量名。",
  "key_points": ["变量命名规则", "动态类型", "多重赋值"],
  "prerequisites": [],
  "estimated_minutes": 45,
  "practice_questions": [{"type": "choice", "question": "...", "options": [...], "answer": "A"}]
}
```
> ⚠️ **不含 `common_mistakes`**（C 端数据未填充，见对接文档 §3.2）。前端访问需 `node.common_mistakes ?? []` 兜底。

### 4.2 POST /path

**请求**: `{"known_ids": [], "weak_ids": [], "level": 2, "max_nodes": 10}`

**响应** (200):
```json
{
  "path_length": 8,
  "estimated_total_hours": 9.5,
  "nodes": [
    {"node_id": "PY-001", "name": "变量与赋值", "difficulty": 1, "estimated_minutes": 45},
    {"node_id": "PY-002", "name": "条件判断", "difficulty": 2, "estimated_minutes": 60}
  ]
}
```
> ⚠️ 返回键是 `nodes`，非 `learning_path`（与 assess 响应的 knowledge_graph 不同）。

### 4.3 GET /node/PY-999（不存在）

**响应** (404): `{"detail": "节点 PY-999 不存在"}`

### 4.4 GET /search（embedding 未配置）

**响应** (503): `{"detail": "语义检索不可用（Embedding 客户端未配置），请使用图遍历类查询"}`

---

## 五、错误码速查

| 码 | 场景 | detail 样例 |
|:---|:---|:---|
| 422 | assess/feedback 参数校验失败 | Pydantic 错误数组 |
| 404 | submit/feedback session 不存在；/node 不存在 | "会话 ... 不存在或已过期" |
| 503 | Neo4j/LLM/Embedding 未就绪 | "知识图谱引擎未就绪..." |
| 500 | 工作流/判分/再生异常 | "测评流程执行失败: ..." |

> 前端拦截器 `api/index.js` 已处理 422/503/500 的 toast，**404 走 else 显示"网络错误"语义不准**，建议 B 补 404 分支。

---

## 六、mock 建议

B 端开发时若不想起后端，可直接用本文件的 JSON 样本 mock：
- `axios` 拦截器或 `msw` 拦截 `/api/diagnostics/*` 返回对应样本
- interactive 流程：先返回 1.3 出题，记下 mock 的 session_id，submit/feedback 返回 2.1/3.1
- 降级测试：用 1.2 / 2.4 / 1.4 样本验证前端错误处理
