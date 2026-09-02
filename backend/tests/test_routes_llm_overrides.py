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

    def fake_build_profile(target, nodes, grading, questions=None, learning_style_quiz=None, practical_evidence=None, demographics=None, time_per_week=None, preferred_pace=None):
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

    def fake_regenerate(strategy, profile, learning_path, kg, **kwargs):
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


# ============================================================
# Task 6: learning + project 路由透传 llm_overrides
# ============================================================

def test_learning_report_request_accepts_llm_overrides():
    from app.api.learning import LearningReportRequest
    req = LearningReportRequest(session_id="s1", llm_overrides={"api_key": "k"})
    assert req.llm_overrides == {"api_key": "k"}


def test_project_review_request_accepts_llm_overrides():
    from app.api.project import ReviewRequest, TestRequest
    assert ReviewRequest(code="x", target_direction="t",
                         llm_overrides={"api_key": "k"}).llm_overrides == {"api_key": "k"}
    assert TestRequest(target_direction="t",
                       llm_overrides={"api_key": "k"}).llm_overrides == {"api_key": "k"}


def test_learning_report_passes_overrides_to_pipeline(monkeypatch):
    """learning report 路由把 llm_overrides 透传进 _run_report_pipeline (进而入 state,
    供 content_generator ThreadPoolExecutor worker 线程 re-set ContextVar)。
    路由层 use_llm_overrides 单独不够 — worker 不继承 ContextVar, 必须经 state 下传。"""
    import app.api.learning as learning_api

    seen = {}

    def fake_pipeline(profile, kg, llm_overrides=None, emit=None, cancel_check=None):
        seen["overrides"] = llm_overrides
        return {"knowledge_graph": {}, "generated_content": {}, "review_results": {},
                "orchestration_log": []}

    monkeypatch.setattr(learning_api, "_run_report_pipeline", fake_pipeline)
    monkeypatch.setattr(learning_api, "build_learning_report",
                        lambda *a, **k: {})  # 纯函数替身, 避免 FakeKg 缺方法
    _patch_appstate_kg(monkeypatch)

    api_diag._INTERACTIVE_SESSIONS["s1"] = {
        "profile": {"theory_level": 1}, "target_direction": "x",
        "created_at": "2026-01-01T00:00:00",
    }

    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    overrides = {"api_key": "sk-l", "model": "lm"}
    r = client.post("/api/learning/report",
                    json={"session_id": "s1", "llm_overrides": overrides})
    assert r.status_code == 200, r.text
    assert seen["overrides"] == overrides


def test_project_review_passes_overrides_to_review_code(monkeypatch):
    """project /review 路由把 llm_overrides 透传到 review_code (后者在 llm_review_code
    内用 use_llm_overrides 包裹 — 直调路径, ContextVar 在 agent 函数内 set)。"""
    import app.api.project as project_api
    from app.agents.llm import _current_overrides

    seen = {}

    def fake_review_code(kg, code, td, kn, llm_overrides=None):
        seen["arg"] = llm_overrides
        seen["ctx"] = _current_overrides.get()  # 路由未 wrap, 应为 None
        return {"passed": True, "overall_score": 1.0, "threshold": 0.6,
                "dimensions": {}, "verdict": "pass", "retry_hint": "",
                "reviewed_at": "2026-01-01T00:00:00Z"}

    # 路由 from app.agents.code_reviewer import review_code — patch 路由模块绑定
    monkeypatch.setattr(project_api, "review_code", fake_review_code)
    _patch_appstate_kg(monkeypatch)

    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    overrides = {"api_key": "sk-r", "model": "rm"}
    r = client.post("/api/project/review",
                    json={"code": "x=1", "target_direction": "t", "llm_overrides": overrides})
    assert r.status_code == 200, r.text
    assert seen["arg"] == overrides
    assert _current_overrides.get() is None


def test_project_test_passes_overrides_to_run_tests(monkeypatch):
    """project /test 路由把 llm_overrides 透传到 run_tests (后者经 generate_test_cases
    → llm_generate_tests 内 use_llm_overrides 包裹)。"""
    import app.api.project as project_api

    seen = {}

    def fake_run_tests(kg, sources, td, kn, **kwargs):
        seen["overrides"] = kwargs.get("llm_overrides")
        return {"rejected": True, "reject_reason": "test stub",
                "summary": {"total": 0, "passed": 0, "failed": 0, "error": 0, "skipped": 0}}

    monkeypatch.setattr(project_api, "run_tests", fake_run_tests)
    _patch_appstate_kg(monkeypatch)

    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    overrides = {"api_key": "sk-t", "model": "tm"}
    r = client.post("/api/project/test",
                    json={"source_type": "text", "code": "x=1",
                          "target_direction": "t", "llm_overrides": overrides})
    assert r.status_code == 200, r.text
    assert seen["overrides"] == overrides
