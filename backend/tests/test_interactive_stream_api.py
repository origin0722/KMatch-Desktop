"""interactive 流式端点单测 (v1.3.3 等待优化感知层)。

覆盖:
  - /submit/stream: start/progress/done 事件序列 + 错误事件 (404 session)
  - /feedback/stream: search/generate 进度事件 + done
  - /report/stream: path/generate/review 进度 + done + 缓存命中直返
  - content_generator 节点: progress_cb 逐资源打点 / cancel_check 提前收摊 (「已取消」失败)
  - regenerate_for_feedback: cancel_check → 「已取消」失败记录

用 TestClient 收完整 SSE body 后按 \\n\\n 分帧断言 (worker 为 mock, 秒级完成)。
"""

import json
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import diagnostics as diag_api
from app.api import learning as learning_api
from app.agents import content_generator as cg


# ---- SSE body 解析 ----

def _parse_sse(text: str):
    """按 \\n\\n 分帧 → [(event, data_dict)]。"""
    events = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        event = None
        data = None
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data = json.loads(line[len("data:"):].strip())
        events.append((event, data))
    return events


def _events_of(events, name):
    return [d for e, d in events if e == name]


_FAKE_QUESTIONS = [
    {"node_id": "PY-005", "question": "q0", "answer": "A", "type": "choice", "difficulty": 2},
    {"node_id": "PY-005", "question": "q1", "answer": "对", "type": "judge", "difficulty": 2},
]
_FAKE_NODES = [{"node_id": "PY-005", "name": "循环", "difficulty": 2}]


def _build_submit_app(monkeypatch):
    """复用 test_submit_api 的夹具思路: fake 出题/判分/画像, 注册 diagnostics 路由。"""
    diag_api._INTERACTIVE_SESSIONS.clear()
    monkeypatch.setattr(diag_api, "llm_configured", lambda: True)
    monkeypatch.setattr(diag_api, "resolve_direction", lambda kg, target, known: ("unknown", []))
    monkeypatch.setattr(diag_api, "prepare_questions",
                        lambda kg, target, known, nodes=None: (_FAKE_QUESTIONS, _FAKE_NODES))

    def _fake_grade(questions, answers):
        return {"per_node": {}, "correct_count": 1, "total_count": 2}
    monkeypatch.setattr(diag_api, "_grade", _fake_grade)
    monkeypatch.setattr(
        diag_api, "_build_profile",
        lambda target, nodes, grading, **kw: {
            "theory_level": 2, "known_topics": [], "weak_topics": [],
            "recommended_path": {"current_node": "PY-005", "next_nodes": [], "estimated_completion_weeks": 4},
        },
    )
    app = FastAPI()
    app.state.kg = MagicMock()
    app.include_router(diag_api.router, prefix="/api/diagnostics")
    return app


# ============================================================
# /submit/stream
# ============================================================

def test_submit_stream_progress_and_done(monkeypatch):
    """submit 流式: start → progress(判分→画像→路径) → done(完整 SubmitResponse 结构)。"""
    app = _build_submit_app(monkeypatch)
    client = TestClient(app)
    sid = client.post("/api/diagnostics/assess", json={
        "target_direction": "Python 入门", "mode": "interactive",
    }).json()["session_id"]

    resp = client.post("/api/diagnostics/submit/stream", json={
        "session_id": sid, "answers": ["A", "错"],
    })
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]

    events = _parse_sse(resp.text)
    assert events[0][0] == "start" and events[0][1]["session_id"] == sid

    progresses = _events_of(events, "progress")
    steps = [p["step"] for p in progresses]
    assert "grading" in steps and "grading_done" in steps and "profile" in steps and "path" in steps
    done = _events_of(events, "done")
    assert len(done) == 1
    assert done[0]["assessment"]["correct_count"] == 1
    assert done[0]["feedback"]["strategy"] == "remediate"  # 1/2
    assert "error" not in [e for e, _ in events]


