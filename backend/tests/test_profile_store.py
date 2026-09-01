"""profile_store 画像档案 (跨次累积/进化) 单测。

覆盖: 首次/进化合并、加权掌握度、跨次 weak 累积 error_patterns、未重测结转、
diff (recovered/newly_known/regressed/newly_weak)、profile_id 复用、耐久存取、
key 去安全化、submit API 带 learner_key 返回 profile_diff。
"""

import json
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agents import profile_store as ps
from app.agents import run_store
from app.api import diagnostics as diag_api


def _patch(monkeypatch, tmp_path):
    from app.config import settings
    monkeypatch.setattr(settings, "DATA_DIR", Path(tmp_path))


def _profile(**kw):
    base = {
        "profile_id": "UP-DIA-aaaaaa",
        "name": "测评用户",
        "theory_level": 2, "practical_level": 1, "learning_style": "read_write",
        "target_direction": "Python",
        "known_topics": [], "weak_topics": [], "weakness_areas": [],
        "recommended_path": {}, "learning_history": [],
    }
    base.update(kw)
    return base


def test_merge_first_run_no_prev():
    p = _profile()
    evolved, diff = ps.merge_profiles(None, p)
    assert evolved["profile_id"] == p["profile_id"]
    assert diff is None


def test_merge_evolution_weighted_and_carry():
    prev = _profile(known_topics=[
        {"node_id": "A", "mastery": 0.9, "last_test_score": 9.0},
        {"node_id": "C", "mastery": 0.95, "last_test_score": 9.5},  # 本轮未重测 → 结转
    ], weak_topics=[
        {"node_id": "B", "mastery": 0.5, "error_patterns": ["索引越界"]},
    ])
    new = _profile(known_topics=[], weak_topics=[
        {"node_id": "B", "mastery": 0.85, "error_patterns": ["索引越界", "负索引"]},
        {"node_id": "D", "mastery": 0.3, "error_patterns": ["切片右界"]},
    ])
    evolved, diff = ps.merge_profiles(prev, new)
    assert evolved["profile_id"] == "UP-DIA-aaaaaa"  # 复用历史 id
    # B: prev 0.5 weak → 本次 0.85 (≥0.8) → 恢复为已掌握, 平滑 0.8*…=0.71→clamp 0.8
    b = next(x for x in evolved["known_topics"] if x["node_id"] == "B")
    assert b["mastery"] == 0.8
    # D 首见 weak
    d = next(x for x in evolved["weak_topics"] if x["node_id"] == "D")
    assert d["mastery"] == 0.3
    # C 未重测结转 (仍 known)
    c = next(x for x in evolved["known_topics"] if x["node_id"] == "C")
    assert c["mastery"] == 0.95
    # 本次高分 → recovered
    assert diff["recovered"] == ["B"]


def test_merge_diff_recovered_regressed_newly():
    prev = _profile(
        known_topics=[{"node_id": "K", "mastery": 0.95}],
        weak_topics=[{"node_id": "R", "mastery": 0.4, "error_patterns": []}],
    )
    new = _profile(
        known_topics=[{"node_id": "R", "mastery": 0.9}],           # 旧薄弱 → 已掌握
        weak_topics=[{"node_id": "K", "mastery": 0.4}, {"node_id": "N", "mastery": 0.2}],
    )
    evolved, diff = ps.merge_profiles(prev, new)
    assert diff["recovered"] == ["R"]
    assert diff["regressed"] == ["K"]
    assert diff["newly_weak"] == ["N"]
    assert diff["summary"]["recovered"] == 1
    # R 新掌握 → 进 evolved known 且带 last_test_score
    assert any(x["node_id"] == "R" and "last_test_score" in x for x in evolved["known_topics"])


def test_merge_carries_topic_name():
    """合并保留知识点名称 (前端按名称展示; 不结转会回退成 PY-xxx 编号)。"""
    prev = _profile(known_topics=[
        {"node_id": "A", "mastery": 0.9, "name": "变量", "last_test_score": 9.0},
    ], weak_topics=[])
    new = _profile(weak_topics=[
        {"node_id": "B", "mastery": 0.3, "name": "条件判断"},
    ])
    evolved, _ = ps.merge_profiles(prev, new)
    assert next(x for x in evolved["known_topics"] if x["node_id"] == "A")["name"] == "变量"
    assert next(x for x in evolved["weak_topics"] if x["node_id"] == "B")["name"] == "条件判断"


