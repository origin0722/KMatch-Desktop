"""report pacing 单测 — 估时"节奏语境" (连续学时 → 按每周可学时折周)。"""

from app.agents.report_builder import build_learning_report


def _kg(hours: float) -> dict:
    return {
        "learning_path": [{"node_id": "A"}, {"node_id": "B"}],
        "path_node_ids": ["A", "B"],
        "estimated_total_hours": hours,
        "node_status_updates": {},
    }


def test_pacing_default_week_and_ceil():
    r = build_learning_report({"time_per_week": 6}, _kg(5.2), {}, {})
    p = r["pacing"]
    assert p["total_hours"] == 5.2
    assert p["hours_per_week"] == 6
    assert p["weeks"] == 1  # ceil(5.2/6) = 1 → "约 1 周"


def test_pacing_low_weekly_hours_prolongs():
    r = build_learning_report({"time_per_week": 2}, _kg(5.2), {}, {})
    assert r["pacing"]["weeks"] == 3  # ceil(5.2/2)=3


def test_pacing_zero_hours_no_weeks():
    r = build_learning_report({"time_per_week": 6}, _kg(0), {}, {})
    assert r["pacing"]["weeks"] == 0


def test_pacing_default_profile_no_week_field():
    r = build_learning_report({}, _kg(12.0), {}, {})
    assert r["pacing"]["hours_per_week"] == 6  # 默认每周 6h
    assert r["pacing"]["weeks"] == 2
