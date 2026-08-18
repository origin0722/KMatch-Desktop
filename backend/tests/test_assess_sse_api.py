"""assess/stream SSE 端点单测 — mock workflow.stream, 验证事件流格式。

TestClient 对 StreamingResponse 会同步消费完整 body, 故用 text/event-stream
解析整段验证 start/progress/done 事件。免真实 LLM/Neo4j。
"""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import diagnostics as diag_api


class _FakeWorkflow:
    """fake workflow: stream 产出预设节点 chunks (stream_mode=updates 格式)。"""
    def __init__(self, chunks):
        self._chunks = chunks  # [{"diagnostics": {...}}, {"reviewer": {...}}, ...]

    def stream(self, initial, config, stream_mode=None):
        yield from self._chunks


def _build_app(monkeypatch, chunks, fail=False):
    diag_api._INTERACTIVE_SESSIONS.clear()
    # Phase 1: SSE done 会经 _persist_run 落盘 settings.DATA_DIR → 指向临时目录,
    # 避免测试往仓库 data/workflow_runs 写真实 run 文件。
    from tempfile import mkdtemp
    from pathlib import Path as _Path
    from app.config import settings as _settings
    monkeypatch.setattr(_settings, "DATA_DIR", _Path(mkdtemp(prefix="kmatch-run-store-test-")))

    workflow = _FakeWorkflow(chunks)
    monkeypatch.setattr(diag_api, "_get_workflow", lambda request: workflow)
    monkeypatch.setattr(diag_api, "_get_kg", lambda request: MagicMock())
    # mock build_learning_report: 返回最小报告
    monkeypatch.setattr(diag_api, "build_learning_report",
                        lambda *a, **kw: {"quality_metrics": {"all_passed": True}})
    app = FastAPI()
    app.state.kg = MagicMock()
    app.state.workflow = workflow
    app.include_router(diag_api.router, prefix="/api/diagnostics")
    return app


def _parse_sse(text):
    """解析 SSE 文本 → [(event, data_dict), ...]。"""
    events = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event = None
        data = None
        for line in block.split("\n"):
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: "):
                import json
                data = json.loads(line[6:])
        if event:
            events.append((event, data))
    return events


def test_sse_stream_emits_start_progress_done(monkeypatch):
    """完整流程: start → 多个 progress → done。"""
    chunks = [
        {"diagnostics": {"user_profile": {"theory_level": 2}, "orchestration_log": ["📝 出题"]}},
        {"reviewer": {"review_results": {"passed": True}}},
        {"graph_controller": {"knowledge_graph": {"learning_path": [{"node_id": "PY-005"}]}}},
        {"content_generator": {"generated_content": {"resources": []}, "orchestration_log": ["✅ 生成"]}},
        {"finish": {"orchestration_log": ["结束"]}},
    ]
    app = _build_app(monkeypatch, chunks)
    r = TestClient(app).post("/api/diagnostics/assess/stream",
                             json={"target_direction": "Python", "mode": "demo"})
    assert r.status_code == 200
    assert "text/event-stream" in r.headers.get("content-type", "")
    events = _parse_sse(r.text)
    event_names = [e for e, _ in events]
    assert event_names[0] == "start"
    assert "progress" in event_names
    assert event_names[-1] == "done"
    # done 含完整结果字段
    done_data = events[-1][1]
    assert "session_id" in done_data
    assert "profile" in done_data
    assert "learning_report" in done_data


def test_sse_progress_includes_node_and_message(monkeypatch):
    chunks = [{"diagnostics": {"orchestration_log": ["log1", "log2", "log3"]}}]
    app = _build_app(monkeypatch, chunks)
    r = TestClient(app).post("/api/diagnostics/assess/stream",
                             json={"target_direction": "Python", "mode": "demo"})
    events = _parse_sse(r.text)
    progress = [d for e, d in events if e == "progress"]
    assert len(progress) >= 1
    assert progress[0]["node"] == "diagnostics"
    assert "学情检测" in progress[0]["message"]
    assert len(progress[0]["log_tail"]) == 3  # 尾部3条


def test_sse_interactive_mode_rejected_400(monkeypatch):
    """interactive 模式应拒绝 (用 /assess 而非 stream)。"""
    app = _build_app(monkeypatch, [])
    r = TestClient(app).post("/api/diagnostics/assess/stream",
                             json={"target_direction": "Python", "mode": "interactive"})
    assert r.status_code == 400


def test_sse_workflow_error_emits_error_event(monkeypatch):
    """workflow.stream 抛异常 → error 事件。"""
    class _FailWorkflow:
        def stream(self, *a, **kw):
            raise RuntimeError("模拟 LLM 故障")
            yield  # 使其为 generator
    app = FastAPI()
    app.state.kg = MagicMock()
    monkeypatch.setattr(diag_api, "_get_workflow", lambda request: _FailWorkflow())
    monkeypatch.setattr(diag_api, "_get_kg", lambda request: MagicMock())
    app.include_router(diag_api.router, prefix="/api/diagnostics")
    r = TestClient(app).post("/api/diagnostics/assess/stream",
                             json={"target_direction": "Python", "mode": "demo"})
    assert r.status_code == 200  # SSE 流本身 200, 错误在事件里
    events = _parse_sse(r.text)
    assert any(e == "error" for e, _ in events)
