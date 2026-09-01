"""reviewer 纯函数单测 — 覆盖 _weighted_score + _hard_check_overlap + _merge_issues。"""

import pytest
from app.agents.reviewer import _weighted_score, _hard_check_overlap, _merge_issues


# ============================================================
# _weighted_score
# ============================================================

def test_weighted_score_perfect():
    """四维度满分 → 总分 1.0。"""
    dims = {
        "factual_accuracy": {"score": 1.0},
        "hallucination": {"score": 1.0},
        "logic_consistency": {"score": 1.0},
        "teaching_appropriateness": {"score": 1.0},
    }
    assert _weighted_score(dims) == 1.0


def test_weighted_score_zero():
    """四维度零分 → 总分 0.0。"""
    dims = {
        "factual_accuracy": {"score": 0.0},
        "hallucination": {"score": 0.0},
        "logic_consistency": {"score": 0.0},
        "teaching_appropriateness": {"score": 0.0},
    }
    assert _weighted_score(dims) == 0.0


def test_weighted_score_mixed():
    """混合分值 — 验证加权公式: 0.4×1.0 + 0.3×0.5 + 0.2×0.0 + 0.1×0.8 = 0.63。"""
    dims = {
        "factual_accuracy": {"score": 1.0},
        "hallucination": {"score": 0.5},
        "logic_consistency": {"score": 0.0},
        "teaching_appropriateness": {"score": 0.8},
    }
    # 0.4*1.0 + 0.3*0.5 + 0.2*0.0 + 0.1*0.8 = 0.4 + 0.15 + 0 + 0.08 = 0.63
    assert _weighted_score(dims) == 0.63


def test_weighted_score_missing_dimension():
    """缺失维度视为 0.0 分。"""
    dims = {
        "factual_accuracy": {"score": 1.0},
        "hallucination": {"score": 1.0},
    }
    # logic_consistency 和 teaching_appropriateness 缺失 → 默认 0.0
    # 0.4*1.0 + 0.3*1.0 + 0.2*0.0 + 0.1*0.0 = 0.7
    assert _weighted_score(dims) == 0.7


def test_weighted_score_rounds_to_3_decimal():
    """结果四舍五入到 3 位小数。"""
    dims = {
        "factual_accuracy": {"score": 0.333},
        "hallucination": {"score": 0.333},
        "logic_consistency": {"score": 0.333},
        "teaching_appropriateness": {"score": 0.333},
    }
    result = _weighted_score(dims)
    # 0.4*0.333 + 0.3*0.333 + 0.2*0.333 + 0.1*0.333 = 0.333
    assert result == 0.333


# ============================================================
# _hard_check_overlap
# ============================================================

def test_overlap_detected():
    """known 和 weak 有交叉 → 返回问题列表。"""
    profile = {
        "known_topics": [
            {"node_id": "PY-001"},
            {"node_id": "PY-002"},
        ],
        "weak_topics": [
            {"node_id": "PY-002"},
            {"node_id": "PY-003"},
        ],
    }
    issues = _hard_check_overlap(profile)
    assert len(issues) == 1
    assert issues[0]["source_node"] == "PY-002"
    assert issues[0]["severity"] == "high"
    assert issues[0]["dimension"] == "hallucination"


def test_overlap_multiple():
    """多个交叉节点。"""
    profile = {
        "known_topics": [{"node_id": "PY-001"}, {"node_id": "PY-002"}],
        "weak_topics": [{"node_id": "PY-001"}, {"node_id": "PY-002"}],
    }
    issues = _hard_check_overlap(profile)
    assert len(issues) == 2


def test_overlap_none():
    """无交叉 → 空列表。"""
    profile = {
        "known_topics": [{"node_id": "PY-001"}],
        "weak_topics": [{"node_id": "PY-002"}],
    }
    assert _hard_check_overlap(profile) == []


def test_overlap_empty_profile():
    """空画像 → 无交叉。"""
    assert _hard_check_overlap({}) == []


def test_overlap_missing_sections():
    """缺少 known_topics 或 weak_topics → 无交叉。"""
    assert _hard_check_overlap({"known_topics": [{"node_id": "PY-001"}]}) == []


