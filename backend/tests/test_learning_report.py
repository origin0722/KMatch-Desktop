"""可视化报告数据接口单测 — build_learning_report 纯函数 + /api/learning/report 端点。

覆盖:
  A. build_learning_report 纯函数 (无 mock): blind_spots/difficulty_match/learning_path 三子对象 + 全空健壮
  B. /api/learning/report 端点 (TestClient+fake kg+monkeypatch): 幂等/404/409/503/补跑happy/reviewer不通过/缓存回写
  C. demo assess 内联 learning_report (扩展)
"""

import json
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agents.report_builder import (
    build_learning_report,
    _mastery_status,
    _match_status,
)
from app.api import diagnostics as diag_api
from app.api import learning as learning_api


# ============================================================
# A. 纯函数: _mastery_status / _match_status
# ============================================================

def test_mastery_status_three_tier():
    assert _mastery_status(0.9) == "mastered"
    assert _mastery_status(0.8) == "mastered"
    assert _mastery_status(0.7) == "learning"
    assert _mastery_status(0.5) == "learning"
    assert _mastery_status(0.4) == "weak"
    assert _mastery_status(0.0) == "weak"


def test_match_status_thresholds():
    assert _match_status(0) == "matched"
    assert _match_status(1) == "matched"
    assert _match_status(-1) == "matched"
    assert _match_status(2) == "too_hard"
    assert _match_status(-2) == "too_easy"


# ============================================================
# A. build_learning_report 纯函数
# ============================================================

def _sample_profile():
    return {
        "theory_level": 3,
        "known_topics": [{"node_id": "PY-001", "mastery": 0.9}],
        "weak_topics": [
            {"node_id": "PY-005", "mastery": 0.25, "error_patterns": ["错题: 循环变量未更新"]},
            {"node_id": "PY-008", "mastery": 0.6, "error_patterns": ["返回值理解有误"]},
        ],
        "recommended_path": {
            "current_node": "PY-005",
            "next_nodes": ["PY-008", "PY-012"],
            "estimated_completion_weeks": 4,
        },
    }


def _sample_kg():
    return {
        "learning_path": [
            {"node_id": "PY-005", "name": "循环", "difficulty": 2, "estimated_minutes": 60},
            {"node_id": "PY-008", "name": "函数", "difficulty": 3, "estimated_minutes": 90},
            {"node_id": "PY-012", "name": "类", "difficulty": 4, "estimated_minutes": 120},
        ],
        "path_node_ids": ["PY-005", "PY-008", "PY-012"],
        "estimated_total_hours": 4.5,
        "node_status_updates": {"PY-005": "difficult", "PY-008": "in_progress"},
        "assembled_at": "2026-06-19T00:00:00Z",
    }


def _sample_gen_content():
    # PY-005(难度2): lecture=2(matched), practice=3(too_hard gap1? gap=1 matched), test=4(too_hard)
    # PY-008(难度3): lecture=2(too_easy gap=-1 matched), test=5(too_hard gap=2)
    return {
        "resources": [
            {"target_node_id": "PY-005", "content_type": "lecture", "difficulty_level": 2},
            {"target_node_id": "PY-005", "content_type": "practice_guide", "difficulty_level": 3},
            {"target_node_id": "PY-005", "content_type": "test", "difficulty_level": 4},
            {"target_node_id": "PY-008", "content_type": "lecture", "difficulty_level": 2},
            {"target_node_id": "PY-008", "content_type": "test", "difficulty_level": 5},
        ],
        "node_count": 2,
    }


def _sample_review():
    return {"passed": True, "overall_score": 0.9, "threshold": 0.85}


