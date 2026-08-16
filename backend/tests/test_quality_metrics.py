"""质量检测指标单测 — 幻觉率 / 适配率 / 覆盖率 / compute_quality_metrics。

纯函数,免 LLM/Neo4j。验证指标定义、达标判定、边界 (无资源/无弱项/维度缺失)。
"""

from app.agents.quality_metrics import (
    ADAPTATION_TARGET,
    COVERAGE_TARGET,
    HALLUCINATION_TARGET,
    compute_adaptation_rate,
    compute_anchor_coverage,
    compute_coverage_rate,
    compute_hallucination_rate,
    compute_quality_metrics,
)


# ---------- 幻觉率 ----------

def test_hallucination_rate_zero_when_dimensions_full_score():
    """reviewer 维度满分 → 幻觉率 0% (达标)。"""
    review = {
        "passed": True,
        "dimensions": {
            "factual_accuracy": {"score": 1.0, "issues": []},
            "hallucination": {"score": 1.0, "issues": []},
        },
    }
    h = compute_hallucination_rate(review)
    assert h["rate"] == 0.0
    assert h["flagged"] is False
    assert h["passed"] is True


def test_hallucination_rate_from_low_dimension_score():
    """幻觉维度 0.6 → rate=0.4 (远超 5% 线,不达标)。"""
    review = {
        "passed": False,
        "dimensions": {
            "factual_accuracy": {"score": 1.0, "issues": []},
            "hallucination": {"score": 0.6, "issues": [{"severity": "high", "problem": "编造"}]},
        },
    }
    h = compute_hallucination_rate(review)
    assert h["rate"] == 0.2  # 1 - avg(1.0, 0.6) = 1 - 0.8
    assert h["score_avg"] == 0.8
    assert h["issues"] == 1
    assert h["flagged"] is True


def test_hallucination_rate_missing_dimensions_defaults_no_hallucination():
    """维度缺失 (reviewer 未跑) → 视无幻觉,rate=0。"""
    h = compute_hallucination_rate({"passed": True})
    assert h["rate"] == 0.0
    assert h["score_avg"] == 1.0


def test_hallucination_rate_empty_review():
    """空 review_results → rate=0。"""
    h = compute_hallucination_rate({})
    assert h["rate"] == 0.0


# ---------- 适配率 ----------

def test_adaptation_rate_all_matched():
    dm = {"summary": {"matched": 9, "total_resources": 9, "too_hard": 0, "too_easy": 0}}
    a = compute_adaptation_rate(dm)
    assert a["rate"] == 1.0
    assert a["matched"] == 9
    assert a["total"] == 9


def test_adaptation_rate_partial():
    """6/9 matched → 0.667 (<85% 不达标)。"""
    dm = {"summary": {"matched": 6, "total_resources": 9}}
    a = compute_adaptation_rate(dm)
    assert a["rate"] == round(6 / 9, 3)


def test_adaptation_rate_no_resources_zero():
    """无资源 → rate=0 (无法适配)。"""
    a = compute_adaptation_rate({"summary": {"matched": 0, "total_resources": 0}})
    assert a["rate"] == 0.0


def test_adaptation_rate_meets_target():
    """9/10=0.9 ≥85% 达标。"""
    dm = {"summary": {"matched": 9, "total_resources": 10}}
    a = compute_adaptation_rate(dm)
    assert a["rate"] >= ADAPTATION_TARGET


# ---------- 覆盖率 ----------

def test_coverage_rate_all_weak_in_path():
    """3 弱项全在路径 → 100%。"""
    profile = {"weak_topics": [
        {"node_id": "PY-012"}, {"node_id": "PY-020"}, {"node_id": "PY-035"}]}
    kg = {"learning_path": [
        {"node_id": "PY-001"}, {"node_id": "PY-012"},
        {"node_id": "PY-020"}, {"node_id": "PY-035"}]}
    c = compute_coverage_rate(profile, kg)
    assert c["rate"] == 1.0
    assert c["covered"] == 3
    assert c["total_weak"] == 3


def test_coverage_rate_partial():
    """3 弱项仅 2 在路径 → 0.667 (<90% 不达标)。"""
    profile = {"weak_topics": [
        {"node_id": "PY-012"}, {"node_id": "PY-020"}, {"node_id": "PY-035"}]}
    kg = {"learning_path": [{"node_id": "PY-012"}, {"node_id": "PY-020"}]}
    c = compute_coverage_rate(profile, kg)
    assert c["rate"] == round(2 / 3, 3)


def test_coverage_rate_no_weak_topics_full():
    """无弱项 → 1.0 (无盲区需覆盖)。"""
    c = compute_coverage_rate({"weak_topics": []}, {"learning_path": []})
    assert c["rate"] == 1.0
    assert c["total_weak"] == 0


def test_coverage_rate_meets_target():
    """9/10 弱项在路径 → 0.9 ≥90% 达标。"""
    weak = [{"node_id": f"PY-0{i}"} for i in range(10)]
    path = [{"node_id": f"PY-0{i}"} for i in range(9)]
    c = compute_coverage_rate({"weak_topics": weak}, {"learning_path": path})
    assert c["rate"] >= COVERAGE_TARGET


# ---------- compute_quality_metrics 组装 ----------

