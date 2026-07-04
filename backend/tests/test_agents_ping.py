"""POST /api/agents/ping — 用 overrides 构造 ChatOpenAI 发 ping 验证可用。"""
from fastapi.testclient import TestClient


def test_agents_ping_ok_with_overrides(monkeypatch):
    """overrides 合法时，ping 调 model.invoke 返回 ok=True。"""
    import app.api.agents as agents_api

    class FakeModel:
        def invoke(self, prompt):
            class Resp:
                content = "pong"
            return Resp()

    # 路由 from app.agents.llm import get_chat_model — patch 路由模块绑定
    monkeypatch.setattr(agents_api, "get_chat_model",
                        lambda temperature=None, overrides=None: FakeModel())
    from app.main import app
    client = TestClient(app)
    r = client.post("/api/agents/ping",
                    json={"llm_overrides": {"api_key": "sk", "model": "m", "base_url": "u"}})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "pong" in body["content"]


def test_agents_ping_failure_returns_ok_false(monkeypatch):
    """model.invoke 抛异常时返回 ok=False + error。"""
    import app.api.agents as agents_api

    def boom_model(temperature=None, overrides=None):
        class M:
            def invoke(self, p):
                raise RuntimeError("invalid api key")
        return M()

    monkeypatch.setattr(agents_api, "get_chat_model", boom_model)
    from app.main import app
    client = TestClient(app)
    r = client.post("/api/agents/ping",
                    json={"llm_overrides": {"api_key": "bad", "model": "m", "base_url": "u"}})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "invalid api key" in body["error"]
