"""主控调度编排单测 — 用 mock 节点验证图流转逻辑，不调 LLM/Neo4j。

直接替换 StateGraph 的节点函数为可控 mock，验证:
  - 审核通过 → 一次流转即结束
  - 审核不通过 & 未超限 → 打回重新检测（循环）
  - 审核不通过 & 超过 max_retries → 强制结束（降级）
"""

from unittest.mock import MagicMock

from langgraph.graph import END, StateGraph

from app.agents.state import AgentState, make_initial_state


def _build_test_graph(diag_fn, review_fn):
    """复用 orchestrator 的图结构，但注入 mock 节点函数。"""
    workflow = StateGraph(AgentState)
    workflow.add_node("diagnostics", diag_fn)
    workflow.add_node("reviewer", review_fn)
    workflow.add_node("finish", lambda s: {"orchestration_log": ["done"]})
    workflow.set_entry_point("diagnostics")
    workflow.add_edge("diagnostics", "reviewer")

    def decide(state):
        if state.get("review_results", {}).get("passed"):
            return "finish"
        if state.get("retry_count", 0) >= state.get("max_retries", 3):
            return "finish"
        return "diagnostics"

    workflow.add_conditional_edges("reviewer", decide, {"diagnostics": "diagnostics", "finish": "finish"})
    workflow.add_edge("finish", END)
    return workflow.compile()


def test_pass_on_first_review():
    """审核首轮通过 → diagnostics→reviewer→finish，retry_count=1。"""
    def diag(s):
        return {"user_profile": {"name": "x"}, "orchestration_log": ["diag"]}

    def review(s):
        return {"review_results": {"passed": True}, "retry_count": s.get("retry_count", 0) + 1,
                "orchestration_log": ["review pass"]}

    app = _build_test_graph(diag, review)
    result = app.invoke(make_initial_state("test"), {"configurable": {"thread_id": "t1"}})

    assert result["review_results"]["passed"] is True
    assert result["retry_count"] == 1


def test_retry_until_pass():
    """前2轮不通过、第3轮通过 → 重试到通过，retry_count=3。"""
    call_count = {"n": 0}

    def diag(s):
        call_count["n"] += 1
        return {"user_profile": {"name": "x"}, "orchestration_log": [f"diag#{call_count['n']}"]}

    def review(s):
        retry = s.get("retry_count", 0) + 1
        passed = retry >= 3
        return {"review_results": {"passed": passed}, "retry_count": retry,
                "orchestration_log": [f"review#{retry} pass={passed}"]}

    app = _build_test_graph(diag, review)
    result = app.invoke(make_initial_state("test", max_retries=3), {"configurable": {"thread_id": "t2"}})

    assert result["review_results"]["passed"] is True
    assert result["retry_count"] == 3
    assert call_count["n"] == 3  # diagnostics 被调用 3 次


def test_force_end_after_max_retries():
    """始终不通过 & 达到 max_retries → 强制结束，最终 passed=False。"""
    def diag(s):
        return {"user_profile": {"name": "x"}, "orchestration_log": ["diag"]}

    def review(s):
        return {"review_results": {"passed": False}, "retry_count": s.get("retry_count", 0) + 1,
                "orchestration_log": ["review fail"]}

    app = _build_test_graph(diag, review)
    result = app.invoke(make_initial_state("test", max_retries=2), {"configurable": {"thread_id": "t3"}})

    assert result["review_results"]["passed"] is False
    assert result["retry_count"] == 2  # 达到上限后不再循环


# ============================================================
# 第3周: 三分支流转 (通过→graph_controller / 打回→diagnostics / 超限→finish)
# ============================================================

def _build_test_graph_v3(diag_fn, review_fn, graph_fn):
    """复用第3周 orchestrator 图结构 (含 graph_controller 节点)，注入 mock。"""
    workflow = StateGraph(AgentState)
    workflow.add_node("diagnostics", diag_fn)
    workflow.add_node("reviewer", review_fn)
    workflow.add_node("graph_controller", graph_fn)
    workflow.add_node("finish", lambda s: {"orchestration_log": ["done"]})
    workflow.set_entry_point("diagnostics")
    workflow.add_edge("diagnostics", "reviewer")

    def decide(state):
        if state.get("review_results", {}).get("passed"):
            return "graph_controller"
        if state.get("retry_count", 0) >= state.get("max_retries", 3):
            return "finish"
        return "diagnostics"

    workflow.add_conditional_edges(
        "reviewer", decide,
        {"graph_controller": "graph_controller", "diagnostics": "diagnostics", "finish": "finish"},
    )
    workflow.add_edge("graph_controller", "finish")
    workflow.add_edge("finish", END)
    return workflow.compile()


