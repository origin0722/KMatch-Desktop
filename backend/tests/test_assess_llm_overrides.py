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
        "llm_overrides": {"api_key": "sk-real-key", "base_url": "https://x/v1", "model": "m"},
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
