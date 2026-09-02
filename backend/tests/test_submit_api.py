"""interactive 答题提交 API 单测 — assess(interactive) 出题 → submit 判分闭环。

用 FastAPI TestClient + monkeypatch 绕过 LLM/Neo4j，验证:
  - assess(interactive) 返回题目并缓存 session
  - submit 用缓存题目判分，返回画像 + 动态反馈
  - session 不存在 → 404
"""

import json
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import diagnostics as diag_api


# ---- fake 数据 ----
_FAKE_QUESTIONS = [
    {"node_id": "PY-005", "question": "q0", "answer": "A", "type": "choice", "difficulty": 2},
    {"node_id": "PY-005", "question": "q1", "answer": "对", "type": "judge", "difficulty": 2},
]
_FAKE_NODES = [{"node_id": "PY-005", "name": "循环", "difficulty": 2}]


def _build_app(monkeypatch):
    """构造带 fake kg 的 FastAPI app，注册 diagnostics 路由。"""
    # 清空会话缓存，避免测试间污染
    diag_api._INTERACTIVE_SESSIONS.clear()
    # submit 路由会先检查 LLM 是否已配置；常规闭环夹具显式表示可用，
    # 未配置分支由 test_submit_llm_not_configured_503 单独覆盖。
    monkeypatch.setattr(diag_api, "llm_configured", lambda: True)

    # mock resolve_direction (阶段16 域判定): unknown → 走旧选点行为, 不碰 LLM/向量
    monkeypatch.setattr(
        diag_api, "resolve_direction", lambda kg, target, known: ("unknown", []),
    )
    # mock prepare_questions: 不调 LLM (nodes kwarg 对齐阶段16 域命中/建域传参)
    monkeypatch.setattr(
        diag_api, "prepare_questions",
        lambda kg, target, known, nodes=None: (_FAKE_QUESTIONS, _FAKE_NODES),
    )
    # mock _grade: 第1题对第2题错
    def _fake_grade(questions, answers):
        per_node = {"PY-005": [
            {"question_index": 0, "correct": True},
            {"question_index": 1, "correct": False},
        ]}
        return {"per_node": per_node, "correct_count": 1, "total_count": 2}
    monkeypatch.setattr(diag_api, "_grade", _fake_grade)
    # mock _build_profile: 返回最小画像 (接受 questions kwarg, BUG-036 深化)
    monkeypatch.setattr(
        diag_api, "_build_profile",
        lambda target, nodes, grading, **kw: {
            "theory_level": 2, "known_topics": [], "weak_topics": [],
            "recommended_path": {"current_node": "PY-005", "next_nodes": [], "estimated_completion_weeks": 4},
        },
    )

    app = FastAPI()
    app.state.kg = MagicMock()  # 非 None 即可通过 _get_kg 检查
    app.include_router(diag_api.router, prefix="/api/diagnostics")
    return app


