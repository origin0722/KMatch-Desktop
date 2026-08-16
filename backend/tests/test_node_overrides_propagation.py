"""验证工作流节点入口从 state.llm_overrides set ContextVar，深层 LLM helper 用到 overrides。

三个 LLM 调用节点 (diagnostics/reviewer/content_generator) 入口须从 state["llm_overrides"]
set _current_overrides，退出 reset；content_generator 的 ThreadPoolExecutor 工作线程不继承
ContextVar，_safe_generate 须在 worker 线程内重新 set。

diagnostics/reviewer 用 spy 拦截 llm_configured() 捕获节点执行期间 ContextVar 的值——
仅断言 reset 无法区分「set 后 reset」与「从未 set」，后者是未实现的行为，必须被测出。
"""
import app.agents.llm as llm_module
from app.agents.llm import _current_overrides


def _make_fake_kg():
    """返回一个不触网的假 KG（节点函数早期会 return，不真正调 LLM）。"""
    class FakeKg:
        def get_node(self, nid):
            return None
    return FakeKg()


def test_diagnostics_node_sets_contextvar_from_state():
    """diagnostics_node 入口把 state.llm_overrides set 进 ContextVar，退出 reset。"""
    overrides = {"api_key": "sk-agent", "base_url": "https://x/v1", "model": "m"}
    from app.agents import diagnostics as diag
    node = diag.diagnostics_node(_make_fake_kg())
    state = {"target_direction": "x", "mode": "demo", "known_topics": [],
             "llm_overrides": overrides}

    # spy: 节点体内 llm_configured() 被调用时捕获 ContextVar 当前值。
    # diagnostics_node 进入 _node_body 后第一处逻辑就是 `if not llm_configured():`，
    # 此时 ContextVar 应已被 _node wrapper set 为 overrides。
    captured = []
    original = diag.llm_configured

    def spy_llm_configured():
        captured.append(_current_overrides.get())
        return original()

    diag.llm_configured = spy_llm_configured

    # 节点外 ContextVar 应为 None
    assert _current_overrides.get() is None
    try:
        node(state)
    except Exception:
        pass  # 假 kg 可能抛，只关心 ContextVar 是否被 set 且退出后 reset
    finally:
        diag.llm_configured = original

    # 节点退出后 ContextVar 必须 reset 回 None
    assert _current_overrides.get() is None, "节点退出后 ContextVar 未 reset"
    # 节点入口已 set ContextVar（llm_configured 调用时读到 overrides 而非 None）
    assert captured, "spy 未被调用，节点未执行到 llm_configured"
    assert any(v == overrides for v in captured), \
        f"节点内 ContextVar 未 set 为 overrides, captured={captured}"


def test_reviewer_node_resets_contextvar_after_exit():
    """reviewer_node 入口 set ContextVar，空画像早返后仍 reset。"""
    from app.agents import reviewer as rev
    node = rev.reviewer_node(_make_fake_kg())
    # 空 profile → 早返（不调 LLM），但 set/reset 仍应平衡且 set 生效
    overrides = {"api_key": "sk-x", "model": "m"}
    state = {"user_profile": {}, "assessment": {}, "retry_count": 0,
             "llm_overrides": overrides}

    # spy: 空画像分支内 `reason = ... if not llm_configured() else ...` 会调 llm_configured，
    # 此时 ContextVar 应已被 set。
    captured = []
    original = rev.llm_configured

    def spy_llm_configured():
        captured.append(_current_overrides.get())
        return original()

    rev.llm_configured = spy_llm_configured

    assert _current_overrides.get() is None
    try:
        node(state)
    finally:
        rev.llm_configured = original

    assert _current_overrides.get() is None, "节点退出后 ContextVar 未 reset"
    assert captured, "spy 未被调用，节点未执行到 llm_configured"
    assert any(v == overrides for v in captured), \
        f"节点内 ContextVar 未 set 为 overrides, captured={captured}"


def test_content_generator_safe_generate_sets_contextvar_in_worker_thread():
    """_safe_generate 在 ThreadPoolExecutor 工作线程内重新 set ContextVar。

    ContextVar 不跨线程传播；验证 worker 线程内 _current_overrides.get() == overrides。
    """
    from app.agents.content_generator import content_generator_node
    captured = []
    import app.agents.content_generator as cg

    def fake_generate_one(node, theory_level, content_type, correction_hint=""):
        captured.append(_current_overrides.get())
        return {}

    original = cg._generate_one
    cg._generate_one = fake_generate_one
    try:
        overrides = {"api_key": "sk-w", "model": "wm"}
        node = content_generator_node(_make_fake_kg())
        state = {
            "user_profile": {"theory_level": 2},
            "knowledge_graph": {"learning_path": [{"node_id": "N1", "difficulty": 1}]},
            "llm_overrides": overrides,
        }
        node(state)
    finally:
        cg._generate_one = original

    assert len(captured) > 0, "worker 未执行"
    for ctx_val in captured:
        assert ctx_val == overrides, f"worker 线程内 ContextVar 未 set: {ctx_val}"