def test_submit_stream_unknown_session_error_event(monkeypatch):
    """session 不存在 → SSE error 事件带 status 404 (HTTP 层仍 200, 前端按事件降级)。"""
    app = _build_submit_app(monkeypatch)
    client = TestClient(app)
    resp = client.post("/api/diagnostics/submit/stream", json={
        "session_id": "no-such", "answers": [],
    })
    assert resp.status_code == 200
    errors = _events_of(_parse_sse(resp.text), "error")
    assert len(errors) == 1 and errors[0]["status"] == 404


# ============================================================
# /feedback/stream
# ============================================================

def test_feedback_stream_progress_events(monkeypatch):
    """feedback 流式: 无 Tavily → generate 进度 (由 fake 再生回调驱动) → done。"""
    app = _build_submit_app(monkeypatch)
    monkeypatch.setattr(diag_api.settings, "TAVILY_API_KEY", "")  # 关联网搜索分支

    seen = {}

    def fake_regen(strategy, profile, learning_path, kg, progress_cb=None, cancel_check=None):
        seen["has_cb"] = callable(progress_cb)
        node = {"node_id": "PY-005", "name": "循环"}
        progress_cb(1, 3, node, "lecture")
        progress_cb(2, 3, node, "test")
        return {"resources": [{"target_node_id": "PY-005"}], "node_count": 1, "generation_failures": []}

    monkeypatch.setattr(diag_api, "regenerate_for_feedback", fake_regen)

    client = TestClient(app)
    sid = client.post("/api/diagnostics/assess", json={
        "target_direction": "Python 入门", "mode": "interactive",
    }).json()["session_id"]

    resp = client.post("/api/diagnostics/feedback/stream", json={
        "session_id": sid, "strategy": "remediate", "profile": {"theory_level": 2},
    })
    assert resp.status_code == 200
    assert seen["has_cb"] is True

    events = _parse_sse(resp.text)
    gen = [p for p in _events_of(events, "progress") if p["step"] == "generate"]
    assert [g["done"] for g in gen] == [1, 2]
    assert "循环·讲义" in gen[0]["message"]  # CONTENT_TYPE_LABELS 中文标签
    done = _events_of(events, "done")
    assert done and done[0]["strategy"] == "remediate"


# ============================================================
# /report/stream
# ============================================================

def _build_report_app(monkeypatch):
    """复用 test_learning_report 夹具思路: fake 三个 node 工厂 + 裁判 + 报告组装。"""
    diag_api._INTERACTIVE_SESSIONS.clear()
    monkeypatch.setattr(learning_api, "llm_configured", lambda: True)

    kg_result = {
        "learning_path": [{"node_id": "PY-005", "name": "循环", "difficulty": 2}],
        "path_node_ids": ["PY-005"],
    }
    content_result = {
        "resources": [{"target_node_id": "PY-005", "content_type": "lecture", "content": "x"}],
        "node_count": 1,
    }
    review_result = {"passed": True, "overall_score": 0.9}

    def _gc_factory(kg):
        def _n(state):
            return {"knowledge_graph": kg_result, "orchestration_log": ["gc done"]}
        return _n

    def _cg_factory(kg):
        def _n(state, progress_cb=None, cancel_check=None):
            if progress_cb:
                progress_cb(1, 3, {"node_id": "PY-005", "name": "循环"}, "lecture")
                progress_cb(2, 3, {"node_id": "PY-005", "name": "循环"}, "test")
                progress_cb(3, 3, {"node_id": "PY-005", "name": "循环"}, "test")
            return {"generated_content": content_result, "content_phase_entered": True,
                    "orchestration_log": ["cg done"]}
        return _n

    def _rv_factory(kg):
        def _n(state):
            return {"review_results": review_result,
                    "retry_count": state.get("retry_count", 0) + 1,
                    "orchestration_log": ["rv done"]}
        return _n

    monkeypatch.setattr(learning_api, "graph_controller_node", _gc_factory)
    monkeypatch.setattr(learning_api, "content_generator_node", _cg_factory)
    monkeypatch.setattr(learning_api, "reviewer_node", _rv_factory)
    monkeypatch.setattr(learning_api, "build_learning_report", lambda *a, **k: {"review_status": {}})
    # 裁判: 惰性导入 app.agents.quality_judge.judge_hallucination → 返回可聚合摘要
    import app.agents.quality_judge as qj
    monkeypatch.setattr(qj, "judge_hallucination",
                        lambda resources, kg: {"total": 1, "grounded": 1, "hallucinated": 0,
                                               "unverifiable": 0, "verdicts": []})

    app = FastAPI()
    app.state.kg = MagicMock()
    app.include_router(learning_api.router, prefix="/api/learning")
    return app


