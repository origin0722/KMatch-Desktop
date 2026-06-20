"""
主控调度 Agent (Orchestrator)

对齐 data/prompts/01_orchestrator_agent.txt。

职责: 用 LangGraph StateGraph 编排无项目场景全流程:
  学情检测 → 画像审核 → 图谱组装 → 内容生成 → 内容审核 → (打回/通过)

流转规则（对齐 orchestrator prompt 规则1/3）:
  - 画像审核通过 → graph_controller 组装学习路径
  - 画像审核不通过 & retry<max → 打回 diagnostics 重新检测
  - 画像通过 → content_generator 生成资源 → reviewer 内容审核
  - 内容审核通过 → END
  - 内容审核不通过 & retry<max → 打回 content_generator 重新生成
  - 任一阶段 retry ≥ max_retries → 强制 END，降级"待人工审核"

reviewer 双模式 (BUG-016): state 无 generated_content.resources 审画像，有则审生成内容。
_decide_next 据 state 是否进入内容阶段决定打回目标 (diagnostics / content_generator)。
code_tester 第6周接入。
"""

from datetime import datetime
from typing import Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from app.agents.content_generator import content_generator_node
from app.agents.diagnostics import diagnostics_node
from app.agents.graph_controller import graph_controller_node
from app.agents.reviewer import reviewer_node
from app.agents.state import AgentState
from app.graph.engine import KnowledgeGraph
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _in_content_phase(state) -> bool:
    """是否已进入内容阶段 (content_generator 已执行过)。决定 reviewer 打回目标。

    与 reviewer.content_mode 判据对齐: 用 content_phase_entered 标志, 而非 resources 非空。
    BUG B8: 旧实现用 resources 非空判, 但 content_generator 空路径时 content_phase_entered=True
    且 resources=[] → reviewer 走内容模式判不通过, 路由却误判画像阶段 → diagnostics 重试
    (每轮烧 3 次 LLM, 且修不了空路径), 直到 retry 上限才结束。
    """
    return bool(state.get("content_phase_entered"))


def _has_delivered_content(state) -> bool:
    """是否实际交付了学习资源 (resources 非空)。用于结束文案, 区分空路径。"""
    gen = state.get("generated_content") or {}
    return bool(isinstance(gen, dict) and gen.get("resources"))


def _finish(state) -> dict:
    """结束节点: 记录最终状态。"""
    review = state.get("review_results", {})
    passed = review.get("passed", False)
    retry = state.get("retry_count", 0)
    max_r = state.get("max_retries", 3)
    has_content = _has_delivered_content(state)

    if passed:
        subject = "内容审核通过 + 学习资源已交付" if has_content else "画像审核通过 + 学习路径已组装"
        msg = f"✅ 流程结束 ({subject})"
    elif retry >= max_r:
        msg = f"⚠️ 流程结束 (超过最大重试 {max_r} 轮，降级为待人工审核)"
    else:
        msg = "✅ 流程结束"

    return {"orchestration_log": [f"[{datetime.utcnow().isoformat()}] {msg}"]}


def _decide_after_review(state) -> Literal["graph_controller", "content_generator", "diagnostics", "finish"]:
    """reviewer 出边: 据审核对象与结果分流。

    画像阶段:
      通过 → graph_controller；未通过&未超限 → diagnostics；超限 → finish
    内容阶段:
      通过 → finish；未通过&未超限 → content_generator；超限 → finish
    """
    review = state.get("review_results", {})
    passed = review.get("passed")
    over_limit = state.get("retry_count", 0) >= state.get("max_retries", 3)

    if _in_content_phase(state):
        if passed:
            return "finish"  # 内容审核通过 → 交付
        if over_limit:
            return "finish"  # 降级
        return "content_generator"  # 打回重新生成
    else:
        # 画像阶段
        if passed:
            # BUG-031 止血: 画像通过但已超 retry 上限 → 降级结束 (防无限循环)
            if over_limit:
                return "finish"
            return "graph_controller"
        if over_limit:
            return "finish"
        return "diagnostics"


def build_workflow(kg: KnowledgeGraph):
    """构建并编译多 Agent 协同图。

    Args:
        kg: KnowledgeGraph 实例（由 main.py lifespan 注入全局单例）

    Returns:
        编译后的 LangGraph 可执行图（带 MemorySaver checkpointer）
    """
    workflow = StateGraph(AgentState)

    # 节点
    workflow.add_node("diagnostics", diagnostics_node(kg))
    workflow.add_node("reviewer", reviewer_node(kg))
    workflow.add_node("graph_controller", graph_controller_node(kg))
    workflow.add_node("content_generator", content_generator_node(kg))
    workflow.add_node("finish", _finish)

    # 入口
    workflow.set_entry_point("diagnostics")

    # 学情检测 → 画像审核
    workflow.add_edge("diagnostics", "reviewer")

    # 画像审核 → 条件分支 (graph_controller / diagnostics / finish)
    workflow.add_conditional_edges(
        "reviewer",
        _decide_after_review,
        {
            "graph_controller": "graph_controller",
            "content_generator": "content_generator",
            "diagnostics": "diagnostics",
            "finish": "finish",
        },
    )

    # 图谱组装 → 内容生成
    workflow.add_edge("graph_controller", "content_generator")

    # 内容生成 → 内容审核 (复用 reviewer 节点，双模式自动切内容模式)
    workflow.add_edge("content_generator", "reviewer")

    # 结束
    workflow.add_edge("finish", END)

    return workflow.compile(checkpointer=MemorySaver())