def test_merge_adds_last_test_at_and_stale_recheck_due():
    """② 时效: 实测条目记 last_test_at; 超 STALE_AFTER_DAYS 未重测的结转 known 标 recheck_due。"""
    prev = _profile(known_topics=[
        {"node_id": "K1", "mastery": 0.95, "last_test_at": "2020-01-01T00:00:00Z"},  # 六年未测 → stale
        {"node_id": "K2", "mastery": 0.9, "last_test_at": "2026-08-10T00:00:00Z"},   # 最近 → 不标
    ], weak_topics=[])
    new = _profile(weak_topics=[{"node_id": "N", "mastery": 0.3}])
    evolved, _ = ps.merge_profiles(prev, new, now=datetime(2026, 8, 18))
    n = next(x for x in evolved["weak_topics"] if x["node_id"] == "N")
    assert n.get("last_test_at")  # 本轮实测带时间戳
    k1 = next(x for x in evolved["known_topics"] if x["node_id"] == "K1")
    assert k1.get("recheck_due") is True
    k2 = next(x for x in evolved["known_topics"] if x["node_id"] == "K2")
    assert k2.get("recheck_due") is None


def test_save_load_roundtrip_and_sanitize(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    p = _profile()
    sid = ps.save_profile("learner-1", p)
    assert sid == "learner-1"
    assert (Path(tmp_path) / "profile_archive" / "learner-1" / "latest.json").is_file()
    loaded = ps.load_profile("learner-1")
    assert loaded["profile_id"] == p["profile_id"]
    assert ps.load_profile("nope") is None
    try:
        ps.safe_key("../evil")
        assert False, "应拒绝非法 key"
    except ValueError:
        pass


# ---------------- submit API 集成 ----------------

def _diag_app() -> FastAPI:
    app = FastAPI()
    app.state.kg = object()
    app.include_router(diag_api.router, prefix="/api/diagnostics")
    return app


def test_submit_with_learner_key_returns_diff_and_reuses_id(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    import app.api.diagnostics as diag_api

    def fake_grade(questions, answers):
        return {"per_node": {"X": [{"correct": True, "question_index": 0}]},
                "total_count": 1, "correct_count": 1}

    def fake_build_profile(target, nodes, grading, questions=None, learning_style_quiz=None, practical_evidence=None, demographics=None):
        return _profile(profile_id="UP-DIA-run1", theory_level=3, weak_topics=[
            {"node_id": "X", "mastery": 0.4, "error_patterns": []},
        ])

    def fake_graph_node(kg):
        def node(state):
            return {"knowledge_graph": {"learning_path": [{"node_id": "X"}]}, "orchestration_log": []}
        return node

    monkeypatch.setattr(diag_api, "_grade", fake_grade)
    monkeypatch.setattr(diag_api, "_build_profile", fake_build_profile)
    monkeypatch.setattr(diag_api, "graph_controller_node", fake_graph_node)
    monkeypatch.setattr(diag_api, "llm_configured", lambda: True)
    # 预置会话 + 一次历史画像档案
    diag_api._INTERACTIVE_SESSIONS["s1"] = {
        "questions": [{"type": "choice"}], "nodes": [{"node_id": "X"}],
        "target_direction": "Python", "known_topics": [], "created_at": None,
    }
    ps.save_profile("learner-9", _profile(profile_id="UP-DIA-run0", weak_topics=[
        {"node_id": "Y", "mastery": 0.3, "error_patterns": ["旧"]},
    ]))

    c = TestClient(_diag_app())
    r = c.post("/api/diagnostics/submit", json={
        "session_id": "s1", "answers": ["A"], "learner_key": "learner-9",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["learner_key"] == "learner-9"
    assert body["profile_diff"] is not None  # 有历史 → 产生 diff
    # profile_id 复用历史 id (进化档案)
    assert body["profile"]["profile_id"] == "UP-DIA-run0"
    # 档案已落库 latest
    loaded = ps.load_profile("learner-9")
    assert loaded["profile_id"] == "UP-DIA-run0"
    # ④ 复盘联动: submit 落盘的 run summary 含 profile_diff (需 _persist_run 走到)
    rec = run_store.load_run("s1")
    assert rec is not None
    assert rec["run"]["summary"].get("profile_diff") is not None
