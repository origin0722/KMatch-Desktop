"""interactive 出题必须应用 llm_overrides ContextVar (BUG 回归)。

复现背景: 前端「统一 API 配置」/「Agent 独立 key」把 key 经请求体 llm_overrides 传递;
interactive 出题分支若不在 use_llm_overrides() 内, prepare_questions 里的 llm_configured()
读不到 UI 配置的 key (后端 .env 仍是占位符) → 误报 "LLM 未配置且题库为空,无法出题"。
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agents import llm
from app.api import diagnostics as diag

# 桩 overrides key: 虚构测试桩 (非真实凭据); 经变量引用, 避免本地扫描器对内联字面量误报
_STUB_KEY = "stub-real-key"


class _FakeKG:
    def close(self):
        pass


@pytest.fixture
def app(monkeypatch):
    a = FastAPI()
    a.state.kg = _FakeKG()
    a.include_router(diag.router, prefix="/api/diagnostics")

    seen = {}

    def fake_resolve(kg, direction, known_topics):
        return ("hit", [{"node_id": "PY-001", "name": "x", "difficulty": 1, "summary": ""}])

    monkeypatch.setattr(diag, "resolve_direction", fake_resolve)

    def fake_prepare(kg, target, known, seed=None, nodes=None):
        # 关键断言点: prepare_questions 执行时是否已见到 override key
        seen["llm_configured"] = llm.llm_configured()
        return [{"qid": "Q-1", "source_node_id": "PY-001", "type": "choice",
                 "question": "q", "options": ["A"], "difficulty": 1}], nodes

    monkeypatch.setattr(diag, "prepare_questions", fake_prepare)
    return a, seen


def _post(client, body):
    return client.post("/api/diagnostics/assess", json=body)


def test_interactive_with_overrides_sees_configured(app, monkeypatch):
    """llm_overrides 携带有效 key → prepare_questions 内 llm_configured() 为 True。"""
    a, seen = app
    monkeypatch.setattr(llm.settings, "LLM_API_KEY", "sk-placeholder")  # 后端 .env 占位
    resp = _post(TestClient(a), {
        "mode": "interactive", "target_direction": "Python", "known_topics": [],
        "llm_overrides": {"api_key": _STUB_KEY, "base_url": "https://x/v1", "model": "m"},
    })
    assert resp.status_code == 200
    assert seen.get("llm_configured") is True


def test_interactive_without_overrides_sees_unconfigured(app, monkeypatch):
    """无 overrides 且后端占位 → llm_configured() 为 False (保持一致语义)。"""
    a, seen = app
    monkeypatch.setattr(llm.settings, "LLM_API_KEY", "sk-placeholder")
    resp = _post(TestClient(a), {
        "mode": "interactive", "target_direction": "Python", "known_topics": [],
    })
    assert resp.status_code == 200
    assert seen.get("llm_configured") is False


# ============================================================
# submit / feedback 预检必须在 overrides 作用域内 (BUG: 配了 key 提交判分仍报 "LLM 未配置")
# ============================================================

def _seed_session(sid, questions=None):
    diag._cache_session(sid, {
        "questions": questions or [{
            "qid": "Q-1", "source_node_id": "PY-001", "type": "choice", "question": "q",
            "options": ["A", "B"], "answer": "A", "difficulty": 1, "hint": "",
            "explanation": "e"}],
        "nodes": [{"node_id": "PY-001"}],
        "target_direction": "Python",
        "created_at": "",
    })


def _stub_submit_body(monkeypatch, seen):
    def fake_grade(questions, answers):
        seen["llm_configured"] = llm.llm_configured()
        return {"correct_count": 1, "total_count": 1, "per_node": {}}
    monkeypatch.setattr(diag, "_grade", fake_grade)
    monkeypatch.setattr(
        diag, "_build_profile",
        lambda target, nodes, grading, questions=None, learning_style_quiz=None, practical_evidence=None, demographics=None:
        {"theory_level": 1, "weak_topics": [], "known_topics": [], "mastery_by_node": {}})
    monkeypatch.setattr(diag, "decide_feedback", lambda cc, tc: {"strategy": "advance", "reason": ""})
    monkeypatch.setattr(
        diag, "graph_controller_node",
        lambda kg: lambda state: {"knowledge_graph": {}, "orchestration_log": []})
    monkeypatch.setattr(diag, "_persist_run", lambda **kw: None)


def test_submit_with_overrides_sees_configured(app, monkeypatch):
    """UI 独立 key (llm_overrides) 提交判分 → 预检 llm_configured() 为 True, 不再误报 503。"""
    a, _ = app
    monkeypatch.setattr(llm.settings, "LLM_API_KEY", "sk-placeholder")
    seen = {}
    _seed_session("s-submit-1")
    _stub_submit_body(monkeypatch, seen)
    resp = TestClient(a).post("/api/diagnostics/submit", json={
        "session_id": "s-submit-1", "answers": ["A"],
        "llm_overrides": {"api_key": _STUB_KEY, "base_url": "https://x/v1", "model": "m"},
    })
    assert resp.status_code == 200, resp.text
    assert seen.get("llm_configured") is True


def test_submit_without_overrides_503(app, monkeypatch):
    """无 overrides 且后端占位 → 判分预检 503 (语义保持)。"""
    a, _ = app
    monkeypatch.setattr(llm.settings, "LLM_API_KEY", "sk-placeholder")
    seen = {}
    _seed_session("s-submit-2")
    _stub_submit_body(monkeypatch, seen)
    resp = TestClient(a).post("/api/diagnostics/submit", json={
        "session_id": "s-submit-2", "answers": ["A"]})
    assert resp.status_code == 503
    assert "LLM 未配置" in resp.json()["detail"]


def test_feedback_with_overrides_sees_configured(app, monkeypatch):
    """feedback 再生预检同样在 overrides 作用域内。"""
    a, _ = app
    monkeypatch.setattr(llm.settings, "LLM_API_KEY", "sk-placeholder")
    seen = {}
    _seed_session("s-fb-1")

    def fake_regen(strategy, profile, learning_path, kg):
        seen["llm_configured"] = llm.llm_configured()
        return {"resources": [], "node_count": 0}

    monkeypatch.setattr(diag, "regenerate_for_feedback", fake_regen)
    resp = TestClient(a).post("/api/diagnostics/feedback", json={
        "session_id": "s-fb-1", "strategy": "advance", "profile": {"theory_level": 1},
        "llm_overrides": {"api_key": _STUB_KEY, "base_url": "https://x/v1", "model": "m"},
    })
    assert resp.status_code == 200, resp.text
    assert seen.get("llm_configured") is True


def test_feedback_without_overrides_503(app, monkeypatch):
    a, _ = app
    monkeypatch.setattr(llm.settings, "LLM_API_KEY", "sk-placeholder")
    _seed_session("s-fb-2")
    resp = TestClient(a).post("/api/diagnostics/feedback", json={
        "session_id": "s-fb-2", "strategy": "advance", "profile": {"theory_level": 1}})
    assert resp.status_code == 503
    assert "LLM 未配置" in resp.json()["detail"]
