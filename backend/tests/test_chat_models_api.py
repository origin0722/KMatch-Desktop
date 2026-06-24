"""场景: /api/chat/models — protocol=openai 走 AsyncOpenAI; protocol=anthropic 返回硬编码列表。"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, MagicMock

from app.main import app

client = TestClient(app)


def test_models_anthropic_short_circuits_returns_hardcoded():
    resp = client.post("/api/chat/models", json={
        "base_url": "https://api.anthropic.com", "api_key": "sk-X", "protocol": "anthropic",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert "claude-fable-5" in body["models"]
    assert "claude-opus-4-8" in body["models"]


def test_models_openai_calls_async_client():
    mock_resp = MagicMock()
    mock_resp.data = [MagicMock(id='deepseek-v4-pro'), MagicMock(id='deepseek-v3')]
    fake_client = MagicMock()
    fake_client.models.list = AsyncMock(return_value=mock_resp)
    with patch("app.api.chat._get_async_client", return_value=fake_client):
        resp = client.post("/api/chat/models", json={
            "base_url": "https://api.deepseek.com/v1", "api_key": "sk-X", "protocol": "openai",
        })
    assert resp.status_code == 200
    assert resp.json() == {"models": ["deepseek-v4-pro", "deepseek-v3"]}


def test_models_defaults_protocol_to_openai_when_omitted():
    fake_client = MagicMock()
    fake_client.models.list = AsyncMock(return_value=MagicMock(data=[]))
    with patch("app.api.chat._get_async_client", return_value=fake_client):
        resp = client.post("/api/chat/models", json={"base_url": "x", "api_key": "y"})
    assert resp.status_code == 200
    assert "models" in resp.json()
