# 00 全局协约（共享契约）— Agent 提示词引用页

> 本文件是多份 Agent 提示词（01-08）与代码之间的**共享单一来源**：JSON 严格性、溯源标记、
> 日志/事件词汇、阈值与常量。任一文件与代码侧改动，`test_prompt_contract`（backend/tests/
> test_prompt_contract.py）会钉死一致性——请勿在这一页与代码之间只改一边。
>
> 各提示词头部引用本页；本页不定义单个 Agent 的职责，只定义"大家都要守的规矩"。

## 1. JSON 严格性

- 面向模型的输出为**结构化的 JSON**（画像/审核报告/测试报告/生成资源等）；禁止在 JSON 外附加
  多余文字、Markdown 代码围栏或解释（除非该段明确指定散文本）。
- 后端按 `parse_llm_json` + conforming 兜底接单次修复；但提示词应先保证"只吐 JSON、字段齐全"，
  不要把兜底当常态。
- 未知/缺省字段按契约范围处理，不得臆造图谱外字段。

## 2. 溯源标记

- 生成内容每处知识依据标注 `[ref: <NODE_ID>.<field>[<idx>]]`（如 `[ref: PY-012.key_points[2]]`）。
- 打回/审核的 `source_node`/`related_node` 必须是真实存在的图谱节点 id。

## 3. 日志与事件词汇（对齐 `log_events.to_log_event`）

- 各 Agent 产出的 `orchestration_log` 行建议带语义前缀，便于 `to_log_event` 归类：
  - `agent-start`（开始/组装/判分等起点）、`agent-end`（✅ 完成通过）、`error`（❌ 失败）、
    `info`（其余）、`run-end`（流程结束，orchestrator）。
  - 状态：`running` / `done` / `failed` / `degraded`。
- 降级语义：⚠️ = 降级（如 LLM 未配置/超重试降级）→ 记为 `degraded`（区别于失败）。

## 4. 阈值与常量（代码同步来源）

| 常量 | 值 | 出处 |
|:---|:---|:---|
| 内容/代码审核通过阈值 | `0.85` | `settings.REVIEW_PASS_THRESHOLD` |
| 打回最大轮数 | `3` | orchestrator 规则3 / `max_retries` |
| LLM 超时重试次数 | `2` | `llm.py` `ChatOpenAI(max_retries=2)` |
| 掌握度分段 | `≥0.8=known`，`<0.8=weak` | `diagnostics` 三段制 `mastery` |
| 反馈分档 | `≥0.8→advance / ≥0.5→remediate / <0.5→scaffold` | `decide_feedback` ↔ 流程定义 `strategy` 决策 |

## 5. 与流程定义（workflow_def）对齐

- 01 orchestrator 的流转规则与 `workflow_def` 的 `scene1-loop / scene1-interactive / scene2-project`
  阶段拓扑保持一致；阶段 `label` 可作为 SSE 进度文案（`_stage_labels`）。
- 决策类分支（如反馈策略）优先用流程定义里的 `decisions`（确定性求值，不跑 Agent）。

## 6. 质量护栏（跨 Agent）

- 幻觉治理：仅用节点事实（summary/key_points/common_mistakes），禁编造实现细节/版本号/性能数；
  先锚定后展开；`unverified_claims` 自声明；代码示例心算自检。
- 安全硬规则（场景二）：`eval/exec/compile/os.system/subprocess/pickle` 高危一票否决（AST 预检）。
- 动态建域（08）：恰好 10 节点、顺序无环、禁编版本/性能数、不纳入 M5 指标。
- 独立裁判（judge）与生成/审核**解耦**：只喂内容+声称溯源+图谱事实，不喂生成过程与结论。
