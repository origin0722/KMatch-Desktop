"""
KMatch 多智能体模块

Agent 节点 (1 主控 + 6 子):
  - orchestrator: 主控调度 (本模块 build_workflow 编排)
  - diagnostics:  学情检测
  - reviewer:     内容审核 (双模式: 画像/生成内容)
  - graph_controller: 知识图谱管控 (第3周已实现)
  - content_generator: 领域知识生成 (第4周已实现)
  - code_reviewer: 代码审查 (第6周实现, 场景二 Step6①)
  - code_tester:  代码测试 (第6周实现, 场景二 Step6②)

第2-4周交付: 学情检测→画像审核→图谱组装→内容生成→内容审核全流程闭环（可 Postman 触发）。
"""

from app.agents.orchestrator import build_workflow
from app.agents.state import AgentState, make_initial_state

__all__ = ["build_workflow", "AgentState", "make_initial_state"]
