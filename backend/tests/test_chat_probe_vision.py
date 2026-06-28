"""场景: /api/chat/probe-vision — 用一张 76x100 的"test vision"图探当前模型是否能 OCR。

cache 命中直接返回; auth 错不写缓存; 普通错写 False 入缓存; DELETE 清空。
"""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings

client = TestClient(app)


@pytest.fixture(autouse=True)
def isolate_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATA_DIR", str(tmp_path))
    cache_path = Path(tmp_path) / "vision_cache.json"
    if cache_path.exists():
        cache_path.unlink()
    yield


def test_probe_vision_cache_hit_skips_call():
    cache_path = Path(settings.DATA_DIR) / "vision_cache.json"
    cache_path.write_text(json.dumps({"https://api.openai.com/v1::gpt-4o": True}))
    resp = client.post("/api/chat/probe-vision", json={
        "base_url": "https://api.openai.com/v1", "api_key": "sk-X",
        "model": "gpt-4o", "protocol": "openai",
    })
    assert resp.status_code == 200
    assert resp.json() == {"vision": True, "cached": True}


def test_probe_vision_openai_extracts_test_vision_and_writes_cache():
    fake_client = MagicMock()
    fake_msg = MagicMock()
    fake_msg.content = "Test vision"
    fake_resp = MagicMock()
    fake_resp.choices = [MagicMock(message=fake_msg)]
    fake_client.chat.completions.create = AsyncMock(return_value=fake_resp)

    with patch("app.api.chat._get_async_client", return_value=fake_client):
        resp = client.post("/api/chat/probe-vision", json={
            "base_url": "https://api.openai.com/v1", "api_key": "sk-X",
            "model": "gpt-4o", "protocol": "openai",
        })
    assert resp.status_code == 200
    assert resp.json() == {"vision": True, "cached": False}
    cache = json.loads((Path(settings.DATA_DIR) / "vision_cache.json").read_text())
    assert cache["https://api.openai.com/v1::gpt-4o"] is True


def test_probe_vision_auth_error_does_not_write_cache():
    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(
        side_effect=Exception("401 Unauthorized: invalid api key"))
    with patch("app.api.chat._get_async_client", return_value=fake_client):
        resp = client.post("/api/chat/probe-vision", json={
            "base_url": "u", "api_key": "bad", "model": "gpt-4o", "protocol": "openai",
        })
    body = resp.json()
    assert body["vision"] is False
    assert body.get("error") == "auth"
    assert not (Path(settings.DATA_DIR) / "vision_cache.json").exists()


def test_probe_vision_non_auth_error_writes_false_to_cache():
    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(side_effect=Exception("500 server error"))
    with patch("app.api.chat._get_async_client", return_value=fake_client):
        resp = client.post("/api/chat/probe-vision", json={
            "base_url": "u", "api_key": "sk-X", "model": "gpt-foo", "protocol": "openai",
        })
    assert resp.json() == {"vision": False, "cached": False}
    cache = json.loads((Path(settings.DATA_DIR) / "vision_cache.json").read_text())
    assert cache["u::gpt-foo"] is False


def test_delete_probe_vision_cache_clears_file():
    (Path(settings.DATA_DIR) / "vision_cache.json").write_text('{"a::b": true}')
    resp = client.delete("/api/chat/probe-vision/cache")
    assert resp.status_code == 200
    assert json.loads((Path(settings.DATA_DIR) / "vision_cache.json").read_text()) == {}