def test_overlap_handles_non_dict_items():
    """节点元素为非 dict（防御）→ 安全跳过。"""
    profile = {
        "known_topics": ["PY-001"],  # 字符串而非 dict
        "weak_topics": ["PY-001"],
    }
    issues = _hard_check_overlap(profile)
    assert issues == []


# ============================================================
# _merge_issues
# ============================================================

def test_merge_issues_adds_to_correct_dimension():
    """硬规则问题合并到对应维度。"""
    dims = {
        "factual_accuracy": {"score": 1.0, "issues": []},
        "hallucination": {"score": 1.0, "issues": []},
    }
    hard_issues = [
        {"dimension": "factual_accuracy", "problem": "节点不存在"},
    ]
    result = _merge_issues(dims, hard_issues)
    assert len(result["factual_accuracy"]["issues"]) == 1


def test_merge_issues_caps_score_at_0_6():
    """有硬规则问题的维度，分数上限降至 0.6。"""
    dims = {
        "factual_accuracy": {"score": 1.0, "issues": []},
    }
    hard_issues = [
        {"dimension": "factual_accuracy", "problem": "节点不存在"},
    ]
    result = _merge_issues(dims, hard_issues)
    assert result["factual_accuracy"]["score"] == 0.6


def test_merge_issues_score_below_cap_unchanged():
    """分数已在 0.6 以下时不改变。"""
    dims = {
        "factual_accuracy": {"score": 0.3, "issues": []},
    }
    hard_issues = [
        {"dimension": "factual_accuracy", "problem": "节点不存在"},
    ]
    result = _merge_issues(dims, hard_issues)
    assert result["factual_accuracy"]["score"] == 0.3


def test_merge_issues_empty_hard_issues():
    """无硬规则问题 → dims 不变。"""
    dims = {
        "factual_accuracy": {"score": 0.95, "issues": []},
    }
    result = _merge_issues(dims, [])
    assert result == dims


def test_merge_issues_creates_dimension_if_missing():
    """硬规则问题引用了 dims 中不存在的维度 → 自动创建。"""
    dims = {}
    hard_issues = [
        {"dimension": "hallucination", "problem": "交叉重复"},
    ]
    result = _merge_issues(dims, hard_issues)
    assert "hallucination" in result
    assert len(result["hallucination"]["issues"]) == 1
    assert result["hallucination"]["score"] == 0.6  # 默认 1.0 → cap 到 0.6


# ============================================================
# _normalize_dims (F2: LLM 非常规 JSON 结构归一化)
# ============================================================

from app.agents.reviewer import _normalize_dims, _default_dims


def test_normalize_non_dict_returns_default():
    """非 dict (list/None/str) → 四维度默认满分。"""
    for bad in ([], None, "字符串"):
        result = _normalize_dims(bad)
        assert set(result.keys()) == {"factual_accuracy", "hallucination",
                                      "logic_consistency", "teaching_appropriateness"}
        assert all(d["score"] == 1.0 for d in result.values())


def test_normalize_flat_score_number():
    """扁平结构 {dim: 0.8} (score 直接是数字) → 包成 {score: 0.8}。"""
    dims = {"factual_accuracy": 0.8, "hallucination": 0.9}
    result = _normalize_dims(dims)
    assert result["factual_accuracy"]["score"] == 0.8
    assert result["factual_accuracy"]["issues"] == []
    # 缺失维度补满分
    assert result["logic_consistency"]["score"] == 1.0


def test_normalize_missing_issues_key():
    """缺 issues 键 {dim: {score: 0.9}} → 补 issues=[]。"""
    dims = {"factual_accuracy": {"score": 0.9}}
    result = _normalize_dims(dims)
    assert result["factual_accuracy"]["issues"] == []


def test_normalize_non_number_score():
    """score 非数字 (字符串/None) → 默认 1.0。"""
    dims = {"factual_accuracy": {"score": "高", "issues": []}}
    result = _normalize_dims(dims)
    assert result["factual_accuracy"]["score"] == 1.0


def test_normalize_non_list_issues():
    """issues 非列表 → 补空列表。"""
    dims = {"factual_accuracy": {"score": 0.9, "issues": "不是列表"}}
    result = _normalize_dims(dims)
    assert result["factual_accuracy"]["issues"] == []


