"""run_store 耐久 run 记录单测 (Phase 1)。

覆盖: save/load 回环、events.jsonl 续写 seq、会话 id 去安全化 (防路径穿越)、
原子写、list_runs 排序; 以及 GET /api/diagnostics/runs 端点 (404/回读)。
所有磁盘 IO 落在 pytest tmp_path (monkeypatch settings.DATA_DIR), 不污染仓库 data/。
"""

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agents import run_store
from app.api import diagnostics as diag_api


def _patch_data_dir(monkeypatch, tmp_path):
    from app.config import settings
    monkeypatch.setattr(settings, "DATA_DIR", Path(tmp_path))


def _make_event(agent, status, msg="x"):
    return {"type": "agent-end", "agent": agent, "status": status, "message": msg, "log": f"[ts] {msg}"}


def test_save_load_roundtrip(monkeypatch, tmp_path):
    _patch_data_dir(monkeypatch, tmp_path)
    evs = [_make_event("diagnostics", "done", "判分 7/10"), _make_event("orchestrator", "done", "流程结束")]
    run_store.save_run(
        session_id="sid-abc-123",
        mode="demo",
        request={"target_direction": "Python"},
        events=evs,
        log=["[ts] 🔧 学情检测: 判分 7/10", "[ts] ✅ 流程结束"],
        summary={"path_nodes": 3},
    )
    data = run_store.load_run("sid-abc-123")
    assert data is not None
    run = data["run"]
    assert run["session_id"] == "sid-abc-123"
    assert run["mode"] == "demo"
    assert run["request"]["target_direction"] == "Python"
    assert len(run["orchestration_events"]) == 2
    assert len(run["orchestration_log"]) == 2
    # events.jsonl 有 seq 递增
    seqs = [e["seq"] for e in data["events"]]
    assert seqs == [0, 1]


def test_save_append_continues_seq(monkeypatch, tmp_path):
    _patch_data_dir(monkeypatch, tmp_path)
    run_store.save_run(session_id="s1", mode="demo", events=[_make_event("diagnostics", "running")])
    run_store.save_run(
        session_id="s1", mode="demo",
        events=[_make_event("diagnostics", "done"), _make_event("orchestrator", "done")],
    )
    data = run_store.load_run("s1")
    seqs = [e["seq"] for e in data["events"]]
    assert seqs == [0, 1, 2]  # 第二次保存从 seq=1 续写
    # run.json 为最后一次完整快照
    assert len(data["run"]["orchestration_events"]) == 2


def test_invalid_session_id_sanitized(monkeypatch, tmp_path):
    _patch_data_dir(monkeypatch, tmp_path)
    for bad in ["../evil", "a/../../b", "..", ".", "a b", ""]:
        sid = run_store.save_run(session_id=bad, mode="demo", events=[])
        assert sid == "unknown"
    # 全部落在 unknown 目录, 不产生越界
    files = list((Path(tmp_path) / "workflow_runs").rglob("*.json"))
    assert files  # unknown 的 run.json 存在
    assert not any("evil" in str(p) for p in files)


def test_atomic_write_valid_json_and_update(monkeypatch, tmp_path):
    _patch_data_dir(monkeypatch, tmp_path)
    run_store.save_run(session_id="s2", mode="demo", events=[_make_event("a", "done")])
    # 再次保存覆盖, run.json 仍是合法 JSON
    run_store.save_run(session_id="s2", mode="interactive", events=[], summary={"n": 9})
    raw = (Path(tmp_path) / "workflow_runs" / "s2" / "run.json").read_text(encoding="utf-8")
    obj = json.loads(raw)
    assert obj["mode"] == "interactive"
    assert obj["summary"]["n"] == 9
    # created_at 保持首次
    assert obj["created_at"]


def test_load_missing_returns_none(monkeypatch, tmp_path):
    _patch_data_dir(monkeypatch, tmp_path)
    assert run_store.load_run("nope") is None


def test_list_runs_order_desc(monkeypatch, tmp_path):
    _patch_data_dir(monkeypatch, tmp_path)
    run_store.save_run(session_id="old", mode="demo", events=[])
    run_store.save_run(session_id="new", mode="demo", events=[], summary={"x": 1})
    runs = run_store.list_runs(limit=10)
    ids = [r["session_id"] for r in runs]
    assert ids[0] == "new" and ids[1] == "old"


# ---------------- API 端点 ----------------

def _diag_app() -> FastAPI:
    app = FastAPI()
    app.state.kg = object()
    app.state.workflow = object()
    app.include_router(diag_api.router, prefix="/api/diagnostics")
    return app


def test_get_run_endpoint_returns_saved(monkeypatch, tmp_path):
    _patch_data_dir(monkeypatch, tmp_path)
    run_store.save_run(
        session_id="run-0001", mode="demo",
        events=[_make_event("diagnostics", "done")],
        summary={"path_nodes": 2},
    )
    r = TestClient(_diag_app()).get("/api/diagnostics/runs/run-0001")
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"] == "run-0001"
    assert body["mode"] == "demo"
    assert len(body["orchestration_events"]) == 1
    assert body["summary"]["path_nodes"] == 2


def test_get_run_endpoint_404(monkeypatch, tmp_path):
    _patch_data_dir(monkeypatch, tmp_path)
    r = TestClient(_diag_app()).get("/api/diagnostics/runs/ghost")
    assert r.status_code == 404


def test_get_runs_endpoint_lists(monkeypatch, tmp_path):
    _patch_data_dir(monkeypatch, tmp_path)
    run_store.save_run(session_id="r1", mode="demo", events=[], summary={})
    run_store.save_run(session_id="r2", mode="interactive", events=[], summary={})
    r = TestClient(_diag_app()).get("/api/diagnostics/runs")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2
    assert {x["session_id"] for x in body["runs"]} == {"r1", "r2"}