def test_pass_routes_to_graph_controller():
    """审核通过 → 进入 graph_controller 组装路径 → finish。"""
    graph_calls = {"n": 0}

    def diag(s):
        return {"user_profile": {"name": "x"}, "orchestration_log": ["diag"]}

    def review(s):
        return {"review_results": {"passed": True}, "retry_count": s.get("retry_count", 0) + 1,
                "orchestration_log": ["review pass"]}

    def graph_ctrl(s):
        graph_calls["n"] += 1
        return {"knowledge_graph": {"path_node_ids": ["PY-005"]},
                "orchestration_log": ["graph assembled"]}

    app = _build_test_graph_v3(diag, review, graph_ctrl)
    result = app.invoke(make_initial_state("test"), {"configurable": {"thread_id": "t4"}})

    assert result["review_results"]["passed"] is True
    assert graph_calls["n"] == 1  # graph_controller 被调用一次
    assert result["knowledge_graph"]["path_node_ids"] == ["PY-005"]


def test_fail_under_limit_skips_graph_controller():
    """审核未通过且未超限 → 打回 diagnostics，不进 graph_controller。"""
    graph_calls = {"n": 0}
    review_calls = {"n": 0}

    def diag(s):
        return {"user_profile": {"name": "x"}, "orchestration_log": ["diag"]}

    def review(s):
        review_calls["n"] += 1
        retry = s.get("retry_count", 0) + 1
        passed = retry >= 3  # 前两轮失败，第三轮通过
        return {"review_results": {"passed": passed}, "retry_count": retry,
                "orchestration_log": [f"review#{retry}"]}

    def graph_ctrl(s):
        graph_calls["n"] += 1
        return {"knowledge_graph": {"path_node_ids": []}, "orchestration_log": ["graph"]}

    app = _build_test_graph_v3(diag, review, graph_ctrl)
    result = app.invoke(make_initial_state("test", max_retries=3), {"configurable": {"thread_id": "t5"}})

    # 最终通过 → graph_controller 只在最后一次 (通过时) 调用一次
    assert result["review_results"]["passed"] is True
    assert review_calls["n"] == 3
    assert graph_calls["n"] == 1


def test_degraded_end_skips_graph_controller():
    """超 max_retries 仍不通过 → 降级 finish，graph_controller 从未调用。"""
    graph_calls = {"n": 0}

    def diag(s):
        return {"user_profile": {"name": "x"}, "orchestration_log": ["diag"]}

    def review(s):
        return {"review_results": {"passed": False}, "retry_count": s.get("retry_count", 0) + 1,
                "orchestration_log": ["review fail"]}

    def graph_ctrl(s):
        graph_calls["n"] += 1
        return {"knowledge_graph": {}, "orchestration_log": ["graph"]}

    app = _build_test_graph_v3(diag, review, graph_ctrl)
    result = app.invoke(make_initial_state("test", max_retries=2), {"configurable": {"thread_id": "t6"}})

    assert result["review_results"]["passed"] is False
    assert graph_calls["n"] == 0  # 降级路径不组装图谱


# ============================================================
# 第4周: 全流程流转 (画像通过→图谱→生成→内容审核→打回/交付)
# ============================================================

def _build_w4_graph(diag_fn, review_fn, graph_fn, gen_fn):
    """复用第4周 orchestrator 图结构 (含 content_generator)，注入 mock。"""
    workflow = StateGraph(AgentState)
    workflow.add_node("diagnostics", diag_fn)
    workflow.add_node("reviewer", review_fn)
    workflow.add_node("graph_controller", graph_fn)
    workflow.add_node("content_generator", gen_fn)
    workflow.add_node("finish", lambda s: {"orchestration_log": ["done"]})
    workflow.set_entry_point("diagnostics")
    workflow.add_edge("diagnostics", "reviewer")

    def in_content(s):
        gen = s.get("generated_content") or {}
        return bool(isinstance(gen, dict) and gen.get("resources"))

    def decide(s):
        review = s.get("review_results", {})
        passed = review.get("passed")
        over = s.get("retry_count", 0) >= s.get("max_retries", 3)
        if in_content(s):
            if passed:
                return "finish"
            if over:
                return "finish"
            return "content_generator"
        if passed:
            return "graph_controller"
        if over:
            return "finish"
        return "diagnostics"

    workflow.add_conditional_edges("reviewer", decide, {
        "graph_controller": "graph_controller",
        "content_generator": "content_generator",
        "diagnostics": "diagnostics",
        "finish": "finish",
    })
    workflow.add_edge("graph_controller", "content_generator")
    workflow.add_edge("content_generator", "reviewer")
    workflow.add_edge("finish", END)
    return workflow.compile()


def test_w4_full_flow_pass():
    """画像通过→图谱→生成→内容审核通过→交付 finish。"""
    gen_calls = {"n": 0}

    def diag(s):
        return {"user_profile": {"theory_level": 2}, "orchestration_log": []}

    def review(s):
        retry = s.get("retry_count", 0) + 1
        # 画像阶段首轮通过; 内容阶段首轮也通过
        in_content = bool((s.get("generated_content") or {}).get("resources"))
        passed = True
        return {"review_results": {"passed": passed}, "retry_count": retry,
                "orchestration_log": []}

    def graph_ctrl(s):
        return {"knowledge_graph": {"learning_path": [{"node_id": "PY-005"}]},
                "orchestration_log": []}

    def gen(s):
        gen_calls["n"] += 1
        return {"generated_content": {"resources": [{"content_type": "lecture"}]},
                "orchestration_log": []}

    app = _build_w4_graph(diag, review, graph_ctrl, gen)
    result = app.invoke(make_initial_state("test"), {"configurable": {"thread_id": "w4a"}})

    assert result["review_results"]["passed"] is True
    assert gen_calls["n"] == 1
    assert len(result["generated_content"]["resources"]) == 1


