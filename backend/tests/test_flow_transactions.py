"""flow_transactions 流程定义事务单测 (Phase 3b)。

覆盖: 草稿宽松校验、提交严格 gate（内置禁改/坏定义拒）、revision 幂等与回滚、
主定义文件保持 schema 干净（可被 discovery 发现）、API 四端点。
"""

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agents import flow_transactions as ft
from app.agents import workflow_def as wf
from app.api import diagnostics as diag_api

CUSTOM = {
    "format": "kmatch.workflow",
    "version": 1,
    "id": "custom-flow",
    "name": "自定义流程",
    "description": "测试自定义",
    "stages": [
        {"id": "s1", "label": "A", "agents": ["diagnostics"], "dependencies": []},
        {"id": "s2", "label": "B", "agents": ["reviewer"], "dependencies": ["s1"]},
    ],
}


def _patch(monkeypatch, tmp_path):
    from app.config import settings
    monkeypatch.setattr(settings, "DATA_DIR", Path(tmp_path))


def test_commit_valid_and_discoverable(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    res = ft.commit_definition(CUSTOM, note="n1")
    assert res["ok"] is True and res["revision"]
    assert (Path(tmp_path) / "workflows" / "custom-flow.json").is_file()
    ids = {x["id"] for x in wf.list_workflows()}
    assert "custom-flow" in ids
    got = wf.get_workflow("custom-flow")
    assert got and got["id"] == "custom-flow"
    assert "_tx" not in got  # 主定义保持 schema 干净


def test_commit_rejects_invalid(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    bad = dict(CUSTOM, stages=[{"id": "x", "agents": ["ghost"]}])
    res = ft.commit_definition(bad)
    assert res["ok"] is False and res["errors"]
    assert not (Path(tmp_path) / "workflows" / "custom-flow.json").exists()


def test_commit_rejects_builtin_shadow(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    res = ft.commit_definition(dict(CUSTOM, id="scene1-loop"))
    assert res["ok"] is False
    assert any("内置" in e for e in res["errors"])


def test_save_draft_lenient(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    ok = ft.save_draft(dict(CUSTOM, id="draft-flow"))
    assert ok["ok"] is True and ok["valid"] is True
    # WIP: 未过严格校验的草稿也允许保存, 返回 warnings
    dangling = dict(CUSTOM, id="draft-bad", stages=[{"id": "z", "agents": ["ghost"]}])
    res = ft.save_draft(dangling)
    assert res["ok"] is True and res["valid"] is False and res["warnings"]
    assert ft.save_draft({"nope": 1})["ok"] is False  # 缺 id → 拒


def test_revisions_and_restore(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    r1 = ft.commit_definition(CUSTOM, note="v1")
    v2 = dict(CUSTOM, name="自定义流程 v2", description="改")
    r2 = ft.commit_definition(v2, note="v2")
    revs = ft.list_revisions("custom-flow")
    assert len(revs) == 2
    assert any(r["_tx"].get("note") == "v2" for r in revs)
    # 回滚到 r1 revision → 定义回到 v1
    res = ft.restore_revision("custom-flow", r1["revision"])
    assert res["ok"] is True
    assert wf.get_workflow("custom-flow")["name"] == "自定义流程"
    # 回滚不存在 → 失败
    assert ft.restore_revision("custom-flow", "nope")["ok"] is False


def test_get_definition(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    assert ft.get_definition("custom-flow") is None  # 未提交
    ft.commit_definition(CUSTOM)
    assert ft.get_definition("custom-flow")["id"] == "custom-flow"
    assert ft.get_definition("scene1-loop")["id"] == "scene1-loop"  # 内置回读


# ---------------- API ----------------

def _diag_app() -> FastAPI:
    app = FastAPI()
    app.state.kg = object()
    app.state.workflow = object()
    app.include_router(diag_api.router, prefix="/api/diagnostics")
    return app


def test_workflows_api_tx(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    c = TestClient(_diag_app())

    # 草稿
    d = c.put("/api/diagnostics/workflows/custom-flow/draft", json={"definition": dict(CUSTOM, id="custom-flow")})
    assert d.status_code == 200 and d.json()["ok"] is True

    # 提交
    r = c.post("/api/diagnostics/workflows/custom-flow/commit",
               json={"definition": CUSTOM, "note": "来自工作台", "reviewed_by": "test"})
    assert r.status_code == 200
    assert "revision" in r.json()
    assert c.get("/api/diagnostics/workflows/custom-flow").json()["name"] == "自定义流程"

    # 内置禁改 → 409
    b = c.post("/api/diagnostics/workflows/scene1-loop/commit", json={"definition": dict(CUSTOM, id="scene1-loop")})
    assert b.status_code == 409

    # 坏定义 → 400
    e = c.post("/api/diagnostics/workflows/custom-flow/commit", json={"definition": dict(CUSTOM, stages=[])})
    assert e.status_code == 400

    # revisions + restore
    revs = c.get("/api/diagnostics/workflows/custom-flow/revisions").json()["revisions"]
    assert len(revs) == 1
    rv = c.post("/api/diagnostics/workflows/custom-flow/restore", json={"revision": r.json()["revision"]})
    assert rv.status_code == 200
    assert c.post("/api/diagnostics/workflows/custom-flow/restore", json={"revision": "nope"}).status_code == 404