def test_normalize_well_formed_passthrough():
    """结构良好的 dims → 原样保留 (score 转 float)。"""
    dims = {
        "factual_accuracy": {"score": 0.9, "issues": [{"problem": "x"}]},
        "teaching_appropriateness": {"score": 0.8, "issues": []},
    }
    result = _normalize_dims(dims)
    assert result["factual_accuracy"]["score"] == 0.9
    assert len(result["factual_accuracy"]["issues"]) == 1
    assert result["teaching_appropriateness"]["score"] == 0.8


# ============================================================
# 内容模式硬规则 (第4周: _hard_check_content_sources)
# ============================================================

from app.agents.reviewer import (
    _extract_source_node_id,
    _hard_check_content_sources,
)


class _KGExistence:
    """假 KG: 只有 PY-001 存在。"""
    def get_node(self, nid):
        return {"node_id": nid} if nid == "PY-001" else None


def test_extract_source_node_id_valid():
    assert _extract_source_node_id("PY-012.key_points[0]") == "PY-012"
    assert _extract_source_node_id("PY-001.summary") == "PY-001"
    assert _extract_source_node_id("PY-001") == "PY-001"


def test_extract_source_node_id_invalid():
    assert _extract_source_node_id("PY001") is None
    assert _extract_source_node_id("not-a-node") is None
    assert _extract_source_node_id("") is None
    assert _extract_source_node_id(None) is None


def test_content_sources_no_traceability_flagged():
    """资源无 source_nodes → 幻觉风险 (hallucination 维度)。"""
    resources = [{"target_node_id": "PY-001", "source_nodes": []}]
    issues = _hard_check_content_sources(_KGExistence(), resources)
    assert len(issues) == 1
    assert issues[0]["dimension"] == "hallucination"


def test_content_sources_nonexistent_node_flagged():
    """溯源引用不存在的节点 → 事实准确性问题。"""
    resources = [{
        "target_node_id": "PY-999",
        "source_nodes": ["PY-999.key_points[0]"],  # PY-999 不存在
    }]
    issues = _hard_check_content_sources(_KGExistence(), resources)
    assert any(i["dimension"] == "factual_accuracy" and "不存在" in i["problem"] for i in issues)


def test_content_sources_malformed_ref_flagged():
    """溯源引用格式非法 → 中等问题。"""
    resources = [{
        "target_node_id": "PY-001",
        "source_nodes": ["PY-001.key_points[0]", "格式错误"],
    }]
    issues = _hard_check_content_sources(_KGExistence(), resources)
    assert any("格式非法" in i["problem"] for i in issues)


def test_content_sources_all_valid_no_issues():
    """全部溯源合法且节点存在 → 无问题。"""
    resources = [{
        "target_node_id": "PY-001",
        "source_nodes": ["PY-001.key_points[0]", "PY-001.summary"],
    }]
    issues = _hard_check_content_sources(_KGExistence(), resources)
    assert issues == []


def test_content_sources_non_dict_resource_flagged():
    """资源元素非对象 → factual_accuracy 问题。"""
    resources = ["not a dict"]
    issues = _hard_check_content_sources(_KGExistence(), resources)
    assert len(issues) == 1
    assert "非对象" in issues[0]["problem"]


# ============================================================
# reviewer_node 降级契约 (空画像 dimensions 不缺失)
# ============================================================

from app.agents.reviewer import reviewer_node


class _KGForNode:
    def get_node(self, nid):
        return {"node_id": nid} if nid == "PY-001" else None


def test_reviewer_node_empty_profile_returns_four_dims(monkeypatch):
    """空画像 (LLM 未配置) → 判不通过，但 dimensions 仍含四维度 (对接契约: 不缺失 key)。"""
    monkeypatch.setattr("app.agents.reviewer.llm_configured", lambda: False)
    node = reviewer_node(_KGForNode())
    result = node({"user_profile": {}, "assessment": {}, "retry_count": 0})

    review = result["review_results"]
    assert review["passed"] is False
    assert review["verdict"] == "reject"
    # 关键契约: dimensions 含四维度，B 端可安全访问 .*.score
    assert set(review["dimensions"].keys()) == {
        "factual_accuracy", "hallucination", "logic_consistency", "teaching_appropriateness"
    }
    assert all("score" in d for d in review["dimensions"].values())
    # retry_hint 说明原因
    assert "LLM 未配置" in review["retry_hint"]


