# 2026-08-18 — PU 入库 · anthropic 连通性 · Agent 协同降级可视化

**会话目标**：收尾三件——① 把动态建域产生的 PU 迷你域入库；② 统一 API 设置的「测试连通性」接通 anthropic 协议；③ Agent 协同面板把"降级/打回"可视化出来。

## 一、PU 知识库产物入库

- 内容：`data/knowledge_base/nodes/_manual_nodes.json`（+10 节点，`category=动态领域`，石油开采迷你域 PU-001~PU-010）+ `questions/PU-*.json`（10 题）。
- 合法性：`scripts/validate_data.py` 全过（292 节点 / 648 题 / 11 画像，0 错误）。按"动态建域产物入库"先例（OO 面向对象域）提交。

## 二、统一 API 设置 · anthropic 连通性

- `backend/app/api/agents.py`：`/api/agents/ping` 增加 `protocol` 字段——`anthropic` 走 `AsyncAnthropic.messages.create`，`openai` 走 `ChatOpenAI`。
- 前端：`apiSettings.testConnectivity` 透传 `protocol`；`ApiSettings` 各行的「测试连通性」按厂商协议计算（统一行按提供方 protocol、AI 助手行按 `providerMeta().protocol`、Agent 行固定 openai）。
- 测试：后端 agents ping 双协议 4 例；前端 store/挂载各补 protocol 断言（含 anthropic 行）。

## 三、Agent 协同 · 降级可视化

- `useAgentStatus`：把"降级"提为独立状态——`run-end degraded` → orchestrator **degraded**（原为 failed）；事件与正则兜底两路都识别 `⚠️` 降级到对应 Agent。
- `useFlowStatus` 定义驱动聚合补 degraded；`StageAgent` 徽章 `⚠️ 降级` + 行配色；`FlowDiagram` 节点降级配色（区别于 running）。
- 打回轮次（retryCount）沿用："打回 ×N" 徽章已在行内展示。

## 四、测试

- 后端：`test_agents_ping`（+anthropic 2 例）+ `test_prompt_contract` = 10 passed
- 前端：全量 **409/409**（events +2 降级用例；经手 7 套件 38/38）
