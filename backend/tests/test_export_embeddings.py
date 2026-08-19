"""离线种子导出脚本 (scripts/export_embeddings.py) 单测 — fetch + 原子写。

不碰真实 Neo4j (mock driver); 验证 entries 形状与原子写 (临时文件清理, 旧文件保真)。
"""

import json
from pathlib import Path

import pytest

from app import config as config_module
from scripts import export_embeddings as exp


def _fake_driver(records):
    class _Rec:
        def __init__(self, d):
            self._d = d

        def __getitem__(self, k):
            return self._d[k]

    class _Session:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def run(self, query, **kw):
            return [_Rec(r) for r in records]

    class _Driver:
        def __init__(self):
            self.closed = False

        def verify_connectivity(self):
            pass

        def session(self):
            return _Session()

        def close(self):
            self.closed = True

    return _Driver()


def test_fetch_embeddings(monkeypatch):
    driver = _fake_driver([
        {"id": "PY-001", "emb": [0.1, 0.2]},
        {"id": "PY-002", "emb": [0.3, 0.4]},
    ])
    monkeypatch.setattr(exp.GraphDatabase, "driver", lambda *a, **k: driver)
    out = exp.fetch_embeddings("bolt://x:7687", "u", "p")
    assert out == {"PY-001": [0.1, 0.2], "PY-002": [0.3, 0.4]}
    assert driver.closed is True  # driver.close 在 finally 中调用


def test_fetch_empty_is_falsy(monkeypatch):
    driver = _fake_driver([])
    monkeypatch.setattr(exp.GraphDatabase, "driver", lambda *a, **k: driver)
    assert exp.fetch_embeddings("bolt://x:7687", "u", "p") == {}


def test_write_seed_atomic(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(config_module.settings, "EMBEDDING_MODEL", "test-model")
    out = tmp_path / "nested" / "embeddings.json"
    exp.write_seed({"PY-001": [1.0, 2.0]}, out, model="m1")
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data == {"model": "m1", "items": {"PY-001": [1.0, 2.0]}}
    assert not (out.with_name(".embeddings.json.tmp")).exists()  # 临时文件已清理


def test_write_seed_default_model(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(config_module.settings, "EMBEDDING_MODEL", "default-model")
    out = tmp_path / "embeddings.json"
    exp.write_seed({"A": [1]}, out)
    assert json.loads(out.read_text(encoding="utf-8"))["model"] == "default-model"