def test_build_blind_spots():
    report = build_learning_report(_sample_profile(), _sample_kg(), _sample_gen_content(), _sample_review())
    bs = report["blind_spots"]
    # 仅被测节点: PY-001(known) + PY-005/008(weak) = 3
    ids = [n["node_id"] for n in bs["nodes"]]
    assert set(ids) == {"PY-001", "PY-005", "PY-008"}
    # mastery 升序 (PY-005=0.25 最前)
    assert bs["nodes"][0]["node_id"] == "PY-005"
    # status 三段制
    by_id = {n["node_id"]: n for n in bs["nodes"]}
    assert by_id["PY-001"]["status"] == "mastered"
    assert by_id["PY-008"]["status"] == "learning"
    assert by_id["PY-005"]["status"] == "weak"
    # error_patterns 仅 weak 有
    assert by_id["PY-005"]["error_patterns"] != []
    assert by_id["PY-001"]["error_patterns"] == []
    # name/difficulty 从 learning_path 富化
    assert by_id["PY-005"]["name"] == "循环"
    assert by_id["PY-005"]["difficulty"] == 2
    # summary 计数
    assert bs["summary"]["total"] == 3
    assert bs["summary"]["mastered"] == 1
    assert bs["summary"]["learning"] == 1
    assert bs["summary"]["weak"] == 1
    # overall_mastery = (0.9+0.25+0.6)/3
    assert abs(bs["summary"]["overall_mastery"] - round(1.75 / 3, 3)) < 0.001


def test_build_blind_spots_node_not_in_path():
    """盲区节点不在 learning_path → name 回退 node_id, difficulty=0。"""
    profile = {"known_topics": [], "weak_topics": [{"node_id": "PY-999", "mastery": 0.1, "error_patterns": []}]}
    report = build_learning_report(profile, {"learning_path": []}, {}, {})
    n = report["blind_spots"]["nodes"][0]
    assert n["name"] == "PY-999"
    assert n["difficulty"] == 0


def test_build_difficulty_match():
    report = build_learning_report(_sample_profile(), _sample_kg(), _sample_gen_content(), _sample_review())
    dm = report["difficulty_match"]
    # per-resource: 5 段 → 5 点
    assert len(dm["points"]) == 5
    # gap 带符号: PY-005(2) lecture(2) → gap=0 matched
    p0 = dm["points"][0]
    assert p0["node_difficulty"] == 2
    assert p0["resource_difficulty"] == 2
    assert p0["gap"] == 0
    assert p0["match_status"] == "matched"
    assert p0["path_position"] == 0
    # PY-005 test(4) → gap=2 too_hard
    p2 = [p for p in dm["points"] if p["content_type"] == "test" and p["node_id"] == "PY-005"][0]
    assert p2["gap"] == 2
    assert p2["match_status"] == "too_hard"
    # PY-008(3) lecture(2) → gap=-1 matched
    p3 = [p for p in dm["points"] if p["content_type"] == "lecture" and p["node_id"] == "PY-008"][0]
    assert p3["gap"] == -1
    assert p3["match_status"] == "matched"
    # PY-008 test(5) → gap=2 too_hard
    p4 = [p for p in dm["points"] if p["content_type"] == "test" and p["node_id"] == "PY-008"][0]
    assert p4["match_status"] == "too_hard"
    # mastery 取自 profile (PY-005=0.25)
    assert p0["mastery"] == 0.25
    # summary
    assert dm["summary"]["total_resources"] == 5
    assert dm["summary"]["too_hard"] == 2  # PY-005 test, PY-008 test
    assert dm["summary"]["matched"] == 3


def test_build_difficulty_match_target_not_in_path():
    """resource.target_node_id 不在 learning_path → 点保留, node_difficulty=0, path_position=-1。"""
    gen = {"resources": [{"target_node_id": "PY-999", "content_type": "lecture", "difficulty_level": 3}]}
    report = build_learning_report({}, {"learning_path": [{"node_id": "PY-005", "name": "循环", "difficulty": 2}]}, gen, {})
    p = report["difficulty_match"]["points"][0]
    assert p["node_difficulty"] == 0
    assert p["path_position"] == -1
    assert p["name"] == "PY-999"
    assert p["gap"] == 3  # 3 - 0
    assert p["match_status"] == "too_hard"


