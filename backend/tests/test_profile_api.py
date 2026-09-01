"""画像档案管理 API (设置页「学习画像」) 单测。

覆盖: GET 404/读写、PUT 合并更新 (demographics 白名单规范化 + time_per_week/preferred_pace 校验 +
learning_goal 大小限制)、DELETE 重置、_build_profile 画像字段真实化 (缺省/非法回退 6/normal)。
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agents import profile_store as ps
from app.agents.diagnostics import (
    _build_profile,
    _normalize_demographics,
    _normalize_pace,
    _normalize_time_per_week,
)
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
        "preferred_pace": "normal", "time_per_week": 6,
    }
    base.update(kw)
    return base


def _diag_app() -> FastAPI:
    app = FastAPI()
    app.state.kg = object()
    app.include_router(diag_api.router, prefix="/api/diagnostics")
    return app


# ============================================================
# _build_profile 画像字段真实化 (缺省/非法回退, 与旧行为兼容)
# ============================================================

_EMPTY_GRADING = {"per_node": {}, "correct_count": 0, "total_count": 0}


def test_build_profile_defaults_unchanged():
    """不传新字段 → 与旧版一致: preferred_pace=normal, time_per_week=6。"""
    profile = _build_profile("Python 入门", [], _EMPTY_GRADING)
    assert profile["preferred_pace"] == "normal"
    assert profile["time_per_week"] == 6


def test_build_profile_real_values_landed():
    """传入合法 time_per_week/preferred_pace → 落到画像。"""
    profile = _build_profile(
        "Python 入门", [], _EMPTY_GRADING,
        time_per_week=12, preferred_pace="fast",
    )
    assert profile["preferred_pace"] == "fast"
    assert profile["time_per_week"] == 12


def test_build_profile_invalid_falls_back():
    """非法 time_per_week (越界/非数字) 与非法 pace → 回退 6 / normal。"""
    profile = _build_profile(
        "Python 入门", [], _EMPTY_GRADING,
        time_per_week=999, preferred_pace="bogus",
    )
    assert profile["preferred_pace"] == "normal"
    assert profile["time_per_week"] == 6


# ============================================================
# _normalize_demographics 白名单扩展
# ============================================================

def test_normalize_demographics_expanded():
    """放宽后白名单: education/major/age_range/programming/python 字段均收入。"""
    out = _normalize_demographics({
        "education": " 本科 ", "major": "会计学",
        "age_range": "26-35",
        "programming_experience_months": "24",
        "python_experience_months": 12.0,
        "hacked": "x", "age_range_bad": "99",
    })
    assert out == {
        "education": "本科", "major": "会计学", "age_range": "26-35",
        "programming_experience_months": 24, "python_experience_months": 12,
    }


def test_normalize_demographics_drops_invalid():
    """非法 age_range / 负数 / 非数字月份 → 丢弃; 全空 → None。"""
    assert _normalize_demographics({"age_range": "99", "programming_experience_months": -5}) is None
    assert _normalize_demographics({"python_experience_months": "abc"}) is None


def test_normalize_time_per_week_bounds():
    assert _normalize_time_per_week(None) == 6.0
    assert _normalize_time_per_week(12) == 12.0
    assert _normalize_time_per_week(0) == 6.0          # 0 非法
    assert _normalize_time_per_week(169) == 6.0        # 越界 (>168)
    assert _normalize_time_per_week("abc") == 6.0      # 非数字
    assert _normalize_time_per_week(168) == 168.0      # 边界含


def test_normalize_pace():
    assert _normalize_pace("slow") == "slow"
    assert _normalize_pace("normal") == "normal"
    assert _normalize_pace("fast") == "fast"
    assert _normalize_pace("bogus") == "normal"
    assert _normalize_pace(None) == "normal"


# ============================================================
# GET / PUT / DELETE profile 路由
# ============================================================

def test_get_profile_404_when_missing(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    c = TestClient(_diag_app())
    r = c.get("/api/diagnostics/profile/learner-1")
    assert r.status_code == 404
    assert "不存在" in r.json()["detail"]


def test_get_profile_returns_profile_and_history(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    ps.save_profile("learner-1", _profile(theory_level=3))
    c = TestClient(_diag_app())
    r = c.get("/api/diagnostics/profile/learner-1")
    assert r.status_code == 200
    body = r.json()
    assert body["learner_key"] == "learner-1"
    assert body["profile"]["theory_level"] == 3
    assert body["profile"]["preferred_pace"] == "normal"
    assert isinstance(body["history"], list)  # history.jsonl 尾 20 条


def test_put_updates_profile_merged(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    ps.save_profile("learner-1", _profile(theory_level=2))
    c = TestClient(_diag_app())
    r = c.put("/api/diagnostics/profile/learner-1", json={
        "demographics": {"education": "硕士", "major": "软件工程", "age_range": "18-25",
                          "programming_experience_months": 36},
        "time_per_week": 10,
        "preferred_pace": "fast",
        "learning_goal": {"goal": "数据分析入门"},
    })
    assert r.status_code == 200
    p = r.json()
    assert p["time_per_week"] == 10
    assert p["preferred_pace"] == "fast"
    assert p["demographics"]["education"] == "硕士"
    assert p["demographics"]["programming_experience_months"] == 36
    assert p["learning_goal"] == {"goal": "数据分析入门"}
    # 已持久化
    assert ps.load_profile("learner-1")["preferred_pace"] == "fast"


def test_put_invalid_pace_learning_goal_too_big(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    ps.save_profile("learner-1", _profile())
    c = TestClient(_diag_app())
    # 非法 pace → 回退 normal; 非法 time_per_week → 6
    r = c.put("/api/diagnostics/profile/learner-1", json={"preferred_pace": "bogus", "time_per_week": 999})
    assert r.status_code == 200
    p = r.json()
    assert p["preferred_pace"] == "normal"
    assert p["time_per_week"] == 6
    # learning_goal 超 2KB → 400
    big = {"data": "x" * 3000}
    r2 = c.put("/api/diagnostics/profile/learner-1", json={"learning_goal": big})
    assert r2.status_code == 400
    assert "过大" in r2.json()["detail"]


def test_put_404_when_missing(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    c = TestClient(_diag_app())
    r = c.put("/api/diagnostics/profile/learner-1", json={"preferred_pace": "fast"})
    assert r.status_code == 404


def test_delete_profile(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    ps.save_profile("learner-1", _profile())
    c = TestClient(_diag_app())
    r = c.delete("/api/diagnostics/profile/learner-1")
    assert r.status_code == 200
    assert r.json()["deleted"] is True
    # 档案已删 → GET 404
    assert c.get("/api/diagnostics/profile/learner-1").status_code == 404


def test_delete_profile_missing_still_ok(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    c = TestClient(_diag_app())
    r = c.delete("/api/diagnostics/profile/learner-1")
    assert r.status_code == 200
    assert r.json()["deleted"] is False  # 尽力而为, 无档案不报错


def test_profile_rejects_unsafe_key(monkeypatch, tmp_path):
    _patch(monkeypatch, tmp_path)
    c = TestClient(_diag_app())
    r = c.get("/api/diagnostics/profile/../evil")
    assert r.status_code in (400, 404)  # safe_key 拒绝 → 400
