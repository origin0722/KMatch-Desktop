"""AgentState llm_overrides 字段 + make_initial_state 透传单测。"""
from app.agents.state import make_initial_state


def test_make_initial_state_defaults_no_overrides():
    """无 llm_overrides 参数时 state 不含该字段（total=False）。"""
    state = make_initial_state(target_direction="Python 入门")
    assert "llm_overrides" not in state
    assert state["target_direction"] == "Python 入门"


def test_make_initial_state_with_overrides():
    """llm_overrides 参数透传进 state。"""
    overrides = {"api_key": "sk-x", "base_url": "https://x/v1", "model": "m"}
    state = make_initial_state(target_direction="Python 入门", llm_overrides=overrides)
    assert state["llm_overrides"] == overrides