def test_build_learning_path_graph():
    report = build_learning_report(_sample_profile(), _sample_kg(), _sample_gen_content(), _sample_review())
    lp = report["learning_path"]
    # 3 节点按路径顺序
    assert [n["node_id"] for n in lp["nodes"]] == ["PY-005", "PY-008", "PY-012"]
    # is_current 仅 current_node
    cur = [n for n in lp["nodes"] if n["is_current"]]
    assert len(cur) == 1 and cur[0]["node_id"] == "PY-005"
    # status 来自 node_status_updates
    by_id = {n["node_id"]: n for n in lp["nodes"]}
    assert by_id["PY-005"]["status"] == "difficult"
    assert by_id["PY-008"]["status"] == "in_progress"
    # PY-012 不在 status_updates 且无 mastery → unlearned
    assert by_id["PY-012"]["status"] == "unlearned"
    # PATH_SEQUENCE 边: N-1=2 条
    seq = [e for e in lp["edges"] if e["type"] == "PATH_SEQUENCE"]
    assert len(seq) == 2
    assert seq[0] == {"source": "PY-005", "target": "PY-008", "type": "PATH_SEQUENCE"}
    # 透传字段
    assert lp["estimated_total_hours"] == 4.5
    assert lp["path_length"] == 3
    assert lp["current_node"] == "PY-005"
    assert lp["next_nodes"] == ["PY-008", "PY-012"]
    assert lp["estimated_completion_weeks"] == 4


def test_build_learning_path_graph_requires_edges():
    """kg 可用时取 REQUIRES 前置边 (仅路径内)。"""
    class _FakeKG:
        def get_prerequisites(self, nid):
            if nid == "PY-008":
                return [{"node_id": "PY-005"}]  # PY-005 在路径内
            if nid == "PY-012":
                return [{"node_id": "PY-008"}, {"node_id": "PY-001"}]  # PY-001 不在路径内
            return []
    report = build_learning_report(_sample_profile(), _sample_kg(), {}, {}, kg=_FakeKG())
    req = [e for e in report["learning_path"]["edges"] if e["type"] == "REQUIRES"]
    # PY-005→PY-008 一条 (PY-001 不在路径内不计); PY-008→PY-012 一条
    assert {"source": "PY-005", "target": "PY-008", "type": "REQUIRES"} in req
    assert {"source": "PY-008", "target": "PY-012", "type": "REQUIRES"} in req
    # PY-001 前置不在路径内 → 不出现
    assert not any(e["source"] == "PY-001" for e in req)


def test_build_report_review_status_and_meta():
    report = build_learning_report(_sample_profile(), _sample_kg(), _sample_gen_content(), _sample_review())
    assert report["review_status"] == {"passed": True, "overall_score": 0.9, "threshold": 0.85}
    assert "generated_at" in report


def test_build_report_all_empty():
    """全空入参 → 三子对象空结构, 不抛异常 (契约完整性)。"""
    report = build_learning_report({}, {}, {}, {})
    assert report["blind_spots"]["nodes"] == []
    assert report["blind_spots"]["summary"]["total"] == 0
    assert report["difficulty_match"]["points"] == []
    assert report["difficulty_match"]["summary"]["total_resources"] == 0
    assert report["learning_path"]["nodes"] == []
    assert report["learning_path"]["edges"] == []
    assert report["learning_path"]["path_length"] == 0
    assert report["review_status"]["passed"] is False


def test_build_report_empty_resources_not_crash():
    """generated_content 无 resources → difficulty_match.points 空, 其余正常。"""
    report = build_learning_report(_sample_profile(), _sample_kg(), {}, _sample_review())
    assert report["difficulty_match"]["points"] == []
    assert report["blind_spots"]["summary"]["total"] == 3  # 画像节点仍算


# ============================================================
# B. /api/learning/report 端点
# ============================================================

