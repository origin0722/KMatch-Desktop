"""全局 State 单测 — 验证字段默认值与日志 reducer 合并行为。"""

from app.agents.state import _append_log, make_initial_state


def test_make_initial_state_defaults():
    """初始状态应填充默认值，画像/审核为空待节点填充。"""
    state = make_initial_state(target_direction="Python 入门")

    assert state["target_direction"] == "Python 入门"
    assert state["mode"] == "demo"
    assert state["scene"] == "no_project"
    assert state["known_topics"] == []
    assert state["user_profile"] == {}
    assert state["assessment"] == {}
    assert state["review_results"] == {"passed": False}
    assert state["retry_count"] == 0
    assert state["max_retries"] == 3
    assert state["orchestration_log"] == []
    assert state["session_id"]  # 非空 uuid


def test_make_initial_state_custom():
    """自定义参数应透传。"""
    state = make_initial_state(
        target_direction="爬虫",
        mode="interactive",
        known_topics=[{"node_id": "PY-001", "mastery": 0.9}],
        max_retries=5,
    )
    assert state["mode"] == "interactive"
    assert state["known_topics"][0]["node_id"] == "PY-001"
    assert state["max_retries"] == 5


def test_append_log_merges():
    """orchestration_log 的 reducer 应把右值追加到左值，而非覆盖。"""
    left = ["a", "b"]
    right = ["c"]
    assert _append_log(left, right) == ["a", "b", "c"]


def test_append_log_handles_none():
    """reducer 应容忍 None（节点可能未返回日志）。"""
    assert _append_log(None, ["x"]) == ["x"]
    assert _append_log(["x"], None) == ["x"]
    assert _append_log(None, None) == []
