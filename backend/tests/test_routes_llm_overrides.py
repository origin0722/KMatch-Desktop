"""验证 4 个 diagnostics 路由从请求体读 llm_overrides 并下传。

用 monkeypatch 拦截 make_initial_state / _grade / _build_profile / regenerate_for_feedback，
断言它们收到 overrides。KG 用假对象避免 Neo4j。

注意: 路由层 `from app.agents.diagnostics import _grade` 按名导入, monkeypatch 必须落在
路由模块 app.api.diagnostics 上才生效 (patch app.agents.diagnostics._grade 不影响路由绑定)。
"""
import pytest

import app.api.diagnostics as api_diag
from app.api.diagnostics import AssessRequest, SubmitRequest, FeedbackRequest


class FakeKg:
    def test_connection(self):
        return True

    def get_node(self, nid):
        return None

    def assemble_learning_path(self, **kw):
        return []

    def get_by_difficulty(self, *a, **kw):
        return []


def _patch_appstate_kg(monkeypatch):
    """给 app.state 注入假 KG + 清 workflow, 用 monkeypatch 自动还原。"""
    from app.main import app
    monkeypatch.setattr(app.state, "kg", FakeKg(), raising=False)
    monkeypatch.setattr(app.state, "workflow", None, raising=False)


@pytest.fixture(autouse=True)
def _clear_sessions():
    """每个测试前后清空 interactive 会话缓存, 避免跨测试污染。"""
    api_diag._INTERACTIVE_SESSIONS.clear()
    yield
    api_diag._INTERACTIVE_SESSIONS.clear()


def test_assess_request_model_accepts_llm_overrides():
    req = AssessRequest(target_direction="x", llm_overrides={"api_key": "k"})
    assert req.llm_overrides == {"api_key": "k"}


def test_assess_demo_passes_overrides_to_initial_state(monkeypatch):
    _patch_appstate_kg(monkeypatch)
    captured = {}

    class FakeWorkflow:
        def invoke(self, initial, config):
            captured["overrides"] = initial.get("llm_overrides")
            return {"user_profile": {}, "assessment": {}, "review_results": {},
                    "knowledge_graph": {}, "generated_content": {}, "orchestration_log": []}

    from app.main import app
    monkeypatch.setattr(app.state, "workflow", FakeWorkflow(), raising=False)

    from fastapi.testclient import TestClient
    client = TestClient(app)
    overrides = {"api_key": "sk-a", "model": "am"}
    r = client.post("/api/diagnostics/assess",
                    json={"target_direction": "x", "mode": "demo",
                          "llm_overrides": overrides})
    assert r.status_code == 200, r.text
    assert captured["overrides"] == overrides


def test_submit_passes_overrides_to_grade(monkeypatch):
    """submit 直调 _grade；用 use_llm_overrides 包裹，_grade 内 get_default_chat_model 读到。"""
    from app.agents.llm import _current_overrides

    seen = {}

    def fake_grade(questions, answers):
        seen["ctx"] = _current_overrides.get()
        return {"per_node": {}, "correct_count": 0, "total_count": len(questions)}

    def fake_build_profile(target, nodes, grading, questions=None):
        return {"theory_level": 1}

    # 路由层 from app.agents.diagnostics import _grade — patch 路由模块绑定才生效
    monkeypatch.setattr(api_diag, "_grade", fake_grade)
    monkeypatch.setattr(api_diag, "_build_profile", fake_build_profile)
    _patch_appstate_kg(monkeypatch)

    # 预置 interactive 会话缓存
    api_diag._INTERACTIVE_SESSIONS["s1"] = {
        "questions": [{"node_id": "N1", "question": "q", "answer": "a"}],
        "nodes": [{"node_id": "N1"}], "target_direction": "x", "known_topics": [],
        "created_at": "2026-01-01T00:00:00",
    }

    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    overrides = {"api_key": "sk-s", "model": "sm"}
    r = client.post("/api/diagnostics/submit",
                    json={"session_id": "s1", "answers": ["a"], "llm_overrides": overrides})
    assert r.status_code == 200, r.text
    assert seen["ctx"] == overrides
    # 路由退出后 ContextVar reset
    assert _current_overrides.get() is None


def test_feedback_passes_overrides_to_regenerate(monkeypatch):
    """feedback 直调 regenerate_for_feedback；用 use_llm_overrides 包裹。"""
    from app.agents.llm import _current_overrides

    seen = {}

    def fake_regenerate(strategy, profile, learning_path, kg):
        seen["ctx"] = _current_overrides.get()
        return {"resources": [], "node_count": 0}

    monkeypatch.setattr(api_diag, "regenerate_for_feedback", fake_regenerate)
    _patch_appstate_kg(monkeypatch)

    api_diag._INTERACTIVE_SESSIONS["s1"] = {
        "nodes": [{"node_id": "N1"}], "target_direction": "x",
        "created_at": "2026-01-01T00:00:00",
    }

    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    overrides = {"api_key": "sk-f", "model": "fm"}
    r = client.post("/api/diagnostics/feedback",
                    json={"session_id": "s1", "strategy": "remediate",
                          "profile": {"theory_level": 1}, "llm_overrides": overrides})
    assert r.status_code == 200, r.text
    assert seen["ctx"] == overrides
    assert _current_overrides.get() is None