def test_compute_quality_metrics_all_pass():
    """三项全达标 → all_passed=True。"""
    profile = {"weak_topics": [{"node_id": "PY-012"}]}
    kg = {"learning_path": [{"node_id": "PY-012"}]}
    review = {"passed": True, "dimensions": {
        "factual_accuracy": {"score": 1.0, "issues": []},
        "hallucination": {"score": 1.0, "issues": []}}}
    dm = {"summary": {"matched": 9, "total_resources": 9}}
    qm = compute_quality_metrics(profile, kg, {}, review, learning_report={"difficulty_match": dm})
    assert qm["all_passed"] is True
    assert qm["hallucination_rate"]["rate"] < HALLUCINATION_TARGET
    assert qm["adaptation_rate"]["rate"] >= ADAPTATION_TARGET
    assert qm["coverage_rate"]["rate"] >= COVERAGE_TARGET
    assert qm["targets"]["hallucination_lt"] == 0.05


def test_compute_quality_metrics_hallucination_fails_all_passed_false():
    """幻觉率超标 → all_passed=False (即使另两项达标)。"""
    profile = {"weak_topics": [{"node_id": "PY-012"}]}
    kg = {"learning_path": [{"node_id": "PY-012"}]}
    review = {"passed": False, "dimensions": {
        "factual_accuracy": {"score": 0.5, "issues": [{"problem": "x"}]},
        "hallucination": {"score": 0.5, "issues": []}}}
    dm = {"summary": {"matched": 9, "total_resources": 9}}
    qm = compute_quality_metrics(profile, kg, {}, review, learning_report={"difficulty_match": dm})
    assert qm["all_passed"] is False
    assert qm["hallucination_rate"]["rate"] == 0.5


def test_compute_quality_metrics_adaptation_fails():
    """适配率不足 → all_passed=False。"""
    profile = {"weak_topics": []}  # 覆盖率 1.0
    kg = {"learning_path": []}
    review = {"passed": True, "dimensions": {
        "factual_accuracy": {"score": 1.0, "issues": []},
        "hallucination": {"score": 1.0, "issues": []}}}
    dm = {"summary": {"matched": 3, "total_resources": 9}}  # 0.333
    qm = compute_quality_metrics(profile, kg, {}, review, learning_report={"difficulty_match": dm})
    assert qm["all_passed"] is False
    assert qm["adaptation_rate"]["rate"] < ADAPTATION_TARGET


def test_compute_quality_metrics_coverage_fails():
    """覆盖率不足 → all_passed=False。"""
    profile = {"weak_topics": [{"node_id": "PY-012"}, {"node_id": "PY-099"}]}
    kg = {"learning_path": [{"node_id": "PY-012"}]}  # 仅覆盖 1/2
    review = {"passed": True, "dimensions": {
        "factual_accuracy": {"score": 1.0, "issues": []},
        "hallucination": {"score": 1.0, "issues": []}}}
    dm = {"summary": {"matched": 9, "total_resources": 9}}
    qm = compute_quality_metrics(profile, kg, {}, review, learning_report={"difficulty_match": dm})
    assert qm["all_passed"] is False
    assert qm["coverage_rate"]["rate"] < COVERAGE_TARGET


def test_compute_quality_metrics_fallback_difficulty_match():
    """未传 learning_report → 兜底现算 difficulty_match (不崩)。"""
    profile = {"weak_topics": []}
    kg = {"learning_path": [{"node_id": "PY-001", "name": "n", "difficulty": 2}]}
    review = {"passed": True, "dimensions": {}}
    generated = {"resources": [{"target_node_id": "PY-001", "difficulty_level": 2, "content_type": "lecture"}]}
    qm = compute_quality_metrics(profile, kg, generated, review)
    # 兜底算出 1 资源 matched → 适配率 1.0
    assert qm["adaptation_rate"]["total"] == 1
    assert qm["adaptation_rate"]["rate"] == 1.0


def test_compute_quality_metrics_has_generated_at():
    qm = compute_quality_metrics({}, {}, {}, {})
    assert "generated_at" in qm
    assert qm["generated_at"].endswith("Z")


# ---------- 锚定覆盖度 (阶段四: 资源内容对节点 key_points 的覆盖) ----------

def test_anchor_coverage_counts_by_level():
    verdicts = [
        {"coverage": "full"},
        {"coverage": "full"},
        {"coverage": "partial"},
        {"coverage": "none"},
    ]
    result = compute_anchor_coverage(verdicts)
    assert result == {"full": 2, "partial": 1, "none": 1, "rate_full": 0.5}


def test_anchor_coverage_invalid_and_missing_default_none():
    result = compute_anchor_coverage([
        {"coverage": "非法值"},
        {},                      # 缺失 → none
        "不是dict",              # 非 dict → 忽略
        None,                    # 非 dict → 忽略
    ])
    assert result == {"full": 0, "partial": 0, "none": 2, "rate_full": 0.0}


def test_anchor_coverage_empty_input():
    assert compute_anchor_coverage([]) == {"full": 0, "partial": 0, "none": 0, "rate_full": 0.0}
    assert compute_anchor_coverage(None) == {"full": 0, "partial": 0, "none": 0, "rate_full": 0.0}


def test_anchor_coverage_all_full():
    result = compute_anchor_coverage([{"coverage": "full"}] * 9)
    assert result["rate_full"] == 1.0
    assert result["full"] == 9