def _fake_node_factory(calls: list, kg_result: dict, content_result: dict, review_result: dict):
    """构造三个 fake node 工厂, 记录调用次数, 返回固定 delta。"""
    def _gc_factory(kg):
        def _n(state):
            calls.append("graph_controller")
            return {"knowledge_graph": kg_result, "orchestration_log": ["gc done"]}
        return _n
    def _cg_factory(kg):
        def _n(state):
            calls.append("content_generator")
            return {"generated_content": content_result, "content_phase_entered": True, "orchestration_log": ["cg done"]}
        return _n
    def _rv_factory(kg):
        def _n(state):
            calls.append("reviewer")
            # 对齐真实 reviewer_node: retry_count 由审核节点自增 (W7 回环终止条件)
            return {"review_results": review_result,
                    "retry_count": state.get("retry_count", 0) + 1,
                    "orchestration_log": ["rv done"]}
        return _n
    return _gc_factory, _cg_factory, _rv_factory


def _build_learning_app(monkeypatch, review_result=None):
    """构造带 fake kg 的 app, 注册 diagnostics + learning 路由, monkeypatch node 函数。"""
    diag_api._INTERACTIVE_SESSIONS.clear()

    review_result = review_result or {"passed": True, "overall_score": 0.9, "threshold": 0.85}
    kg_result = {
        "learning_path": [{"node_id": "PY-005", "name": "循环", "difficulty": 2, "estimated_minutes": 60}],
        "path_node_ids": ["PY-005"], "estimated_total_hours": 1.0,
        "node_status_updates": {"PY-005": "difficult"}, "assembled_at": "2026-06-19T00:00:00Z",
    }
    content_result = {
        "resources": [{"target_node_id": "PY-005", "content_type": "lecture", "difficulty_level": 2}],
        "node_count": 1,
    }

    calls = []
    gc_f, cg_f, rv_f = _fake_node_factory(calls, kg_result, content_result, review_result)
    monkeypatch.setattr(learning_api, "graph_controller_node", gc_f)
    monkeypatch.setattr(learning_api, "content_generator_node", cg_f)
    monkeypatch.setattr(learning_api, "reviewer_node", rv_f)
    monkeypatch.setattr(learning_api, "llm_configured", lambda: True)

    app = FastAPI()
    app.state.kg = MagicMock()  # 非 None 通过 _get_kg
    app.include_router(learning_api.router, prefix="/api/learning")
    app._test_calls = calls  # 挂在 app 供测试断言
    return app


def _seed_session(profile=None):
    """向 session 缓存注入一个已 submit 的会话 (带 profile)。"""
    sid = "test-session-001"
    diag_api._INTERACTIVE_SESSIONS[sid] = {
        "questions": [], "nodes": [], "target_direction": "Python",
        "known_topics": [], "created_at": "2026-06-19T00:00:00",
        "profile": profile if profile is not None else {
            "theory_level": 2, "known_topics": [], "weak_topics": [],
            "recommended_path": {"current_node": "", "next_nodes": [], "estimated_completion_weeks": 0},
        },
    }
    return sid


def test_report_404_unknown_session(monkeypatch):
    app = _build_learning_app(monkeypatch)
    client = TestClient(app)
    resp = client.post("/api/learning/report", json={"session_id": "nope"})
    assert resp.status_code == 404


def test_report_409_profile_not_ready(monkeypatch):
    """session 存在但无 profile (未 submit) → 409。"""
    app = _build_learning_app(monkeypatch)
    diag_api._INTERACTIVE_SESSIONS["s2"] = {"questions": [], "created_at": "x"}  # 无 profile
    client = TestClient(app)
    resp = client.post("/api/learning/report", json={"session_id": "s2"})
    assert resp.status_code == 409


def test_report_503_llm_not_configured(monkeypatch):
    app = _build_learning_app(monkeypatch)
    monkeypatch.setattr(learning_api, "llm_configured", lambda: False)
    sid = _seed_session()
    client = TestClient(app)
    resp = client.post("/api/learning/report", json={"session_id": sid})
    assert resp.status_code == 503


