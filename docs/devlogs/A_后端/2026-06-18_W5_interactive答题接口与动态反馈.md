# 2026-06-18 — W5 interactive 答题接口 + 动态反馈（feature 分支）

**参与成员**: A（后端）+ Claude
**分支**: `feature/W5-backend-interactive`（按计划书 W5 起 feature 分支策略）
**会话目标**: 实现 interactive 模式答题提交接口 + 动态反馈机制（W4 计划⑤ + 对接文档 W5 缺口）
**耗时**: 0.5 日

---

## 一、背景

对接文档标注 `mode=interactive` 答题提交接口为 W5 缺口。W4 全流程闭环已交付（demo 模式），但 interactive 模式此前在 diagnostics_node 内跑完整工作流（`answers=[""]*n` 判全错），语义错误。本次实现真正的两步答题闭环。

W5 起按计划书「第5-6周 feature/xxx」分支策略，本任务在 `feature/W5-backend-interactive` 分支开发。

---

## 二、产出

| 产出 | 文件 | 说明 |
|:---|:---|:---|
| interactive 出题函数 | `backend/app/agents/diagnostics.py` | 新增 `prepare_questions()` 公开函数，assess 路由直接调用不走工作流 |
| 动态反馈纯函数 | `backend/app/agents/diagnostics.py` | 新增 `decide_feedback()`：≥0.8 advance / 0.5-0.8 remediate / <0.5 scaffold |
| diagnostics_node 修复 | `backend/app/agents/diagnostics.py` | interactive 模式出题后即返回，不再判全错画像污染工作流 |
| assess 路由分流 | `backend/app/api/diagnostics.py` | mode=interactive 调 prepare_questions 出题+缓存；mode=demo 走工作流 |
| submit 路由 | `backend/app/api/diagnostics.py` | 新增 `POST /api/diagnostics/submit`：取缓存题目→判分→画像→动态反馈 |
| 会话缓存 | `backend/app/api/diagnostics.py` | 模块级 dict + LRU（上限100），按 session_id 缓存题目+nodes |
| 单测 | `test_diagnostics_unit.py` + `test_submit_api.py` | decide_feedback 8 + submit API 集成 4 |
| 对接文档 | `docs/接口对接/A端后端对接文档.md` | §3.1 分流、新增 §3.3 submit、§6.4 W5 两步流程、§9 curl |

---

## 三、interactive 两步流程

```
B端                            A端
 │                              │
 │ POST /assess mode=interactive│
 │ ───────────────────────────→ │ prepare_questions() 出题
 │                              │ 缓存 session_id→{questions,nodes}
 │ ←── session_id + questions ──│
 │                              │
 │ (用户逐题作答)                │
 │                              │
 │ POST /submit {session_id,answers}
 │ ───────────────────────────→ │ 取缓存题目
 │                              │ _grade(questions, answers) 判分
 │                              │ _build_profile() 画像
 │                              │ decide_feedback() 动态反馈
 │ ←── profile+assessment+feedback
 │                              │
 │ (按 feedback.strategy 决定UI) │
```

**关键设计**：interactive 不走工作流、不经过 reviewer。用户亲自答题产出的画像无需审"画像合理性"（那是 demo 模式防 LLM 幻觉用的）。如需对生成内容审核，用 demo 模式。

---

## 四、动态反馈策略（对齐 orchestrator prompt 规则2）

| 正确率 | strategy | 含义 |
|:---|:---|:---|
| ≥ 0.8 | `advance` | 掌握良好，进下一节点或生成进阶挑战 |
| 0.5 ~ 0.8 | `remediate` | 部分掌握，触发降维解释（换角度重讲）|
| < 0.5 | `scaffold` | 掌握不足，标记困难节点，补前置基础知识 |

`decide_feedback` 为纯函数，已单测覆盖边界（0.8/0.5/0/全对/total=0）。

---

## 五、关键设计决策

1. **interactive 不走工作流**：避免 diagnostics_node 内判全错画像污染 reviewer→打回循环。assess 路由 mode 分流，interactive 直接调纯函数出题。W4 demo 工作流不受影响。
2. **会话缓存用模块级 dict + LRU**：开发期够用，题目+nodes 跨 assess→submit 两请求。生产可换 Redis。上限 100 条防内存泄漏。
3. **答案数量自动对齐**：`answers` 不足补空串（判错），多余截断，避免 LLM 出题数与前端作答数不一致导致 _grade 越界。
4. **复用 W4 纯函数**：submit 直接调 `_grade`/`_build_profile`，不重复实现判分逻辑，BUG-022/025 的治本修复自动继承。

---

## 六、测试覆盖

```
112 passed, 61 warnings in 2.54s   (原 100 → +12)

新增:
  test_diagnostics_unit.py  +8  decide_feedback (advance/remediate/scaffold/边界/0/全对/total=0)
  test_submit_api.py         4  assess出题→submit判分闭环 / 404 / 答案对齐
```

submit API 集成测试用 FastAPI TestClient + monkeypatch 绕过 LLM/Neo4j，验证完整两步闭环。

验证：FastAPI app 14 路由（2 diagnostics + 10 graph + health + version）注册；validate_data 0 错误。

---

## 七、对 B 端影响

对接文档 §3.3 + §6.4 已更新。B 端 W5 答题页：
1. `POST /assess` (mode=interactive) 取 session_id + questions
2. 渲染答题组件，用户作答
3. `POST /submit` 提交，按 `feedback.strategy` 决定下一步 UI

---

## 八、遗留

- 动态反馈的"补前置/降维重讲"当前返回策略，内容再生成可后续对接 content_generator 按 strategy 重新生成（复用现有节点）。
- 会话缓存为内存态，服务重启丢失（开发期可接受）。
- submit 返回的画像未走 reviewer，如需审核可后续加开关。
- datetime.utcnow() 弃用警告后续批量迁移。