def test_interactive_assess_returns_questions(monkeypatch):
    """assess(interactive) 返回 AssessResponse (题目填充, 其余字段空)，缓存 session。"""
    app = _build_app(monkeypatch)
    client = TestClient(app)

    resp = client.post("/api/diagnostics/assess", json={
        "target_direction": "Python 入门", "mode": "interactive",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"]
    assert len(data["assessment"]["questions"]) == 2
    assert data["assessment"]["total_count"] == 2
    # interactive 出题阶段: 其余字段为空 (统一 AssessResponse 结构)
    assert data["profile"] == {}
    assert data["review_results"] == {}
    assert data["knowledge_graph"] == {}
    assert data["orchestration_log"] == []
    # 题目已缓存
    assert data["session_id"] in diag_api._INTERACTIVE_SESSIONS


def test_submit_judges_and_returns_feedback(monkeypatch):
    """submit 判分 → 画像 + 动态反馈 (1/2=0.5 → remediate)。"""
    app = _build_app(monkeypatch)
    client = TestClient(app)

    # 先出题
    assess = client.post("/api/diagnostics/assess", json={
        "target_direction": "Python 入门", "mode": "interactive",
    })
    session_id = assess.json()["session_id"]

    # 提交答案
    resp = client.post("/api/diagnostics/submit", json={
        "session_id": session_id, "answers": ["A", "错"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == session_id
    assert data["assessment"]["correct_count"] == 1
    assert data["assessment"]["total_count"] == 2
    assert data["profile"]["theory_level"] == 2
    # 1/2=0.5 → remediate
    assert data["feedback"]["strategy"] == "remediate"
    assert data["feedback"]["accuracy"] == 0.5


def test_submit_unknown_session_404(monkeypatch):
    """session 不存在 → 404。"""
    app = _build_app(monkeypatch)
    client = TestClient(app)

    resp = client.post("/api/diagnostics/submit", json={
        "session_id": "nonexistent", "answers": ["A"],
    })
    assert resp.status_code == 404


def test_submit_aligns_answer_count(monkeypatch):
    """提交答案数 ≠ 题数 → 自动对齐 (缺失补空串，多余截断)。"""
    app = _build_app(monkeypatch)
    client = TestClient(app)

    assess = client.post("/api/diagnostics/assess", json={
        "target_direction": "Python 入门", "mode": "interactive",
    })
    session_id = assess.json()["session_id"]

    # 只提交 1 个答案 (题目有 2 道)
    resp = client.post("/api/diagnostics/submit", json={
        "session_id": session_id, "answers": ["A"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["assessment"]["answers"]) == 2  # 对齐到题数


def test_submit_llm_not_configured_503(monkeypatch):
    """LLM 未配置时 submit 返回 503 (而非 _grade 调用失败 500)。"""
    # _build_app 会 mock _grade，但 llm_configured 检查在 _grade 之前，需还原
    app = _build_app(monkeypatch)
    # 覆盖: 让 llm_configured 返回 False (即使 _grade 被 mock，前置检查先拦截)
    monkeypatch.setattr(diag_api, "llm_configured", lambda: False)
    client = TestClient(app)

    # 先出题 (prepare_questions 被 mock，不查 llm_configured)
    assess = client.post("/api/diagnostics/assess", json={
        "target_direction": "Python 入门", "mode": "interactive",
    })
    session_id = assess.json()["session_id"]

    resp = client.post("/api/diagnostics/submit", json={
        "session_id": session_id, "answers": ["A"],
    })
    assert resp.status_code == 503
    assert "LLM 未配置" in resp.json()["detail"]


# ============================================================
# W5 动态反馈 content 再生: POST /api/diagnostics/feedback
# ============================================================

def _build_feedback_app(monkeypatch, regen_result=None, prereqs=None):
    """构造测 feedback 接口的 app。"""
    diag_api._INTERACTIVE_SESSIONS.clear()
    # Tavily 隔离: 开发机 .env 常有真实 key (阶段16 起), 不隔离会走真联网搜索
    monkeypatch.setattr(diag_api.settings, "TAVILY_API_KEY", "")
    # 域判定走 unknown (阶段16): 不碰 LLM/向量
    monkeypatch.setattr(
        diag_api, "resolve_direction", lambda kg, target, known: ("unknown", []),
    )
    # assess interactive 出题 mock (复用 _build_app 的 mock 不便，单独构造; nodes kwarg 对齐阶段16)
    monkeypatch.setattr(
        diag_api, "prepare_questions",
        lambda kg, target, known, nodes=None: (_FAKE_QUESTIONS, _FAKE_NODES),
    )
    monkeypatch.setattr(diag_api, "llm_configured", lambda: True)
    # mock regenerate_for_feedback
    if regen_result is None:
        regen_result = {
            "strategy": "remediate",
            "resources": [{"content_type": "lecture", "target_node_id": "PY-005", "content": "降维讲解..."}],
            "node_count": 1,
            "generated_at": "2026-06-18T00:00:00Z",
        }
    monkeypatch.setattr(diag_api, "regenerate_for_feedback", lambda *a, **k: regen_result)

    app = FastAPI()
    app.state.kg = MagicMock()
    app.include_router(diag_api.router, prefix="/api/diagnostics")
    return app


def test_feedback_regenerates_content(monkeypatch):
    """feedback 接口按策略再生内容。"""
    app = _build_feedback_app(monkeypatch)
    client = TestClient(app)

    # 先出题缓存 session
    assess = client.post("/api/diagnostics/assess", json={
        "target_direction": "Python 入门", "mode": "interactive",
    })
    session_id = assess.json()["session_id"]

    resp = client.post("/api/diagnostics/feedback", json={
        "session_id": session_id,
        "strategy": "remediate",
        "profile": {"theory_level": 2, "weak_topics": [{"node_id": "PY-005", "mastery": 0.2}]},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["strategy"] == "remediate"
    assert len(data["resources"]) == 1
    assert data["resources"][0]["target_node_id"] == "PY-005"
    assert data["node_count"] == 1


def test_feedback_invalid_strategy_422(monkeypatch):
    """无效 strategy → 422 (Pydantic Literal 校验)。"""
    app = _build_feedback_app(monkeypatch)
    client = TestClient(app)
    assess = client.post("/api/diagnostics/assess", json={
        "target_direction": "Python 入门", "mode": "interactive",
    })
    session_id = assess.json()["session_id"]

    resp = client.post("/api/diagnostics/feedback", json={
        "session_id": session_id, "strategy": "bogus", "profile": {},
    })
    assert resp.status_code == 422


def test_feedback_unknown_session_404(monkeypatch):
    """session 不存在 → 404。"""
    app = _build_feedback_app(monkeypatch)
    client = TestClient(app)
    resp = client.post("/api/diagnostics/feedback", json={
        "session_id": "nonexistent", "strategy": "remediate", "profile": {},
    })
    assert resp.status_code == 404


def test_feedback_llm_not_configured_503(monkeypatch):
    """LLM 未配置 → 503。"""
    diag_api._INTERACTIVE_SESSIONS.clear()
    monkeypatch.setattr(
        diag_api, "resolve_direction", lambda kg, target, known: ("unknown", []),
    )
    monkeypatch.setattr(
        diag_api, "prepare_questions",
        lambda kg, target, known, nodes=None: (_FAKE_QUESTIONS, _FAKE_NODES),
    )
    monkeypatch.setattr(diag_api, "llm_configured", lambda: False)
    app = FastAPI()
    app.state.kg = MagicMock()
    app.include_router(diag_api.router, prefix="/api/diagnostics")
    client = TestClient(app)

    assess = client.post("/api/diagnostics/assess", json={
        "target_direction": "Python 入门", "mode": "interactive",
    })
    session_id = assess.json()["session_id"]
    resp = client.post("/api/diagnostics/feedback", json={
        "session_id": session_id, "strategy": "remediate", "profile": {},
    })
    assert resp.status_code == 503


def test_interactive_assess_strips_answer(monkeypatch):
    """BUG-033: assess(interactive) 返回的 questions 不含 answer (防泄露)，缓存保留完整题目。"""
    app = _build_app(monkeypatch)
    client = TestClient(app)

    resp = client.post("/api/diagnostics/assess", json={
        "target_direction": "Python 入门", "mode": "interactive",
    })
    data = resp.json()
    # 客户端拿到的题目无 answer 字段
    for q in data["assessment"]["questions"]:
        assert "answer" not in q
    # 但缓存的完整题目含 answer (供 submit 判分)
    session = diag_api._INTERACTIVE_SESSIONS[data["session_id"]]
    assert all("answer" in q for q in session["questions"])


def test_fetch_candidate_nodes_handles_non_dict_known_topics(monkeypatch):
    """BUG-6: known_topics 含非 dict 元素 (如字符串) 不崩溃。"""
    # 直接测 prepare_questions 内的 _fetch_candidate_nodes 逻辑
    from app.agents.diagnostics import _fetch_candidate_nodes

    class _FakeKG2:
        def assemble_learning_path(self, **k):
            return []
        def get_by_difficulty(self, mn, mx):
            return [{"node_id": "PY-001", "name": "变量", "difficulty": 1}]

    # 混入字符串元素，不应抛 AttributeError
    nodes = _fetch_candidate_nodes(_FakeKG2(), ["PY-001", "not-a-dict", 123], "test")
    assert len(nodes) == 1  # 回退到 get_by_difficulty