def test_report_happy_path(monkeypatch):
    app = _build_learning_app(monkeypatch)
    sid = _seed_session()
    client = TestClient(app)
    resp = client.post("/api/learning/report", json={"session_id": sid})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # 三个 node 函数各调用一次, 顺序正确
    assert app._test_calls == ["graph_controller", "content_generator", "reviewer"]
    # 返回完整产出
    assert data["knowledge_graph"]["path_node_ids"] == ["PY-005"]
    assert len(data["generated_content"]["resources"]) == 1
    assert data["review_results"]["passed"] is True
    # learning_report 含三子对象
    lr = data["learning_report"]
    assert "blind_spots" in lr and "difficulty_match" in lr and "learning_path" in lr
    assert lr["difficulty_match"]["summary"]["total_resources"] == 1
    assert lr["review_status"]["passed"] is True


def test_report_idempotent_cache(monkeypatch):
    """连续两次同 session → 第二次命中缓存, node 函数不再调用, 返回一致。"""
    app = _build_learning_app(monkeypatch)
    sid = _seed_session()
    client = TestClient(app)

    r1 = client.post("/api/learning/report", json={"session_id": sid})
    assert r1.status_code == 200
    calls_after_first = list(app._test_calls)
    assert len(calls_after_first) == 3

    r2 = client.post("/api/learning/report", json={"session_id": sid})
    assert r2.status_code == 200
    # 第二次未增加 node 调用 (命中缓存)
    assert len(app._test_calls) == 3
    # 两次 learning_report 一致
    assert r1.json()["learning_report"] == r2.json()["learning_report"]


def test_report_reviewer_fail_loops_once(monkeypatch):
    """W7 有界回环: reviewer 首轮不通过 → 定向再生再审 (共 2 轮), 内容仍交付。

    fake reviewer 每轮返回同一 fail 结论且 retry_count 自增 → 恰好打回 1 次
    (retry 达 max=2 后降级结束, 与 demo workflow 语义一致)。
    """
    fail_review = {"passed": False, "overall_score": 0.7, "threshold": 0.85,
                   "retry_hint": "幻觉", "reviewed_at": "2026-06-19T00:00:00Z"}
    app = _build_learning_app(monkeypatch, review_result=fail_review)
    sid = _seed_session()
    client = TestClient(app)
    resp = client.post("/api/learning/report", json={"session_id": sid})
    assert resp.status_code == 200
    data = resp.json()
    # 首轮生成+审核 + 打回再生+再审 = 各 2 次
    assert app._test_calls.count("content_generator") == 2
    assert app._test_calls.count("reviewer") == 2
    # 内容仍交付
    assert len(data["generated_content"]["resources"]) == 1
    # 最终 passed=False, 轮次轨迹 2 轮
    assert data["review_results"]["passed"] is False
    assert len(data["review_rounds"]) == 2
    assert data["review_rounds"][0]["round"] == 1
    assert data["review_rounds"][1]["round"] == 2
    assert data["learning_report"]["review_status"]["passed"] is False


def test_report_review_pass_single_round(monkeypatch):
    """W7: 首轮审核通过 → 不进回环, content_generator/reviewer 各 1 次, 轨迹 1 轮。"""
    app = _build_learning_app(monkeypatch)
    sid = _seed_session()
    client = TestClient(app)
    resp = client.post("/api/learning/report", json={"session_id": sid})
    assert resp.status_code == 200
    data = resp.json()
    assert app._test_calls.count("content_generator") == 1
    assert app._test_calls.count("reviewer") == 1
    assert len(data["review_rounds"]) == 1
    assert data["review_rounds"][0]["passed"] is True


def test_report_cache_writeback(monkeypatch):
    """补跑后 session 缓存写入 knowledge_graph/generated_content/review_results/learning_report_cache。"""
    app = _build_learning_app(monkeypatch)
    sid = _seed_session()
    client = TestClient(app)
    client.post("/api/learning/report", json={"session_id": sid})
    session = diag_api._INTERACTIVE_SESSIONS[sid]
    assert session["knowledge_graph"]["path_node_ids"] == ["PY-005"]
    assert session["generated_content"]["resources"]
    assert session["review_results"]["passed"] is True
    assert "learning_report_cache" in session
    assert session["learning_report_cache"]["difficulty_match"]["summary"]["total_resources"] == 1