def test_w4_content_retry_loop():
    """内容审核首轮不通过→打回 content_generator→第二轮通过。"""
    gen_calls = {"n": 0}

    def diag(s):
        return {"user_profile": {"theory_level": 2}, "orchestration_log": []}

    def review(s):
        retry = s.get("retry_count", 0) + 1
        in_content = bool((s.get("generated_content") or {}).get("resources"))
        if not in_content:
            return {"review_results": {"passed": True}, "retry_count": retry,
                    "orchestration_log": []}
        # 内容阶段: 首轮(总retry=2)不通过, 次轮(总retry=3)通过
        passed = retry >= 3
        return {"review_results": {"passed": passed}, "retry_count": retry,
                "orchestration_log": []}

    def graph_ctrl(s):
        return {"knowledge_graph": {"learning_path": [{"node_id": "PY-005"}]},
                "orchestration_log": []}

    def gen(s):
        gen_calls["n"] += 1
        return {"generated_content": {"resources": [{"content_type": "lecture"}]},
                "orchestration_log": []}

    app = _build_w4_graph(diag, review, graph_ctrl, gen)
    result = app.invoke(make_initial_state("test", max_retries=5), {"configurable": {"thread_id": "w4b"}})

    assert result["review_results"]["passed"] is True
    assert gen_calls["n"] == 2  # 生成2次 (首轮被打回)


def test_w4_content_degraded_end():
    """内容审核始终不通过 & 超限 → 降级 finish，不无限循环。"""
    gen_calls = {"n": 0}

    def diag(s):
        return {"user_profile": {"theory_level": 2}, "orchestration_log": []}

    def review(s):
        retry = s.get("retry_count", 0) + 1
        in_content = bool((s.get("generated_content") or {}).get("resources"))
        if not in_content:
            return {"review_results": {"passed": True}, "retry_count": retry,
                    "orchestration_log": []}
        return {"review_results": {"passed": False}, "retry_count": retry,
                "orchestration_log": []}

    def graph_ctrl(s):
        return {"knowledge_graph": {"learning_path": [{"node_id": "PY-005"}]},
                "orchestration_log": []}

    def gen(s):
        gen_calls["n"] += 1
        return {"generated_content": {"resources": [{"content_type": "lecture"}]},
                "orchestration_log": []}

    app = _build_w4_graph(diag, review, graph_ctrl, gen)
    result = app.invoke(make_initial_state("test", max_retries=3), {"configurable": {"thread_id": "w4c"}})

    assert result["review_results"]["passed"] is False
    # 画像1轮 + 内容打回至多 max_retries 轮, gen 不会无限
    assert gen_calls["n"] <= 3


# ============================================================
# BUG-031: 内容阶段空资源不回退画像模式 (防无限循环)
# ============================================================

def test_w4_empty_content_does_not_loop_back_to_profile(monkeypatch):
    """画像通过→图谱→生成(空资源)→reviewer 内容模式判不通过→超限降级 finish，不回退画像模式无限循环。"""
    gen_calls = {"n": 0}
    review_calls = {"n": 0}

    def diag(s):
        return {"user_profile": {"theory_level": 2}, "orchestration_log": []}

    def review(s):
        review_calls["n"] += 1
        retry = s.get("retry_count", 0) + 1
        in_content = bool(s.get("content_phase_entered"))
        if not in_content:
            # 画像阶段: 通过
            return {"review_results": {"passed": True}, "retry_count": retry, "orchestration_log": []}
        # 内容阶段: 资源空 → 判不通过 (模拟 BUG-031 修复后的 reviewer 行为)
        return {"review_results": {"passed": False}, "retry_count": retry, "orchestration_log": []}

    def graph_ctrl(s):
        return {"knowledge_graph": {"learning_path": [{"node_id": "PY-005"}]}, "orchestration_log": []}

    def gen(s):
        gen_calls["n"] += 1
        # 始终返回空 resources (路径空/生成失败场景) + content_phase_entered=True
        return {"generated_content": {"resources": []}, "content_phase_entered": True,
                "orchestration_log": []}

    app = _build_w4_graph(diag, review, graph_ctrl, gen)
    result = app.invoke(make_initial_state("test", max_retries=3), {"configurable": {"thread_id": "bug31"}})

    # 不无限循环: 最终 passed=False, 降级结束
    assert result["review_results"]["passed"] is False
    # content_generator 被调用但不无限 (受 max_retries 约束)
    assert gen_calls["n"] <= 3
    assert review_calls["n"] <= 4  # 画像1 + 内容审核若干