def test_reviewer_node_empty_profile_with_llm_configured(monkeypatch):
    """LLM 已配置但画像为空 (diagnostics 异常) → retry_hint 提示画像问题。"""
    monkeypatch.setattr("app.agents.reviewer.llm_configured", lambda: True)
    node = reviewer_node(_KGForNode())
    result = node({"user_profile": {}, "assessment": {}, "retry_count": 0})

    review = result["review_results"]
    assert review["passed"] is False
    assert set(review["dimensions"].keys()) == {
        "factual_accuracy", "hallucination", "logic_consistency", "teaching_appropriateness"
    }
    assert "学情检测未产出有效画像" in review["retry_hint"]


def test_reviewer_node_content_mode_calls_llm_with_profile(monkeypatch):
    """BUG-037 回归: 内容模式 LLM 审核必须传 (resources, profile)，否则 TypeError 降级。

    content_phase_entered=True + resources 非空 → 内容模式 → _llm_review_content(resources, profile)。
    旧实现 llm_arg=resources 漏传 profile 致 TypeError，降级为仅硬规则 (内容未被真正 LLM 校验)。
    """
    monkeypatch.setattr("app.agents.reviewer.llm_configured", lambda: True)

    captured = {}

    def _fake_llm_review_content(resources, profile):
        captured["resources"] = resources
        captured["profile"] = profile
        return {
            "factual_accuracy": {"score": 0.95, "issues": []},
            "hallucination": {"score": 0.95, "issues": []},
            "logic_consistency": {"score": 0.95, "issues": []},
            "teaching_appropriateness": {"score": 0.95, "issues": []},
        }

    monkeypatch.setattr("app.agents.reviewer._llm_review_content", _fake_llm_review_content)

    resources = [{
        "target_node_id": "PY-001",
        "source_nodes": ["PY-001.summary"],
        "content": "讲义内容",
    }]
    profile = {"theory_level": 2, "target_direction": "Python"}
    state = {
        "user_profile": profile,
        "assessment": {},
        "retry_count": 0,
        "content_phase_entered": True,
        "generated_content": {"resources": resources},
    }
    node = reviewer_node(_KGForNode())
    result = node(state)

    # LLM 被调用且收到 resources + profile (BUG-037: 不再 TypeError 降级)
    assert captured.get("resources") == resources
    assert captured.get("profile") == profile
    review = result["review_results"]
    # LLM 高分 → 通过 (非降级仅硬规则)
    assert review["passed"] is True
    assert review["overall_score"] >= 0.85



# ============================================================
# B12 回归: _merge_issues 仅封顶硬规则命中维度, 不双重惩罚 LLM 维度
# ============================================================

from app.agents.reviewer import _merge_issues


def test_merge_issues_only_caps_hard_hit_dims():
    """LLM 在 logic_consistency 返回 score=0.9 + 1 issue (已降分),
    硬规则命中 factual_accuracy → 只封顶 factual, logic 保留 0.9 (不双重惩罚)。"""
    dims = {
        "factual_accuracy": {"score": 1.0, "issues": []},
        "hallucination": {"score": 1.0, "issues": []},
        "logic_consistency": {"score": 0.9, "issues": [{"problem": "轻微逻辑问题"}]},  # LLM 带 issue
        "teaching_appropriateness": {"score": 1.0, "issues": []},
    }
    hard_issues = [{"dimension": "factual_accuracy", "problem": "溯源缺失"}]
    result = _merge_issues(dims, hard_issues)
    assert result["factual_accuracy"]["score"] == 0.6  # 硬规则命中 → 封顶
    assert result["logic_consistency"]["score"] == 0.9  # LLM 维度保留, 不二次封顶 (B12)


