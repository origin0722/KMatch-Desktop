# 2026-08-18 — Phase 0：结构化 Agent 运行事件（借鉴工作流插件可观测性）

**会话目标**：把"Agent 协同"面板从正则抠日志升级为结构化事件驱动，并修复 demo 流式期间协同卡片空白。这是"工作流插件借鉴方案"（对照 dsh_workflow / dsh-deepseek-flow 逐文件对比得出的 5 阶段）的第一阶段，为 Phase 1（耐久 run 记录）打地基。

## 一、产出

| 产出 | 文件 | 说明 |
|:---|:---|:---|
| 编排日志结构化分类 | `backend/app/agents/log_events.py`（新） | 纯函数 `to_log_event`：emoji 日志行 → `{type, agent, status, message, log}`；agent 解析优先级处理「审核学情检测…」歧义行 |
| SSE / 响应注入事件 | `backend/app/api/diagnostics.py` | demo SSE progress 加 `log_events`（实时）、done 加 `orchestration_events`；/assess demo 与 /submit 响应模型加 `orchestration_events`（向后兼容，原 `orchestration_log` 不变） |
| 前端存储 | `frontend/src/stores/assessment.js` | 新增 `orchestrationEvents`；demo 流式期间实时累加事件+日志（去重）——修复 2-4 分钟流式期间 Agent 协同卡片"尚无协同记录" |
| 状态推导 | `frontend/src/composables/useAgentStatus.js` | 结构化事件优先推导状态，正则降级；`pipelineRunning` 计入事件；`retryCount` 仍从日志合并 |
| 后端单测 | `backend/tests/test_log_events.py`（新） | 13 用例：agent 解析/终态/进行中/清洗/歧义行 |
| 前端单测 | `frontend/src/__tests__/useAgentStatus-events.test.js`（新） | 6 用例：事件驱动/优先级/降级结束/retry 合并/正则兜底 |
| 存量测试对齐 | `frontend/__tests__/session-store.test.js` + `stores/session.js` | issue-06 后 phase 判断前置，旧测试仍期待 `agent > quiz` 属存量不一致（基线验证证实非本次引入）；对齐测试与注释到真实语义 `quiz > agent` |

## 二、借鉴来源（对照结论）

对照 `dsh_workflow`（定义态+耐久运行层）与 `dsh-deepseek-flow`（可视画布编辑器）的逐文件分析：两者的执行可观测性靠**结构化生命周期事件**（run/phase/agent-start/agent-end）而非日志文本。本次先落地这个事件词汇，画布/流程资产化留待 Phase 1-4。

## 三、测试

- 后端：`pytest backend/tests/test_log_events.py`（13 passed）+ `test_assess_sse_api.py`（4 passed）
- 前端：useAgentStatus-events / useAgentStatus / stage-agent-collab / session-store / assessment-store 全绿；全量 362/364，2 个失败（useChatStream abort 时序、fs-write-guard 环境路径）为基线即存在的存量问题（stash 隔离验证实证）

## 四、待办（Phase 1-4）

- Phase 1：耐久 run 记录（`data/workflow_runs/<session>/run.json + events.jsonl`）＋ chat run 节点折叠卡
- Phase 2：学习流程即数据（capsule v1 子集：manifest/intent/inputs + preflight）
- Phase 3：G6 流程画布（只读进度 DAG → 可编辑拓扑 + 事务审查）
- Phase 4：逻辑门自适应分支（确定性布尔求值）