def _seed_session():
    sid = "stream-report-001"
    diag_api._INTERACTIVE_SESSIONS[sid] = {
        "questions": [], "nodes": [], "target_direction": "Python",
        "known_topics": [],
        "profile": {"theory_level": 2, "known_topics": [], "weak_topics": [],
                    "recommended_path": {"current_node": "", "next_nodes": [], "estimated_completion_weeks": 0}},
    }
    return sid


def test_report_stream_progress_and_done(monkeypatch):
    app = _build_report_app(monkeypatch)
    sid = _seed_session()
    client = TestClient(app)

    resp = client.post("/api/learning/report/stream", json={"session_id": sid})
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]

    events = _parse_sse(resp.text)
    steps = [p["step"] for p in _events_of(events, "progress")]
    assert "path" in steps and "generate" in steps and "review" in steps and "judge" in steps
    gen = [p for p in _events_of(events, "progress") if p["step"] == "generate" and "done" in p]
    assert [g["done"] for g in gen] == [1, 2, 3]  # 逐资源进度 (阶段级 generate 事件无 done 字段)
    done = _events_of(events, "done")
    assert done and done[0]["learning_report"] == {"review_status": {}}
    # 缓存已回写 (compute 完成)
    assert diag_api._INTERACTIVE_SESSIONS[sid]["learning_report_cache"]


def test_report_stream_cached_returns_directly(monkeypatch):
    """缓存命中 → stream 端点直接同步返回 JSON (非 text/event-stream)。"""
    app = _build_report_app(monkeypatch)
    sid = _seed_session()
    diag_api._INTERACTIVE_SESSIONS[sid]["learning_report_cache"] = {"review_status": {}}
    client = TestClient(app)

    resp = client.post("/api/learning/report/stream", json={"session_id": sid})
    assert resp.status_code == 200
    assert "text/event-stream" not in resp.headers["content-type"]
    assert resp.json()["learning_report"] == {"review_status": {}}


# ============================================================
# content_generator 节点: 逐资源进度 / 取消检查点
# ============================================================

def _gen_state(n_nodes=2):
    nodes = [{"node_id": f"PY-00{i}", "name": f"节点{i}", "difficulty": 2} for i in range(1, n_nodes + 1)]
    return {
        "user_profile": {"theory_level": 2},
        "knowledge_graph": {"learning_path": nodes},
        "content_phase_entered": False,
        "orchestration_log": [],
    }


def test_content_generator_progress_cb(monkeypatch):
    """每段资源完成回调一次 progress_cb (done 单调递增至 total)。"""
    monkeypatch.setattr(cg, "llm_configured", lambda: True)

    def _fake_generate_one(node, theory_level, ctype, retry_hint, style_extra, **kw):
        # 对齐真实 _generate_one: 返回资源 dict (safe_llm_call 外层才包 (ok, res))
        return {"content": "# t", "content_type": ctype, "target_node_id": node["node_id"]}
    monkeypatch.setattr(cg, "_generate_one", _fake_generate_one)

    progress = []
    node_fn = cg.content_generator_node(MagicMock())
    delta = node_fn(_gen_state(2), progress_cb=lambda d, t, n, ct: progress.append((d, t, n["node_id"], ct)))

    total = 2 * len(cg.CONTENT_TYPES)
    assert [p[0] for p in progress] == list(range(1, total + 1))
    assert all(p[1] == total for p in progress)
    assert len(delta["generated_content"]["resources"]) == total
    assert delta["generated_content"]["generation_failures"] == []


