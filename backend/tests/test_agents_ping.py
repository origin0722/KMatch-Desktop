"""POST /api/agents/ping — 用 overrides 构造客户端发 ping 验证可用 (openai | anthropic)。"""
from fastapi.testclient import TestClient
import app.api.agents as agents_api

from app.main import app


def _ping(payload):
    return TestClient(app).post("/api/agents/ping", json=payload)


def test_agents_ping_ok_with_overrides(monkeypatch):
    """overrides 合法时，ping 调 model.invoke 返回 ok=True。"""

    class FakeModel:
        def invoke(self, prompt):
            class Resp:
                content = "pong"
            return Resp()

    # 路由 from app.agents.llm import get_chat_model — patch 路由模块绑定
    monkeypatch.setattr(agents_api, "get_chat_model",
                        lambda temperature=None, overrides=None: FakeModel())
    r = _ping({"llm_overrides": {"api_key": "sk", "model": "m", "base_url": "u"}})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "pong" in body["content"]
    assert body["protocol"] == "openai"


def test_agents_ping_failure_returns_ok_false(monkeypatch):
    """model.invoke 抛异常时返回 ok=False + error。"""

    def boom_model(temperature=None, overrides=None):
        class M:
            def invoke(self, p):
                raise RuntimeError("invalid api key")
        return M()

    monkeypatch.setattr(agents_api, "get_chat_model", boom_model)
    r = _ping({"llm_overrides": {"api_key": "bad", "model": "m", "base_url": "u"}})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "invalid api key" in body["error"]


def test_agents_ping_anthropic_ok(monkeypatch):
    """protocol=anthropic 走 AsyncAnthropic.messages.create。"""

    class _FakeMessages:
        async def create(self, **kwargs):
            return type("R", (), {"content": [type("B", (), {"type": "text", "text": "pong-anthropic"})()]})()

    class _FakeClient:
        def __init__(self, api_key=None):
            self.messages = _FakeMessages()

    monkeypatch.setattr(agents_api, "AsyncAnthropic", _FakeClient)
    r = _ping({"protocol": "anthropic", "llm_overrides": {"api_key": "k", "model": "claude-x"}})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["content"] == "pong-anthropic"
    assert body["protocol"] == "anthropic"


def test_agents_ping_anthropic_error_ok_false(monkeypatch):
    class _FakeClient:
        def __init__(self, api_key=None):
            self.messages = type("M", (), {
                "create": lambda self, **kw: (_ for _ in ()).throw(RuntimeError("claude unavailable"))
            })()

    monkeypatch.setattr(agents_api, "AsyncAnthropic", _FakeClient)
    r = _ping({"protocol": "anthropic", "llm_overrides": {"api_key": "k", "model": "c"}})
    body = r.json()
    assert body["ok"] is False
    assert "claude unavailable" in body["error"]
