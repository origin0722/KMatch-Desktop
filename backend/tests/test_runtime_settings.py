"""运行时设置单测 (W?: 治"端用户被迫改 .env")。

覆盖:
  - runtime_settings: 默认/合并保存 (None=不变, ""=清除, clear_api_key)/脱敏/生效值优先级
  - quality_judge.get_judge_llm 优先级: 运行时(启用) > env JUDGE_LLM_* > 同源回退
  - /api/settings 路由: GET 脱敏不泄明文 / POST 触发引擎 reconfigure / clear 语义
"""

import json
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import runtime_settings as rs
from app.api import settings as settings_api


@pytest.fixture
def local_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(rs.settings, "LOCAL_DIR", tmp_path)
    return tmp_path


# ============================================================
# runtime_settings 纯函数
# ============================================================

def test_load_defaults_when_no_file(local_dir):
    data = rs.load()
    assert data["embedding"] == {"api_key": "", "base_url": "", "model": ""}
    assert data["judge"]["enabled"] is False


def test_save_merge_semantics(local_dir):
    rs.save({"embedding": {"api_key": "sk-abc", "model": "text-embedding-v3"}})
    # 只给 model 不给 api_key (None) → 保持已存值
    rs.save({"embedding": {"api_key": None, "model": "text-embedding-v4"}})
    data = rs.load()
    assert data["embedding"]["api_key"] == "sk-abc"
    assert data["embedding"]["model"] == "text-embedding-v4"
    # "" = 显式清除
    rs.save({"embedding": {"api_key": ""}})
    assert rs.load()["embedding"]["api_key"] == ""


def test_save_persists_to_local_dir(local_dir):
    rs.save({"judge": {"enabled": True, "api_key": "sk-j", "model": "m1"}})
    raw = json.loads((local_dir / "backend_settings.json").read_text(encoding="utf-8"))
    assert raw["judge"]["enabled"] is True
    assert raw["judge"]["model"] == "m1"


def test_masked_never_returns_plaintext(local_dir):
    m = rs.masked("sk-very-secret-1234")
    assert m["configured"] is True
    assert m["tail"] == "1234"
    assert "secret" not in json.dumps(m)
    assert rs.masked("") == {"configured": False, "tail": ""}


def test_effective_embedding_priority(local_dir, monkeypatch):
    monkeypatch.setattr(rs.settings, "EMBEDDING_API_KEY", "sk-env")
    monkeypatch.setattr(rs.settings, "EMBEDDING_BASE_URL", "https://env/v1")
    monkeypatch.setattr(rs.settings, "EMBEDDING_MODEL", "env-model")
    # 未配文件 → env 生效
    eff = rs.effective_embedding()
    assert eff["api_key"] == "sk-env" and eff["key_source"] == "env"
    # 文件配置 > env
    rs.save({"embedding": {"api_key": "sk-file", "base_url": "https://file/v1", "model": "file-model"}})
    eff = rs.effective_embedding()
    assert eff["api_key"] == "sk-file" and eff["key_source"] == "runtime"
    assert eff["base_url"] == "https://file/v1" and eff["model"] == "file-model"


def test_effective_judge_priority(local_dir, monkeypatch):
    # 无任何配置 → 同源回退
    monkeypatch.setattr(rs.settings, "JUDGE_LLM_API_KEY", "")
    assert rs.effective_judge()["same_source"] is True
    # env 配置 → 异源 (source=env)
    monkeypatch.setattr(rs.settings, "JUDGE_LLM_API_KEY", "sk-env-judge")
    eff = rs.effective_judge()
    assert eff["same_source"] is False and eff["source"] == "env"
    # 运行时启用 > env
    rs.save({"judge": {"enabled": True, "api_key": "sk-rt", "base_url": "https://rt/v1", "model": "rt-m"}})
    eff = rs.effective_judge()
    assert eff["source"] == "runtime" and eff["api_key"] == "sk-rt"
    # 运行时开关关掉 → 回落 env
    rs.save({"judge": {"enabled": False}})
    assert rs.effective_judge()["source"] == "env"


