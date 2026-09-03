# 2026-06-18 — 三端审查报告 A 端 Action Item 修复

**参与成员**: A（后端）
**会话目标**: 按 `docs/W1-2_ABC三端审查报告_2026-06-18.md` 认领并修复 A 端 P0/P1/P2 Action Item
**耗时**: 0.5 日

---

## 一、背景

B 端在 6/18 完成 W1-2 三端审查，产出审查报告与 BUG-023~026 记录。其中 A 端待认领项：

| 优先级 | 项 | 状态 |
|:---|:---|:---|
| 🔴 P0 #2 | `recommended_path` 字段三方错配（BUG-025） | ✅ |
| 🔴 P0 #4 | `_grade` question_index 治本（BUG-026） | ✅ |
| 🟡 P1 C7 | state.py 注释 `per_question_scores` → `per_node` | ✅ |
| 🔵 P2 C1 | engine.py:110 `id` 兜底命名收口 | ⚠️ 经核实**不可删除**，改为加注释说明 |

---

## 二、产出

| 产出 | 文件 | 说明 |
|:---|:---|:---|
| recommended_path 对象化 | `backend/app/agents/diagnostics.py` | `_build_profile` 输出从 `recommended_start_node`(string) → `recommended_path: {current_node, next_nodes, estimated_completion_weeks}`；新增 `_suggest_next_nodes` 纯函数 |
| _grade 治本 | `backend/app/agents/diagnostics.py` | 判分 prompt 要求 LLM 显式回写 `question_index`；后端 `g.get("question_index", idx)` + 越界/非 int 兜底 + 非 dict 跳过 |
| prompt schema 同步 | `data/prompts/01_orchestrator_agent.txt` + `02_diagnostics_agent.txt` | 输出 schema 段从 `recommended_start_node` → `recommended_path` 对象 |
| 画像校验增强 | `backend/scripts/validate_data.py` | 新增 `recommended_path` 结构校验（current_node/next_nodes/weeks）+ `recommended_start_node` 废弃提示 |
| state 注释修正 | `backend/app/agents/state.py` | `per_question_scores` → `per_node`（C7） |
| engine 兜底注释 | `backend/app/graph/engine.py` | `generate_embeddings` 的 `node_id or id` 兜底加注释说明不可删（C1） |
| 单测补齐 | `backend/tests/test_diagnostics_unit.py` | 新增 4 用例：`_grade` 乱序/缺字段/越界 3 个 + `recommended_path` 序列 1 个；改 2 个旧用例断言新结构 |

---

## 三、关键设计决策

### 1. `recommended_path.next_nodes` 不引入 `kg` 依赖

报告建议"复用图遍历取 weak 之后的 3-5 个"。但 `_build_profile` 是**纯函数**（已建立 47 项纯函数测试体系），若注入 `kg` 会破坏可测性。

权衡：候选 `nodes` 已由 `engine.assemble_learning_path` 按"距离升序、层内难度升序"排好序，本身就是合理进阶序列。故 `_suggest_next_nodes` 直接从 `nodes` 顺序取 `current_node` 之后的节点，保持纯函数 + 可单测。`current_node` 不在候选列表时（如默认 `PY-001`）从头取前 N 个。

### 2. C1「删除 `or node.get('id')` 兜底」**未采纳** —— 报告建议会致回归

报告（B 撰写）C1 建议"删除 engine.py:110 的 `or node.get('id')` 兜底，命名彻底收口"。经核实**不可删**：

- `generate_embeddings` 被 `import_knowledge_base.py:263` 调用，传入的是**原始 JSON 节点**（用 `id` 键，知识库 JSON 文件均用 `id`）。
- `_node_from_record` 的 `id`→`node_id` 映射只作用于**图读取**节点，不作用于 import 路径传入的原始节点。
- 删除兜底 → `node_ids` 全为 `None` → `MATCH (n:KnowledgeNode {id: $id})` 全部失配 → embedding 永不写回。

处理：保留兜底，加注释说明两种来源与删除后果。命名真正收口需在 import 脚本侧统一（C 域 / 后续），非 engine 单点删除可达。**已在 BUG 日志与本文档记录此偏离**。

### 3. prompt 由 A 同步（非 C）

项目速查卡 规定 `data/prompts/` 由 C 统筹。但 `01_orchestrator_agent.txt` / `02_diagnostics_agent.txt` 的头部均标注"更新: 2026/06/17 A — 对齐代码实际实现"，即 A 历史维护此二 prompt，且审查报告 A6 确认"C 未动、目前不冲突"。为避免数据契约再次错配（正是 BUG-025 的根因），由 A 一并同步 prompt schema 段。C 后续若接管需注意此二文件已被 A 改动。

---

## 四、测试覆盖

```
51 passed, 9 warnings in 2.49s   (原 47 → +4)

测试文件分布:
  test_state.py             4
  test_llm.py               5
  test_orchestrator.py      3
  test_diagnostics_unit.py 23  (+4 新增)
  test_reviewer_unit.py    11
  ─────────────────────────
  Total                    51
```

新增 `_grade` 用例（monkeypatch 假 model，免真实 LLM API）：
- `test_grade_disordered_question_index` — LLM 乱序返回但显式回写 `question_index` → 正确归位
- `test_grade_fallback_when_question_index_missing` — LLM 旧格式无字段 → 回退数组下标
- `test_grade_fallback_when_question_index_out_of_range` — 越界值 99 → 回退下标 0

新增 `_build_profile` 用例：
- `test_build_profile_recommended_path_next_nodes_sequence` — next_nodes 取 current 之后候选序列

数据校验：`validate_data.py` → 92 节点 + 4 画像 0 错误。

---

## 五、数据契约变更（B/C 端需知晓）

| 变更 | 旧 | 新 |
|:---|:---|:---|
| `user_profile.recommended_start_node` | `"PY-001"` (string) | **已废弃** → `recommended_path` (object) |
| `user_profile.recommended_path` | 不存在 | `{current_node, next_nodes[], estimated_completion_weeks}` |

前端 `stores/assessment.js:29` JSDoc 已写 `recommended_path`，无需改；后续 KnowledgeGraph 主图组件按 object 结构消费。`per_node` 结构（BUG-022 已改）不变。

---

## 六、遗留 / 待 C 端

- C1 真正命名收口需 import 脚本侧统一 `id`→`node_id`（C 域或后续联调），本次仅加注释防回归。
- 项目速查卡 `BUG 清单: 16 条` 计数已过时（实际 26 条），未在本会话改动（共享文件，留给 owner 统一更新）。
- 隐性风险 C2（reviewer 校验 node_id 真实性）、C3（`_demo_answer` 硬编码初学者水平）、C5（OpenAI 客户端 lifespan 关闭）未在本批处理，按报告属 P2+，后续排期。
