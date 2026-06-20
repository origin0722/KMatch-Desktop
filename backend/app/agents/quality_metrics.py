"""质量检测指标计算 (赛题 M5: 幻觉率 / 适配率 / 覆盖率)

纯函数,不调 LLM。从一次运行产出 (profile / knowledge_graph / generated_content /
review_results) 派生三项质量指标,供:

  - learning_report.quality_metrics (per-session,demo/interactive 实时展示给评委)
  - scripts/run_quality_test.py (批量跑 N 画像,聚合写 M5 质量检测报告)

指标定义 (与赛题 9.2 评分标准 / M5 检查点对齐):

  幻觉率 hallucination_rate
      = 1 - avg(dimensions.hallucination.score, dimensions.factual_accuracy.score)
      reviewer 抗幻觉维度分数的补数。reviewer 通过 (维度满分) → 0%。
      达标线 <5%。维度缺失 (reviewer 未跑/LLM 未配置) → 视 1.0 (无幻觉检出) → 0%。
      另计 hallucination_issues (幻觉+事实维度 issue 条数) 与 打回标志 (passed=False)
      供批量聚合区分"检出幻觉"与"维度分扣分"。

  适配率 adaptation_rate
      = difficulty_match.summary.matched / total_resources
      生成资源难度与知识点难度匹配 (|gap|<=1) 的占比。达标线 ≥85%。
      无资源 → 0.0 (无法适配,记为不达标)。

  覆盖率 coverage_rate
      = |弱项节点 ∩ 学习路径节点| / |弱项节点|
      学习路径对已识别盲区 (weak_topics) 的覆盖。达标线 ≥90%。
      无弱项 → 1.0 (无盲区需覆盖,视作完全覆盖)。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

# 赛题 M5 达标线 (与 项目开发计划书 9.2 / 10.2 一致)
HALLUCINATION_TARGET = 0.05   # 幻觉率 <5%
ADAPTATION_TARGET = 0.85      # 适配率 ≥85%
COVERAGE_TARGET = 0.90        # 覆盖率 ≥90%

# reviewer 抗幻觉相关维度 (reviewer.py _llm_review 输出)
_HALLUCINATION_DIMS = ("factual_accuracy", "hallucination")


def _dim_score(dimensions: dict, key: str) -> float:
    """取某维度分数,缺失/非法 → 1.0 (无问题)。"""
    d = (dimensions or {}).get(key)
    if not isinstance(d, dict):
        return 1.0
    score = d.get("score", 1.0)
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        return 1.0
    return float(score)


def _dim_issues(dimensions: dict, key: str) -> list:
    """取某维度 issues 列表,缺失 → []。"""
    d = (dimensions or {}).get(key)
    if not isinstance(d, dict):
        return []
    issues = d.get("issues", [])
    return issues if isinstance(issues, list) else []


def compute_hallucination_rate(review_results: dict) -> dict:
    """幻觉率 — reviewer 抗幻觉维度补数 + issue/打回计数。

    Returns:
        {rate, score_avg, issues, passed, flagged}
        rate: 0-1 幻觉率 (1 - 维度均分)
        score_avg: 抗幻觉维度均分 (0-1)
        issues: 幻觉+事实维度 issue 总数
        passed: reviewer 是否通过 (passed=False 视为本次检出问题)
        flagged: 是否检出幻觉 (issues>0 或维度分<1)
    """
    review_results = review_results or {}
    dimensions = review_results.get("dimensions", {}) if isinstance(review_results, dict) else {}
    scores = [_dim_score(dimensions, k) for k in _HALLUCINATION_DIMS]
    score_avg = round(sum(scores) / len(scores), 3) if scores else 1.0
    rate = round(1.0 - score_avg, 3)

    issues = sum(len(_dim_issues(dimensions, k)) for k in _HALLUCINATION_DIMS)
    passed = bool(review_results.get("passed", False))
    flagged = issues > 0 or score_avg < 1.0

    return {
        "rate": rate,
        "score_avg": score_avg,
        "issues": issues,
        "passed": passed,
        "flagged": flagged,
    }


def compute_adaptation_rate(difficulty_match: dict) -> dict:
    """适配率 — 难度匹配资源占比。

    Args:
        difficulty_match: learning_report.difficulty_match 子对象
            (含 summary.{matched, total_resources})

    Returns:
        {rate, matched, total}
    """
    dm = difficulty_match or {}
    summary = dm.get("summary", {}) if isinstance(dm, dict) else {}
    matched = summary.get("matched", 0) if isinstance(summary, dict) else 0
    total = summary.get("total_resources", 0) if isinstance(summary, dict) else 0
    if not isinstance(matched, (int, float)):
        matched = 0
    if not isinstance(total, (int, float)) or total <= 0:
        return {"rate": 0.0, "matched": 0, "total": 0}
    rate = round(matched / total, 3)
    return {"rate": rate, "matched": int(matched), "total": int(total)}


def compute_coverage_rate(profile: dict, knowledge_graph: dict) -> dict:
    """覆盖率 — 学习路径对弱项盲区的覆盖。

    弱项节点 (profile.weak_topics) 全部纳入学习路径 → 100%。
    无弱项 → 1.0 (无盲区需覆盖)。

    Returns:
        {rate, covered, total_weak}
    """
    profile = profile or {}
    knowledge_graph = knowledge_graph or {}
    weak_ids = set()
    for t in profile.get("weak_topics", []) if isinstance(profile, dict) else []:
        if isinstance(t, dict) and t.get("node_id"):
            weak_ids.add(t["node_id"])

    if not weak_ids:
        return {"rate": 1.0, "covered": 0, "total_weak": 0}

    path_ids = set()
    for n in knowledge_graph.get("learning_path", []) if isinstance(knowledge_graph, dict) else []:
        if isinstance(n, dict) and n.get("node_id"):
            path_ids.add(n["node_id"])

    covered = len(weak_ids & path_ids)
    rate = round(covered / len(weak_ids), 3)
    return {"rate": rate, "covered": covered, "total_weak": len(weak_ids)}


def compute_quality_metrics(
    profile: dict,
    knowledge_graph: dict,
    generated_content: dict,
    review_results: dict,
    learning_report: Optional[dict] = None,
) -> dict:
    """组装三项质量指标 + 达标判定。

    Args:
        profile: 用户画像 (含 weak_topics)
        knowledge_graph: {learning_path, ...}
        generated_content: {resources, ...} (本指标未直接用,保留入参对称)
        review_results: reviewer 输出 {passed, dimensions, ...}
        learning_report: 已组装的可视化报告 (取 difficulty_match 子对象);
            缺省则从 generated_content/learning_path 现算 (避免循环依赖)。

    Returns:
        {hallucination_rate, adaptation_rate, coverage_rate, targets, all_passed, generated_at}
        各 *_rate 为 {rate, ...详情}。targets 为达标线。all_passed 三项全达标。
    """
    # 适配率: 优先复用 learning_report.difficulty_match,避免与 report_builder 重复计算
    if learning_report and isinstance(learning_report.get("difficulty_match"), dict):
        dm = learning_report["difficulty_match"]
    else:
        # 兜底: 现算 (与 report_builder._build_difficulty_match 同语义,轻量版)
        from app.agents.report_builder import _build_difficulty_match
        learning_path = (knowledge_graph or {}).get("learning_path", [])
        dm = _build_difficulty_match(generated_content or {}, learning_path, profile or {})

    hallucination = compute_hallucination_rate(review_results)
    adaptation = compute_adaptation_rate(dm)
    coverage = compute_coverage_rate(profile, knowledge_graph)

    all_passed = (
        hallucination["rate"] < HALLUCINATION_TARGET
        and adaptation["rate"] >= ADAPTATION_TARGET
        and coverage["rate"] >= COVERAGE_TARGET
    )

    return {
        "hallucination_rate": hallucination,
        "adaptation_rate": adaptation,
        "coverage_rate": coverage,
        "targets": {
            "hallucination_lt": HALLUCINATION_TARGET,
            "adaptation_gte": ADAPTATION_TARGET,
            "coverage_gte": COVERAGE_TARGET,
        },
        "all_passed": all_passed,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