def test_content_generator_cancel_checkpoint(monkeypatch):
    """cancel_check 恒真 → 第 1 段完成后收摊: 1 成功 + 其余「已取消」失败。"""
    monkeypatch.setattr(cg, "llm_configured", lambda: True)

    def _fake_generate_one(node, theory_level, ctype, retry_hint, style_extra, **kw):
        # 对齐真实 _generate_one: 返回资源 dict (safe_llm_call 外层才包 (ok, res))
        return {"content": "# t", "content_type": ctype, "target_node_id": node["node_id"]}
    monkeypatch.setattr(cg, "_generate_one", _fake_generate_one)

    progress = []
    node_fn = cg.content_generator_node(MagicMock())
    delta = node_fn(_gen_state(2), progress_cb=lambda d, t, n, c: progress.append(d),
                    cancel_check=lambda: True)

    total = 2 * len(cg.CONTENT_TYPES)
    assert progress == [1]  # 只上报了第 1 段
    assert len(delta["generated_content"]["resources"]) == 1
    failures = delta["generated_content"]["generation_failures"]
    assert len(failures) == total - 1
    assert all("已取消" in f["reason"] for f in failures)


def test_regenerate_for_feedback_cancel(monkeypatch):
    """feedback 再生: cancel_check 恒真 → 已完成 1 段保留, 其余记「已取消」。"""
    monkeypatch.setattr(cg, "llm_configured", lambda: True)

    def _fake_one(node, theory_level, ctype, log_hint, style_extra, **kw):
        return {"content": "# t", "content_type": ctype, "target_node_id": node["node_id"]}
    monkeypatch.setattr(cg, "_generate_feedback_one", _fake_one)

    profile = {"theory_level": 2, "weak_topics": [{"node_id": "PY-001", "name": "弱项"}]}
    path = [{"node_id": "PY-001", "name": "弱项", "difficulty": 2}]
    result = cg.regenerate_for_feedback("remediate", profile, path, MagicMock(),
                                        cancel_check=lambda: True)
    # 取消语义: 检查点在首个任务完成后才触发 → 1 段已完成保留, 其余记「已取消」
    total = len(cg.CONTENT_TYPES)
    assert len(result["resources"]) == 1
    assert len(result["generation_failures"]) == total - 1
    assert all("已取消" in f["reason"] for f in result["generation_failures"])


def test_report_cancel_skips_cache_writeback(monkeypatch):
    """终审回归: 用户停止等待 → content_generator 返回「已取消」失败记录 → 缓存不回写。

    此前取消路径不抛异常, 半成品报告被无条件回写并被幂等命中永久卡住 (审查发现)。
    """
    app = _build_report_app(monkeypatch)
    sid = _seed_session()
    # 替换 content_generator fake: cancel_check 恒真 → 半成品 delta + 「已取消」失败记录
    content_cancelled = {
        "resources": [], "node_count": 1,
        "generation_failures": [{"node_id": "PY-005", "content_type": "lecture",
                                 "reason": "已取消（用户停止等待）"}],
    }
    def _cg_cancel(kg):
        def _n(state, progress_cb=None, cancel_check=None):
            assert cancel_check is not None
            return {"generated_content": content_cancelled, "content_phase_entered": True,
                    "orchestration_log": ["cg cancelled"]}
        return _n
    monkeypatch.setattr(learning_api, "content_generator_node", _cg_cancel)

    client = TestClient(app)
    resp = client.post("/api/learning/report/stream", json={"session_id": sid})
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    done = _events_of(events, "done")
    assert done  # 流正常收尾
    # 关键断言: 缓存未被回写 (重试将重新完整补跑)
    assert diag_api._INTERACTIVE_SESSIONS[sid].get("learning_report_cache") is None