# ============================================================
# C. demo assess 内联 learning_report (扩展 test_submit_api 模式)
# ============================================================

def test_report_judge_summary_landed(monkeypatch):
    """赛题(4)① 交叉验证在线闭环: 裁判盲判结果并入 review_results.judge_summary。"""
    app = _build_learning_app(monkeypatch)
    monkeypatch.setattr(learning_api, "_judge_resources", lambda state, kg: {
        "judged": 1, "grounded": 1, "hallucinated": 0, "unverifiable": 0,
        "same_source": False, "verdicts": [],
    })
    sid = _seed_session()
    client = TestClient(app)
    resp = client.post("/api/learning/report", json={"session_id": sid})
    assert resp.status_code == 200, resp.text
    assert resp.json()["review_results"]["judge_summary"]["judged"] == 1


def test_report_judge_failure_degrades(monkeypatch):
    """裁判失败 → 报告仍 200, review_results 不带 judge_summary (降级不阻塞)。"""
    app = _build_learning_app(monkeypatch)

    def _boom(state, kg):
        raise RuntimeError("judge down")

    monkeypatch.setattr(learning_api, "_judge_resources", _boom)
    sid = _seed_session()
    client = TestClient(app)
    resp = client.post("/api/learning/report", json={"session_id": sid})
    assert resp.status_code == 200
    assert "judge_summary" not in resp.json()["review_results"]


def test_demo_assess_inlines_learning_report(monkeypatch):
    """demo assess 响应含 learning_report (三子对象); interactive 出题阶段 learning_report={}。"""
    diag_api._INTERACTIVE_SESSIONS.clear()

    # mock workflow.invoke 返回固定 result (含完整产出)
    fake_result = {
        "user_profile": _sample_profile(),
        "review_results": _sample_review(),
        "assessment": {"questions": [], "correct_count": 7, "total_count": 10},
        "knowledge_graph": _sample_kg(),
        "generated_content": _sample_gen_content(),
        "orchestration_log": ["done"],
    }
    fake_workflow = MagicMock()
    fake_workflow.invoke = MagicMock(return_value=fake_result)

    app = FastAPI()
    app.state.kg = MagicMock()
    app.state.workflow = fake_workflow
    app.include_router(diag_api.router, prefix="/api/diagnostics")
    client = TestClient(app)

    resp = client.post("/api/diagnostics/assess", json={
        "target_direction": "Python 入门", "mode": "demo",
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    lr = data["learning_report"]
    assert lr != {}
    assert "blind_spots" in lr and "difficulty_match" in lr and "learning_path" in lr
    assert lr["difficulty_match"]["summary"]["total_resources"] == 5


def test_interactive_assess_learning_report_empty(monkeypatch):
    """interactive 出题阶段 learning_report 为 {} (回归)。"""
    diag_api._INTERACTIVE_SESSIONS.clear()
    # 域判定走 unknown (阶段16): 不碰 LLM/向量, 直接旧选点行为
    monkeypatch.setattr(
        diag_api, "resolve_direction", lambda kg, target, known: ("unknown", []),
    )
    monkeypatch.setattr(
        diag_api, "prepare_questions",
        lambda kg, target, known, nodes=None: (
            [{"node_id": "PY-005", "question": "q", "answer": "A", "type": "choice", "difficulty": 2}],
            [{"node_id": "PY-005", "name": "循环", "difficulty": 2}],
        ),
    )
    app = FastAPI()
    app.state.kg = MagicMock()
    app.include_router(diag_api.router, prefix="/api/diagnostics")
    client = TestClient(app)

    resp = client.post("/api/diagnostics/assess", json={
        "target_direction": "Python 入门", "mode": "interactive",
    })
    assert resp.status_code == 200
    assert resp.json()["learning_report"] == {}