def test_merge_issues_no_hard_keeps_llm_scores():
    """无硬规则 → 所有维度保留 LLM 原分。"""
    dims = {
        "factual_accuracy": {"score": 0.85, "issues": [{"problem": "x"}]},
        "hallucination": {"score": 1.0, "issues": []},
        "logic_consistency": {"score": 1.0, "issues": []},
        "teaching_appropriateness": {"score": 1.0, "issues": []},
    }
    result = _merge_issues(dims, [])
    assert result["factual_accuracy"]["score"] == 0.85  # 无硬规则, 保留 LLM 0.85


# ---- 赛题(4)① 申诉-复审: 裁定归一化与落盘 (生成↔审核辩论) ----

def test_sanitize_rebuttal_verdicts_keeps_valid_and_downgrades_illegal():
    from app.agents.reviewer import _sanitize_rebuttal_verdicts
    out = _sanitize_rebuttal_verdicts([
        {"issue": "find() 返回值有据", "verdict": "accepted", "reason": "引用 key_points[0] 成立"},
        {"issue": "b", "verdict": "bogus", "reason": "x"},
        "bad",
    ])
    assert len(out) == 2
    assert out[0] == {"issue": "find() 返回值有据", "verdict": "accepted", "reason": "引用 key_points[0] 成立"}
    assert out[1]["verdict"] == "rejected"  # 非法裁定置 rejected


def test_sanitize_rebuttal_verdicts_non_list():
    from app.agents.reviewer import _sanitize_rebuttal_verdicts
    assert _sanitize_rebuttal_verdicts(None) == []
    assert _sanitize_rebuttal_verdicts("x") == []


def test_reviewer_node_lands_rebuttal_verdicts(monkeypatch):
    """LLM 审核输出带 rebuttal_verdicts → 归一化后落 review_results (答辩可展示的辩论轨迹)。"""
    captured = {}

    def _fake_llm_review_content(resources, profile):
        captured["resources"] = resources
        return {
            "factual_accuracy": {"score": 0.9, "issues": []},
            "hallucination": {"score": 0.9, "issues": []},
            "logic_consistency": {"score": 0.9, "issues": []},
            "teaching_appropriateness": {"score": 0.9, "issues": []},
            "rebuttal_verdicts": [
                {"issue": "find() 返回值描述", "verdict": "accepted", "reason": "节点事实支撑"},
                {"issue": "性能数据", "verdict": "rejected", "reason": "图谱外编造"},
            ],
        }

    monkeypatch.setattr("app.agents.reviewer.llm_configured", lambda: True)
    monkeypatch.setattr("app.agents.reviewer._llm_review_content", _fake_llm_review_content)

    resources = [{"target_node_id": "PY-001", "source_nodes": ["PY-001.summary"], "content": "讲义"}]
    state = {
        "user_profile": {"theory_level": 2, "target_direction": "Python"},
        "assessment": {},
        "retry_count": 0,
        "content_phase_entered": True,
        "generated_content": {"resources": resources},
    }
    result = reviewer_node(_KGForNode())(state)
    review = result["review_results"]
    assert review["rebuttal_verdicts"] == [
        {"issue": "find() 返回值描述", "verdict": "accepted", "reason": "节点事实支撑"},
        {"issue": "性能数据", "verdict": "rejected", "reason": "图谱外编造"},
    ]


def test_reviewer_node_without_rebuttal_defaults_empty(monkeypatch):
    """LLM 未返回 rebuttal_verdicts (如画像模式/旧输出) → 空数组, 契约字段恒在。"""
    monkeypatch.setattr("app.agents.reviewer.llm_configured", lambda: True)
    monkeypatch.setattr(
        "app.agents.reviewer._llm_review_content",
        lambda resources, profile: {
            "factual_accuracy": {"score": 0.9, "issues": []},
            "hallucination": {"score": 0.9, "issues": []},
            "logic_consistency": {"score": 0.9, "issues": []},
            "teaching_appropriateness": {"score": 0.9, "issues": []},
        },
    )
    resources = [{"target_node_id": "PY-001", "source_nodes": ["PY-001.summary"], "content": "讲义"}]
    state = {
        "user_profile": {"theory_level": 2, "target_direction": "Python"},
        "assessment": {},
        "retry_count": 0,
        "content_phase_entered": True,
        "generated_content": {"resources": resources},
    }
    review = reviewer_node(_KGForNode())(state)["review_results"]
    assert review["rebuttal_verdicts"] == []
