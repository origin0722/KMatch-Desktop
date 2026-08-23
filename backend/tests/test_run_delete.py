"""run 记录删除 API 单测 (issue-83)。"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agents import run_store as rs
from app.api import diagnostics as diag
from app.config import settings


def _client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATA_DIR", Path(tmp_path))
    app = FastAPI()
    app.include_router(diag.router, prefix="/api/diagnostics")
    return TestClient(app)


def test_delete_run_ok_then_404(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    rs.save_run(session_id="demo-del", mode="demo", summary={"x": 1})
    r = c.delete("/api/diagnostics/runs/demo-del")
    assert r.status_code == 200
    assert r.json()["deleted"] is True
    # 二次删除 → 404
    r2 = c.delete("/api/diagnostics/runs/demo-del")
    assert r2.status_code == 404
    # 列表不再包含
    lst = c.get("/api/diagnostics/runs").json()
    assert all(x["session_id"] != "demo-del" for x in lst["runs"])


def test_delete_run_unknown_404(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    assert c.delete("/api/diagnostics/runs/nope-not-exist").status_code == 404
    # 非法 session_id (路径穿越) → 安全归一化 → 404
    assert c.delete("/api/diagnostics/runs/..%2F..").status_code == 404