# ============================================================
# get_judge_llm 优先级 (patch ChatOpenAI 捕获构造参数)
# ============================================================

class _FakeJudgeLLM:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def test_get_judge_llm_runtime_over_env(local_dir, monkeypatch):
    import app.agents.quality_judge as qj
    monkeypatch.setattr(rs.settings, "JUDGE_LLM_API_KEY", "sk-env-judge")
    monkeypatch.setattr("langchain_openai.ChatOpenAI", _FakeJudgeLLM)
    monkeypatch.setattr(qj, "get_default_chat_model", lambda: (_FakeJudgeLLM(), True))

    # env 生效
    judge, same = qj.get_judge_llm()
    assert same is False and judge.kwargs["api_key"] == "sk-env-judge"

    # 运行时启用覆盖 env
    rs.save({"judge": {"enabled": True, "api_key": "sk-rt", "base_url": "https://rt/v1", "model": "rt-m"}})
    judge, same = qj.get_judge_llm()
    assert same is False and judge.kwargs["api_key"] == "sk-rt"
    assert judge.kwargs["base_url"] == "https://rt/v1" and judge.kwargs["model"] == "rt-m"


def test_get_judge_llm_fallback_same_source(local_dir, monkeypatch):
    import app.agents.quality_judge as qj
    monkeypatch.setattr(rs.settings, "JUDGE_LLM_API_KEY", "")
    sentinel = _FakeJudgeLLM()
    monkeypatch.setattr(qj, "get_default_chat_model", lambda: sentinel)
    judge, same = qj.get_judge_llm()
    assert same is True and judge is sentinel


# ============================================================
# /api/settings 路由
# ============================================================

class _FakeStore:
    kind = "embedded"
    semantic_ready = False

    def __init__(self):
        self.reconfigured = None

    def reconfigure_embedding(self, api_key, base_url="", model=""):
        self.reconfigured = (api_key, base_url, model)
        self.semantic_ready = True
        return True


def _build_app(store=None):
    app = FastAPI()
    app.state.kg = store
    app.include_router(settings_api.router, prefix="/api/settings")
    return app


def test_get_backend_settings_masks_key(local_dir):
    rs.save({"embedding": {"api_key": "sk-super-secret-9999"}})
    client = TestClient(_build_app(_FakeStore()))
    data = client.get("/api/settings/backend").json()
    text = json.dumps(data)
    assert "sk-super-secret" not in text  # 明文不外泄
    assert data["embedding"]["configured"] is True
    assert data["embedding"]["key_tail"] == "9999"
    assert data["store"]["kind"] == "embedded"


def test_post_backend_applies_embedding(local_dir):
    store = _FakeStore()
    client = TestClient(_build_app(store))
    resp = client.post("/api/settings/backend", json={
        "embedding": {"api_key": "sk-new", "base_url": "https://x/v1", "model": "m"},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["saved"] is True
    assert data["embedding_applied"]["ok"] is True
    # 引擎收到的是生效值 (探活由 fake 捕获)
    assert store.reconfigured == ("sk-new", "https://x/v1", "m")


def test_post_clear_api_key(local_dir):
    rs.save({"embedding": {"api_key": "sk-old"}})
    store = _FakeStore()
    client = TestClient(_build_app(store))
    client.post("/api/settings/backend", json={"embedding": {"clear_api_key": True}})
    assert rs.load()["embedding"]["api_key"] == ""


def test_post_partial_update_keeps_key(local_dir):
    rs.save({"embedding": {"api_key": "sk-keep"}})
    client = TestClient(_build_app(None))
    # 只改 model, key 未提供 → 保持 (前端"留空不变"语义)
    client.post("/api/settings/backend", json={"embedding": {"api_key": None, "model": "m2"}})
    data = rs.load()
    assert data["embedding"]["api_key"] == "sk-keep"
    assert data["embedding"]["model"] == "m2"
