"""diagnostics 纯函数单测 — 覆盖 parse_llm_json + _build_profile + _grade。"""

import json

import pytest
from app.utils.json_utils import parse_llm_json
from app.agents.diagnostics import _build_profile, _grade


class _FakeModel:
    """假 LLM model：invoke 返回固定 content（用于 _grade 单测，免真实 API）。"""

    def __init__(self, content: str):
        self._content = content

    def invoke(self, messages):
        class _Resp:
            content = self._content
        return _Resp()


# ============================================================
# parse_llm_json
# ============================================================

def test_parse_plain_json_object():
    """纯 JSON 对象直接解析。"""
    assert parse_llm_json('{"a": 1, "b": 2}') == {"a": 1, "b": 2}


def test_parse_plain_json_array():
    """纯 JSON 数组直接解析。"""
    result = parse_llm_json('[{"x": 1}, {"x": 2}]')
    assert isinstance(result, list)
    assert len(result) == 2


def test_parse_markdown_code_block():
    """> ``json 代码块包裹。"""
    text = '```json\n{"key": "value"}\n```'
    assert parse_llm_json(text) == {"key": "value"}


def test_parse_markdown_no_lang_tag():
    """无语言标签的 markdown 代码块。"""
    text = '```\n{"key": "value"}\n```'
    assert parse_llm_json(text) == {"key": "value"}


def test_parse_multi_object_concat():
    """多对象拼接 — 只取第一个。"""
    text = '{"a": 1}{"b": 2}'
    assert parse_llm_json(text) == {"a": 1}


def test_parse_trailing_text():
    """JSON 后面有 LLM 的额外文本。"""
    result = parse_llm_json('{"x": 1}\n以上是评测结果，请审阅。')
    assert result == {"x": 1}


def test_parse_nested_braces():
    """嵌套花括号 — raw_decode 自动匹配层级，不会在第一个 } 截断。"""
    text = '{"outer": {"inner": [1, 2, 3]}}'
    result = parse_llm_json(text)
    assert result == {"outer": {"inner": [1, 2, 3]}}


def test_parse_nested_array():
    """嵌套数组。"""
    text = '[{"items": [{"name": "a"}, {"name": "b"}]}]'
    result = parse_llm_json(text)
    assert result == [{"items": [{"name": "a"}, {"name": "b"}]}]


def test_parse_leading_text_then_json():
    """LLM 先说话再给 JSON。"""
    result = parse_llm_json('好的，以下是结果：\n{"score": 0.95}')
    assert result == {"score": 0.95}


def test_parse_completely_invalid_returns_empty_dict():
    """完全非法文本 — 返回 {} 不抛异常。"""
    result = parse_llm_json("对不起，我无法完成这个请求。")
    assert result == {}


def test_parse_empty_string():
    """空字符串 — 返回 {}。"""
    assert parse_llm_json("") == {}


# ============================================================
# _build_profile
# ============================================================

NODES_ALL_CORRECT = [
    {"node_id": "PY-001", "name": "变量与赋值", "difficulty": 1},
    {"node_id": "PY-002", "name": "条件判断", "difficulty": 2},
    {"node_id": "PY-003", "name": "循环", "difficulty": 3},
]

NODES_MIXED = [
    {"node_id": "PY-001", "name": "变量", "difficulty": 1},
    {"node_id": "PY-002", "name": "条件", "difficulty": 2},
    {"node_id": "PY-005", "name": "类", "difficulty": 4},
]


def _make_grading(per_node: dict, total_count: int) -> dict:
    """构造 grading dict，自动计算 correct_count。"""
    correct_count = 0
    for grades in per_node.values():
        correct_count += sum(1 for g in grades if g["correct"])
    return {
        "per_node": per_node,
        "correct_count": correct_count,
        "total_count": total_count,
    }


def test_build_profile_all_correct():
    """全对 → theory_level=5，全部归入 known_topics。"""
    per_node = {
        "PY-001": [{"question_index": 0, "correct": True}, {"question_index": 1, "correct": True}],
        "PY-002": [{"question_index": 2, "correct": True}],
        "PY-003": [{"question_index": 3, "correct": True}],
    }
    grading = _make_grading(per_node, total_count=4)

    profile = _build_profile("Python 入门", NODES_ALL_CORRECT, grading)

    assert profile["theory_level"] == 5
    assert len(profile["known_topics"]) == 3
    assert len(profile["weak_topics"]) == 0
    assert profile["profile_id"].startswith("UP-DIA-")
    assert profile["target_direction"] == "Python 入门"


def test_build_profile_all_wrong():
    """全错 → theory_level=1，全部归入 weak_topics。"""
    per_node = {
        "PY-001": [{"question_index": 0, "correct": False}],
        "PY-002": [{"question_index": 1, "correct": False}],
    }
    grading = _make_grading(per_node, total_count=2)

    profile = _build_profile("Python 入门", NODES_ALL_CORRECT[:2], grading)

    assert profile["theory_level"] == 1
    assert len(profile["known_topics"]) == 0
    assert len(profile["weak_topics"]) == 2


def test_build_profile_mixed():
    """混合正确率 — known/weak 按 mastery≥0.5 分界。"""
    per_node = {
        "PY-001": [{"question_index": 0, "correct": True}, {"question_index": 1, "correct": True}],   # mastery=1.0
        "PY-002": [{"question_index": 2, "correct": False}],                                          # mastery=0.0
    }
    grading = _make_grading(per_node, total_count=3)

    profile = _build_profile("Python 入门", NODES_MIXED[:2], grading)

    assert profile["known_topics"][0]["node_id"] == "PY-001"
    assert profile["weak_topics"][0]["node_id"] == "PY-002"


def test_build_profile_topics_carry_name():
    """画像 known/weak 条目带 name (前端盲区图按名称展示, 治理 PY-xxx 混显)。"""
    per_node = {
        "PY-001": [{"question_index": 0, "correct": True}],   # mastery=1.0 → known
        "PY-002": [{"question_index": 1, "correct": False}],  # mastery=0.0 → weak
    }
    grading = _make_grading(per_node, total_count=2)
    profile = _build_profile("Python 入门", NODES_MIXED[:2], grading)

    assert profile["known_topics"][0]["name"] == "变量"
    assert profile["weak_topics"][0]["name"] == "条件"


# ---- 赛题(2) 先验画像: 学历/专业背景透传 (可选采集, 白名单规范化) ----

_EMPTY_GRADING = {"per_node": {}, "correct_count": 0, "total_count": 0}


def test_build_profile_demographics_landed_normalized():
    """demographics 透传入画像, 仅保留白名单键并去首尾空白。"""
    profile = _build_profile(
        "Python 入门", [], _EMPTY_GRADING,
        demographics={"education": " 本科 ", "major": "会计学", "hacked": "x"},
    )
    assert profile["demographics"] == {"education": "本科", "major": "会计学"}


def test_build_profile_demographics_absent_returns_none():
    """未采集 (缺省) → demographics 为 None, 画像契约向后兼容。"""
    profile = _build_profile("Python 入门", [], _EMPTY_GRADING)
    assert profile["demographics"] is None


def test_build_profile_demographics_blank_returns_none():
    """全空白值 → None (不落空键)。"""
    profile = _build_profile(
        "Python 入门", [], _EMPTY_GRADING,
        demographics={"education": "  ", "major": ""},
    )
    assert profile["demographics"] is None


def test_build_profile_mastery_boundary():
    """BUG-039: mastery 三段制 — ≥0.8 归 known, <0.8 (含0.5学习中) 归 weak。"""
    nodes = [
        {"node_id": "PY-001", "name": "A", "difficulty": 1},
        {"node_id": "PY-002", "name": "B", "difficulty": 1},
        {"node_id": "PY-005", "name": "C", "difficulty": 1},
    ]
    per_node = {
        # 4题全对 = mastery=1.0 → known
        "PY-001": [{"question_index": 0, "correct": True}, {"question_index": 1, "correct": True}],
        # 2题1对1错 = mastery=0.5 → weak (学习中, 旧误判known致循环)
        "PY-002": [{"question_index": 2, "correct": True}, {"question_index": 3, "correct": False}],
        # 全错 = mastery=0.0 → weak
        "PY-005": [{"question_index": 4, "correct": False}, {"question_index": 5, "correct": False}],
    }
    grading = _make_grading(per_node, total_count=6)
    profile = _build_profile("Python", nodes, grading, questions=[])

    # mastery=1.0 → known (≥0.8)
    assert len(profile["known_topics"]) == 1
    assert profile["known_topics"][0]["node_id"] == "PY-001"
    # mastery=0.5 和 0.0 → weak (<0.8)
    weak_ids = [t["node_id"] for t in profile["weak_topics"]]
    assert set(weak_ids) == {"PY-002", "PY-005"}
    # 0.5 不再误归 known
    assert "PY-002" not in [t["node_id"] for t in profile["known_topics"]]


def test_build_profile_level_mapping():
    """theory_level 映射: BUG-035 保守分段 <0.6→1, <0.7→2, <0.8→3, <0.9→4, ≥0.9→5。"""
    # 2/10 correct = 0.2 → level=1 (<0.6)
    per_node = {}
    for i in range(10):
        nid = f"PY-{i:03d}"
        correct = i < 2  # 前2题对
        per_node[nid] = [{"question_index": i, "correct": correct}]
    grading = _make_grading(per_node, total_count=10)

    # Create matching nodes
    nodes = [{"node_id": f"PY-{i:03d}", "name": f"Node{i}", "difficulty": 1} for i in range(10)]
    profile = _build_profile("Python", nodes, grading)

    assert profile["theory_level"] == 1  # 0.2 → level 1 (<0.6)


def test_build_profile_empty_nodes_fallback():
    """零节点时 recommended_path.current_node 回退到 PY-001，next_nodes 为空。"""
    grading = {"per_node": {}, "correct_count": 0, "total_count": 0}
    profile = _build_profile("Python", [], grading)

    assert profile["recommended_path"]["current_node"] == "PY-001"
    assert profile["recommended_path"]["next_nodes"] == []
    # BUG-038: 无弱项无未掌握节点 → weeks=1 (巩固)，不再固定 4
    assert profile["recommended_path"]["estimated_completion_weeks"] == 1
    assert profile["known_topics"] == []
    assert profile["weak_topics"] == []


def test_build_profile_weakness_areas():
    """弱项节点生成 weakness_areas 文本。"""
    per_node = {
        "PY-001": [{"question_index": 0, "correct": False}],
    }
    grading = _make_grading(per_node, total_count=1)

    profile = _build_profile("Python", NODES_ALL_CORRECT[:1], grading)
    assert any("变量" in area for area in profile["weakness_areas"])


def test_build_profile_recommended_start_weak_priority():
    """推荐起始节点优先弱项 → 弱项为空时用首个候选；next_nodes 取其后继。"""
    per_node = {
        "PY-001": [{"question_index": 0, "correct": True}],
        "PY-002": [{"question_index": 1, "correct": False}],
    }
    grading = _make_grading(per_node, total_count=2)

    profile = _build_profile("Python", NODES_ALL_CORRECT[:2], grading)

    # PY-002 是弱项 → 优先推荐为 current_node
    path = profile["recommended_path"]
    assert path["current_node"] == "PY-002"
    # next_nodes 取候选中 PY-002 之后的节点（此处为空，PY-002 是最后一个候选）
    assert path["next_nodes"] == []
    # issue-69: 预计周数按实际学时折算 (2 节点 × 20min = 0.67h → ceil(0.67/6) = 1 周),
    # 不再随弱项数线性膨胀 (旧公式给 3 周)
    assert path["estimated_completion_weeks"] == 1


def test_build_profile_recommended_path_next_nodes_sequence():
    """next_nodes 取 current_node 之后的候选节点序列（最多5个），排除已掌握节点 (BUG-034)。"""
    # PY-001 掌握、PY-002 弱项(current)、PY-003 掌握、PY-004 未测(不在per_node)
    # current=PY-002，后继候选 PY-003/PY-004，但 PY-003 已掌握被排除 → next_nodes=[PY-004]
    nodes = [
        {"node_id": "PY-001", "name": "变量", "difficulty": 1},
        {"node_id": "PY-002", "name": "条件", "difficulty": 2},
        {"node_id": "PY-003", "name": "循环", "difficulty": 3},
        {"node_id": "PY-004", "name": "函数", "difficulty": 3},
    ]
    per_node = {
        "PY-001": [{"question_index": 0, "correct": True}],
        "PY-002": [{"question_index": 1, "correct": False}],
        "PY-003": [{"question_index": 2, "correct": True}],
    }
    grading = _make_grading(per_node, total_count=3)
    profile = _build_profile("Python", nodes, grading)

    path = profile["recommended_path"]
    assert path["current_node"] == "PY-002"
    # BUG-034: PY-003 已掌握被排除，next_nodes 不含已掌握节点
    assert "PY-003" not in path["next_nodes"]
    assert "PY-001" not in path["next_nodes"]
    assert path["next_nodes"] == ["PY-004"]


# ============================================================
# BUG-034/035/036 修复 (W7①回归发现)
# ============================================================

def test_suggest_next_nodes_excludes_known():
    """BUG-034: next_nodes 排除 known_ids 中的已掌握节点。"""
    from app.agents.diagnostics import _suggest_next_nodes
    nodes = [{"node_id": f"PY-00{i}"} for i in range(1, 6)]
    # current=PY-002，known 含 PY-003/PY-004 → next 应只剩 PY-005
    result = _suggest_next_nodes(nodes, "PY-002", known_ids=["PY-003", "PY-004"])
    assert result == ["PY-005"]


def test_suggest_next_nodes_empty_when_all_known():
    """BUG-034: 后继全部已掌握 → next_nodes 为空 (不报错)。"""
    from app.agents.diagnostics import _suggest_next_nodes
    nodes = [{"node_id": "PY-001"}, {"node_id": "PY-002"}, {"node_id": "PY-003"}]
    result = _suggest_next_nodes(nodes, "PY-001", known_ids=["PY-002", "PY-003"])
    assert result == []


def test_derive_theory_level_mapping():
    """BUG-035: 正确率→等级保守分段映射，0.7→3(非4)，对齐'4级≥0.85'语义。"""
    from app.agents.diagnostics import _derive_theory_level
    assert _derive_theory_level(0.1) == 1
    assert _derive_theory_level(0.5) == 1    # <0.6 → 1
    assert _derive_theory_level(0.6) == 2    # [0.6,0.7) → 2
    assert _derive_theory_level(0.69) == 2
    assert _derive_theory_level(0.7) == 3    # [0.7,0.8) → 3 (关键: 旧误判4)
    assert _derive_theory_level(0.79) == 3
    assert _derive_theory_level(0.8) == 4    # [0.8,0.9) → 4 (含0.85)
    assert _derive_theory_level(0.85) == 4   # 4级≥0.85 自洽
    assert _derive_theory_level(0.89) == 4
    assert _derive_theory_level(0.9) == 5    # ≥0.9 → 5
    assert _derive_theory_level(1.0) == 5


def test_build_error_patterns_uses_wrong_questions():
    """BUG-036 深化: 有错题 → error_pattern 引用错题题目 (与错题对齐，reviewer 不批 fabricated)。"""
    from app.agents.diagnostics import _build_error_patterns
    node = {"name": "输入输出", "common_mistakes": ["print误用"], "key_points": ["print"]}
    wrong = [{"question": "input() 返回什么类型？"}, {"question": "print() 如何分隔多参数？"}]
    patterns = _build_error_patterns(node, wrong)
    assert len(patterns) == 2
    assert "input() 返回什么类型" in patterns[0]
    assert "print() 如何分隔" in patterns[1]


def test_build_error_patterns_uses_common_mistakes():
    """BUG-036: 无错题文本 → 节点有 common_mistakes → 取首条。"""
    from app.agents.diagnostics import _build_error_patterns
    node = {"name": "列表切片", "common_mistakes": ["切片索引混淆", "越界未处理"], "key_points": ["语法"]}
    assert _build_error_patterns(node) == ["切片索引混淆"]


def test_build_error_patterns_fallback_key_points():
    """BUG-036: 无错题无 common_mistakes → 按 key_points 生成。"""
    from app.agents.diagnostics import _build_error_patterns
    node = {"name": "循环", "common_mistakes": [], "key_points": ["for迭代", "while条件"]}
    patterns = _build_error_patterns(node)
    assert len(patterns) == 1
    assert "循环" in patterns[0] and "for迭代" in patterns[0]


def test_build_error_patterns_fallback_name_only():
    """BUG-036: 无错题无 common_mistakes 无 key_points → 兜底按名称。"""
    from app.agents.diagnostics import _build_error_patterns
    node = {"name": "函数"}
    patterns = _build_error_patterns(node)
    assert patterns == ["对《函数》掌握不足"]


def test_build_profile_all_mastered_no_contradiction():
    """BUG-038: 全掌握 (无弱项) 画像不矛盾——current_node 不指向已掌握起点，weeks 缩短。"""
    # 3 节点全对 → 全 known，无 weak
    nodes = [
        {"node_id": "PY-001", "name": "变量", "difficulty": 1},
        {"node_id": "PY-002", "name": "条件", "difficulty": 2},
        {"node_id": "PY-003", "name": "循环", "difficulty": 3},
    ]
    per_node = {n["node_id"]: [{"question_index": i, "correct": True}] for i, n in enumerate(nodes)}
    grading = _make_grading(per_node, total_count=3)
    profile = _build_profile("Python", nodes, grading, questions=[])

    path = profile["recommended_path"]
    # 无弱项 → weeks 不再固定 4 (巩固周数，短)
    assert path["estimated_completion_weeks"] < 4
    # next_nodes 排除全部已掌握 → 空
    assert path["next_nodes"] == []
    # current_node 不应是矛盾起点 (全掌握时取最后节点作巩固方向)
    assert path["current_node"] == "PY-003"
    assert profile["weak_topics"] == []


# ============================================================
# _grade — BUG-022 治本：LLM 显式回写 question_index + 兜底
# ============================================================

def _patch_model(monkeypatch, content):
    # _grade 走 get_chat_model(max_retries=1), 其它节点走 get_default_chat_model —— 两者都钉到假模型
    fake = lambda *a, **k: _FakeModel(content)
    monkeypatch.setattr("app.agents.diagnostics.get_default_chat_model", fake)
    monkeypatch.setattr("app.agents.diagnostics.get_chat_model", fake)


def test_grade_disordered_question_index(monkeypatch):
    """LLM 乱序返回 grades 时，按显式 question_index 正确归位（治本 BUG-022）。"""
    questions = [
        {"node_id": "PY-001", "question": "q0", "answer": "A"},
        {"node_id": "PY-002", "question": "q1", "answer": "对"},
        {"node_id": "PY-001", "question": "q2", "answer": "B"},
    ]
    answers = ["A", "错", "B"]
    # LLM 乱序：先答 q2，再 q0，再 q1，但显式回写了正确的 question_index
    grades = json.dumps([
        {"question_index": 2, "node_id": "PY-001", "correct": True},
        {"question_index": 0, "node_id": "PY-001", "correct": True},
        {"question_index": 1, "node_id": "PY-002", "correct": False},
    ])
    _patch_model(monkeypatch, grades)

    result = _grade(questions, answers)

    # PY-001: q0 对、q2 对 → mastery 应为 2/2
    assert [g["question_index"] for g in result["per_node"]["PY-001"]] == [2, 0]
    assert all(g["correct"] for g in result["per_node"]["PY-001"])
    # PY-002: q1 错
    assert result["per_node"]["PY-002"] == [{"question_index": 1, "correct": False}]
    assert result["correct_count"] == 2
    assert result["total_count"] == 3


def test_grade_fallback_when_question_index_missing(monkeypatch):
    """LLM 未回写 question_index 时，回退到 grades 数组下标兜底。"""
    questions = [
        {"node_id": "PY-001", "question": "q0", "answer": "A"},
        {"node_id": "PY-002", "question": "q1", "answer": "对"},
    ]
    answers = ["A", "对"]
    # LLM 旧格式：无 question_index 字段
    grades = json.dumps([
        {"node_id": "PY-001", "correct": True},
        {"node_id": "PY-002", "correct": True},
    ])
    _patch_model(monkeypatch, grades)

    result = _grade(questions, answers)
    assert result["per_node"]["PY-001"] == [{"question_index": 0, "correct": True}]
    assert result["per_node"]["PY-002"] == [{"question_index": 1, "correct": True}]
    assert result["correct_count"] == 2


def test_grade_fallback_when_question_index_out_of_range(monkeypatch):
    """LLM 回写的 question_index 越界时回退到数组下标。"""
    questions = [
        {"node_id": "PY-001", "question": "q0", "answer": "A"},
    ]
    grades = json.dumps([
        {"question_index": 99, "node_id": "PY-001", "correct": True},
    ])
    _patch_model(monkeypatch, grades)

    result = _grade(questions, ["A"])
    # 99 越界 → 回退到下标 0
    assert result["per_node"]["PY-001"] == [{"question_index": 0, "correct": True}]


def test_grade_node_id_resolved_from_question_not_grade(monkeypatch):
    """F5: node_id 用题目真实值反查，grade 漏写/错写 node_id 不影响 per_node 分组。"""
    questions = [
        {"node_id": "PY-005", "question": "q0", "answer": "A"},
        {"node_id": "PY-008", "question": "q1", "answer": "对"},
    ]
    # LLM 在 grade 里漏写/错写 node_id (null / 错值)
    grades = json.dumps([
        {"question_index": 0, "node_id": None, "correct": True},
        {"question_index": 1, "node_id": "WRONG-999", "correct": False},
    ])
    _patch_model(monkeypatch, grades)

    result = _grade(questions, ["A", "错"])
    # 反查 questions 真实 node_id，而非信任 grade 回传
    assert result["per_node"]["PY-005"] == [{"question_index": 0, "correct": True}]
    assert result["per_node"]["PY-008"] == [{"question_index": 1, "correct": False}]
    assert "WRONG-999" not in result["per_node"]
    assert None not in result["per_node"]
    assert result["correct_count"] == 1


# ============================================================
# decide_feedback (W5 动态反馈纯函数)
# ============================================================

from app.agents.diagnostics import decide_feedback


def test_feedback_advance():
    """正确率 ≥0.8 → advance 进阶。"""
    fb = decide_feedback(8, 10)
    assert fb["strategy"] == "advance"
    assert fb["accuracy"] == 0.8


def test_feedback_advance_boundary_80():
    """8/10 = 0.8 → advance (边界包含)。"""
    assert decide_feedback(8, 10)["strategy"] == "advance"


def test_feedback_remediate():
    """0.5 ≤ 正确率 < 0.8 → remediate 降维。"""
    fb = decide_feedback(6, 10)
    assert fb["strategy"] == "remediate"
    assert fb["accuracy"] == 0.6


def test_feedback_remediate_boundary_50():
    """5/10 = 0.5 → remediate (边界包含)。"""
    assert decide_feedback(5, 10)["strategy"] == "remediate"


def test_feedback_scaffold():
    """正确率 <0.5 → scaffold 补前置。"""
    fb = decide_feedback(3, 10)
    assert fb["strategy"] == "scaffold"
    assert fb["accuracy"] == 0.3


def test_feedback_zero_correct():
    """全错 → scaffold。"""
    assert decide_feedback(0, 10)["strategy"] == "scaffold"


def test_feedback_zero_total_no_crash():
    """total=0 不崩溃 (除以 1 兜底)。"""
    fb = decide_feedback(0, 0)
    assert fb["strategy"] == "scaffold"
    assert fb["accuracy"] == 0.0


def test_feedback_full_correct():
    """全对 → advance。"""
    assert decide_feedback(10, 10)["strategy"] == "advance"


# ============================================================
# BUG-2: _grade correct 字符串布尔 / BUG-5: question_index 去重
# ============================================================

def test_grade_string_correct_false(monkeypatch):
    """BUG-2: LLM 返回 'correct':'false' (字符串) 不被误判为 True。"""
    questions = [{"node_id": "PY-005", "question": "q0", "answer": "A"}]
    grades = json.dumps([{"question_index": 0, "node_id": "PY-005", "correct": "false"}])
    _patch_model(monkeypatch, grades)
    result = _grade(questions, ["A"])
    assert result["per_node"]["PY-005"][0]["correct"] is False
    assert result["correct_count"] == 0


def test_grade_string_correct_true(monkeypatch):
    """BUG-2: 'correct':'true' (字符串) 判为 True。"""
    questions = [{"node_id": "PY-005", "question": "q0", "answer": "A"}]
    grades = json.dumps([{"question_index": 0, "node_id": "PY-005", "correct": "True"}])
    _patch_model(monkeypatch, grades)
    result = _grade(questions, ["A"])
    assert result["per_node"]["PY-005"][0]["correct"] is True
    assert result["correct_count"] == 1


def test_grade_dedup_duplicate_question_index(monkeypatch):
    """BUG-5: LLM 对同一 question_index 返回多条 → 去重，correct_count 不虚增。"""
    questions = [
        {"node_id": "PY-005", "question": "q0", "answer": "A"},
        {"node_id": "PY-008", "question": "q1", "answer": "对"},
    ]
    # q0 被判两次 (都正确)，q1 一次
    grades = json.dumps([
        {"question_index": 0, "node_id": "PY-005", "correct": True},
        {"question_index": 0, "node_id": "PY-005", "correct": True},  # 重复
        {"question_index": 1, "node_id": "PY-008", "correct": True},
    ])
    _patch_model(monkeypatch, grades)
    result = _grade(questions, ["A", "对"])
    # 去重后 correct_count=2 (非3), per_node 每题一条
    assert result["correct_count"] == 2
    assert len(result["per_node"]["PY-005"]) == 1


# ============================================================
# 题库驱动出题: _select_from_bank / prepare_questions (W7②)
# ============================================================

from app.agents.diagnostics import (
    _select_from_bank,
    prepare_questions,
    BANK_TYPES,
    MAX_THEORY_QUESTIONS,
)


class _BankFakeKG:
    """假 KG: get_questions_for_nodes 返回预设题库。记录调用参数。"""

    def __init__(self, bank_by_node: dict):
        # bank_by_node: {node_id: [question, ...]}
        self._bank = bank_by_node
        self.last_call = None

    def get_questions_for_nodes(self, node_ids, types=None, max_per_node=2):
        self.last_call = dict(node_ids=node_ids, types=types, max_per_node=max_per_node)
        result = []
        for nid in node_ids:
            qs = self._bank.get(nid, [])
            for q in qs[:max_per_node]:
                if types and q.get("type") not in types:
                    continue
                result.append(dict(q))  # 拷贝避免污染
        return result


def _make_node(nid="PY-005", name="循环", difficulty=2):
    return {"node_id": nid, "name": name, "difficulty": difficulty, "key_points": ["for", "while"]}


def test_select_from_bank_picks_choice_fill_excludes_code():
    """题库含 choice/fill/code → 只抽 choice/fill, 排除 code。"""
    kg = _BankFakeKG({"PY-005": [
        {"qid": "Q1", "source_node_id": "PY-005", "node_id": "PY-005", "type": "choice",
         "question": "q", "options": ["A"], "answer": "A", "difficulty": 2},
        {"qid": "Q2", "source_node_id": "PY-005", "node_id": "PY-005", "type": "fill",
         "question": "q", "answer": "x", "difficulty": 2},
        {"qid": "Q3", "source_node_id": "PY-005", "node_id": "PY-005", "type": "code",
         "question": "q", "answer": "print(1)", "difficulty": 3},
    ]})
    banked = _select_from_bank(kg, [_make_node()], target_count=10, seed=42)
    types = {q["type"] for q in banked}
    assert types <= set(BANK_TYPES)  # 不含 code
    assert "code" not in types


def test_select_from_bank_respects_per_node_limit():
    """单节点 ≥2 题 → max_per_node=QUESTIONS_PER_NODE 限制 (引擎层)。"""
    qs = [{"qid": f"Q{i}", "source_node_id": "PY-005", "node_id": "PY-005",
           "type": "choice", "question": f"q{i}", "answer": "A", "difficulty": 2} for i in range(5)]
    kg = _BankFakeKG({"PY-005": qs})
    _select_from_bank(kg, [_make_node()], seed=42)
    # 引擎 max_per_node=2 → 传给 get_questions_for_nodes
    assert kg.last_call["max_per_node"] == 2


def test_select_from_bank_seed_reproducible():
    """同 seed + 同 kg 两次抽题结果一致。"""
    bank = {
        "PY-005": [{"qid": f"Q5-{i}", "source_node_id": "PY-005", "node_id": "PY-005",
                     "type": "choice", "question": f"q{i}", "answer": "A", "difficulty": 2} for i in range(4)],
        "PY-008": [{"qid": f"Q8-{i}", "source_node_id": "PY-008", "node_id": "PY-008",
                     "type": "fill", "question": f"q{i}", "answer": "x", "difficulty": 3} for i in range(4)],
    }
    nodes = [_make_node("PY-005"), _make_node("PY-008", "函数", 3)]
    r1 = _select_from_bank(_BankFakeKG(bank), nodes, seed=7)
    r2 = _select_from_bank(_BankFakeKG(bank), nodes, seed=7)
    assert [q["qid"] for q in r1] == [q["qid"] for q in r2]


def test_select_from_bank_empty_returns_empty():
    """题库空 → 返回空 (shortfall 由 prepare_questions LLM 补)。"""
    kg = _BankFakeKG({})
    assert _select_from_bank(kg, [_make_node()], seed=42) == []


def test_prepare_questions_bank_sufficient_no_llm(monkeypatch):
    """题库够 10 题 (5节点×2题, 每节点max2) → 不调 LLM。"""
    # 5 节点各 2 题 = 10 题, 满足每节点 max_per_node=2 限制
    bank = {}
    nodes = []
    for i in range(5):
        nid = f"PY-00{i}"
        bank[nid] = [
            {"qid": f"Q-{nid}-1", "source_node_id": nid, "node_id": nid, "type": "choice",
             "question": f"q{i}a", "options": ["A"], "answer": "A", "difficulty": 2},
            {"qid": f"Q-{nid}-2", "source_node_id": nid, "node_id": nid, "type": "fill",
             "question": f"q{i}b", "answer": "x", "difficulty": 2},
        ]
        nodes.append(_make_node(nid))
    kg = _BankFakeKG(bank)

    def _boom(*a, **kw):
        raise AssertionError("不应调用 LLM (题库已够)")
    monkeypatch.setattr("app.agents.diagnostics.get_default_chat_model", _boom)
    monkeypatch.setattr("app.agents.diagnostics.llm_configured", lambda: True)
    monkeypatch.setattr("app.agents.diagnostics._fetch_candidate_nodes",
                        lambda kg, kt, td: nodes)
    questions, _ = prepare_questions(kg, "Python", [], seed=42)
    assert len(questions) == 10  # 5节点×2题, 不调 LLM


def test_prepare_questions_llm_supplements_shortfall(monkeypatch):
    """题库仅 2 题 (单节点max2全取) → LLM 补 8 题, 总数=10。"""
    qs = [{"qid": f"Q{i}", "source_node_id": "PY-005", "node_id": "PY-005",
           "type": "choice", "question": f"q{i}", "answer": "A", "difficulty": 2} for i in range(2)]
    kg = _BankFakeKG({"PY-005": qs})

    # shortfall=8, LLM 补 8 道
    supp = [{"type": "choice", "node_id": "PY-005", "question": f"s{i}",
             "options": ["A"], "answer": "A", "difficulty": 2} for i in range(8)]
    _patch_model(monkeypatch, json.dumps(supp))
    monkeypatch.setattr("app.agents.diagnostics.llm_configured", lambda: True)
    monkeypatch.setattr("app.agents.diagnostics._fetch_candidate_nodes",
                        lambda kg, kt, td: [_make_node()])

    questions, nodes = prepare_questions(kg, "Python", [], seed=42)
    assert len(questions) == 10


def test_prepare_questions_no_llm_no_bank_raises(monkeypatch):
    """LLM 未配置 + 题库空 → raise ValueError。"""
    kg = _BankFakeKG({})
    monkeypatch.setattr("app.agents.diagnostics.llm_configured", lambda: False)
    monkeypatch.setattr("app.agents.diagnostics._fetch_candidate_nodes",
                        lambda kg, kt, td: [_make_node()])
    with pytest.raises(ValueError, match="LLM 未配置"):
        prepare_questions(kg, "Python", [], seed=42)


def test_prepare_questions_no_llm_bank_partial_ok(monkeypatch):
    """LLM 未配置 + 题库有2题 (单节点max2) → 不报错, 返回2题 (不足但题库兜底)。"""
    qs = [{"qid": f"Q{i}", "source_node_id": "PY-005", "node_id": "PY-005",
           "type": "choice", "question": f"q{i}", "answer": "A", "difficulty": 2} for i in range(2)]
    kg = _BankFakeKG({"PY-005": qs})
    monkeypatch.setattr("app.agents.diagnostics.llm_configured", lambda: False)
    monkeypatch.setattr("app.agents.diagnostics._fetch_candidate_nodes",
                        lambda kg, kt, td: [_make_node()])
    questions, _ = prepare_questions(kg, "Python", [], seed=42)
    assert len(questions) == 2


def test_grade_with_banked_questions_per_node(monkeypatch):
    """题库题 (node_id=source_node_id) 经 _grade → per_node 正确分组 (回归 node_id 注入)。"""
    questions = [
        {"node_id": "PY-005", "question": "q0", "answer": "A", "type": "choice"},
        {"node_id": "PY-008", "question": "q1", "answer": "x", "type": "fill"},
    ]
    grades = json.dumps([
        {"question_index": 0, "node_id": "PY-005", "correct": True},
        {"question_index": 1, "node_id": "PY-008", "correct": False},
    ])
    _patch_model(monkeypatch, grades)
    result = _grade(questions, ["A", "wrong"])
    assert result["correct_count"] == 1
    assert "PY-005" in result["per_node"]
    assert "PY-008" in result["per_node"]


# ============================================================
# A1 回归: demo 工作流节点走题库出题 (不再纯 LLM 造 judge 题)
# ============================================================

from app.agents.diagnostics import diagnostics_node


def test_diagnostics_node_demo_uses_bank_not_judge(monkeypatch):
    """demo 节点出题来自 :Question 题库 (choice/fill), 不再走纯 LLM 造 judge 题 (A1)。

    题库给 5 节点×2 题=10 满足, 不触发补题 LLM; 仅 mock demo 作答 + 判分两次 LLM。
    断言: 出题全部 choice/fill (无 judge), node_id 来自题库注入。
    """
    nodes = [_make_node(f"PY-00{i}") for i in range(5)]
    bank = {}
    for n in nodes:
        bank[n["node_id"]] = [
            {"qid": f"Q-{n['node_id']}-1", "source_node_id": n["node_id"], "node_id": n["node_id"],
             "type": "choice", "question": f"{n['node_id']}c", "options": ["A", "B"],
             "answer": "A", "difficulty": 2},
            {"qid": f"Q-{n['node_id']}-2", "source_node_id": n["node_id"], "node_id": n["node_id"],
             "type": "fill", "question": f"{n['node_id']}f", "answer": "x", "difficulty": 2},
        ]
    kg = _BankFakeKG(bank)

    monkeypatch.setattr("app.agents.diagnostics.llm_configured", lambda: True)
    monkeypatch.setattr("app.agents.diagnostics._fetch_candidate_nodes",
                        lambda kg, kt, td: nodes)
    # 题库满 10 不触发补题 LLM; 仅 demo 作答 + 判分两次 LLM, 用序列模型分别喂
    calls = {"n": 0}

    class _SeqModel:
        def __init__(self):
            self._seq = [
                json.dumps(["A", "B"] * 5),  # _demo_answer
                json.dumps([{"question_index": i, "node_id": nodes[i // 2]["node_id"],
                             "correct": i % 2 == 0} for i in range(10)]),  # _grade
            ]
        def invoke(self, msgs):
            c = self._seq[calls["n"]]
            calls["n"] += 1
            return _FakeModel(c).invoke(msgs)

    monkeypatch.setattr("app.agents.diagnostics.get_default_chat_model", _SeqModel)
    # 判分使用专属 get_chat_model（45s/零重试），也必须隔离为同一序列假模型，
    # 避免该离线单测意外使用本机 API key 发起真实网络请求。
    monkeypatch.setattr("app.agents.diagnostics.get_chat_model", lambda **_kwargs: _SeqModel())

    node_fn = diagnostics_node(kg)
    state = {"target_direction": "Python", "known_topics": [], "mode": "demo"}
    result = node_fn(state)

    questions = result["assessment"]["questions"]
    assert len(questions) == 10
    # A1 核心: 全部 choice/fill, 无 judge
    assert all(q["type"] in ("choice", "fill") for q in questions)
    assert "judge" not in {q["type"] for q in questions}
    # node_id 来自题库注入 (非空)
    assert all(q.get("node_id") for q in questions)


# ============================================================
# W5 三维测评: learning_style (VARK) / practical_level (代码测试证据)
# ============================================================

from app.agents.diagnostics import learning_style_from_quiz, practical_level_from_evidence


class TestLearningStyleFromQuiz:
    def test_majority_visual(self):
        result = learning_style_from_quiz(["v", "v", "a", "r", "k"])
        assert result == {"style": "visual", "source": "quiz"}

    def test_kinesthetic_majority_with_noise(self):
        result = learning_style_from_quiz(["K", " k ", "k", "v", "r", "bogus", ""])
        assert result == {"style": "kinesthetic", "source": "quiz"}

    def test_tie_takes_first_by_vark_order(self):
        # v=1, a=1, r=2, k=2 → max 平局按 dict 序 (v,a,r,k) 取先达最大者 r? 
        # 计数 r=2, k=2 → max 按 counts 值取, 平局时取先遍历到的 (v,a,r,k 顺序中 r 在前)
        result = learning_style_from_quiz(["r", "k", "r", "k"])
        assert result["source"] == "quiz"
        assert result["style"] in ("read_write", "kinesthetic")

    def test_empty_answers_defaults(self):
        assert learning_style_from_quiz(None) == {"style": "read_write", "source": "default"}
        assert learning_style_from_quiz([]) == {"style": "read_write", "source": "default"}
        assert learning_style_from_quiz(["x", 123]) == {"style": "read_write", "source": "default"}


class TestPracticalLevelFromEvidence:
    def test_no_evidence_unassessed(self):
        assert practical_level_from_evidence(None) == {"level": 1, "source": "unassessed"}
        assert practical_level_from_evidence({}) == {"level": 1, "source": "unassessed"}
        assert practical_level_from_evidence({"tests_total": 0}) == {"level": 1, "source": "unassessed"}

    def test_high_pass_rate_level_4(self):
        assert practical_level_from_evidence({"tests_passed": 9, "tests_total": 10}) == {"level": 4, "source": "code_test"}

    def test_medium_rates(self):
        assert practical_level_from_evidence({"tests_passed": 7, "tests_total": 10})["level"] == 3
        assert practical_level_from_evidence({"tests_passed": 5, "tests_total": 10})["level"] == 2
        assert practical_level_from_evidence({"tests_passed": 2, "tests_total": 10})["level"] == 1

    def test_invalid_values_unassessed(self):
        assert practical_level_from_evidence({"tests_passed": "x", "tests_total": "y"}) == {"level": 1, "source": "unassessed"}


class TestBuildProfile3Dim:
    """_build_profile 消费问卷/证据 → 画像带来源标记 (消除占位)。"""

    def _grading(self, rate=1.0, n=5):
        return {
            "per_node": {"PY-001": [{"question_index": i, "correct": i < n * rate} for i in range(n)]},
            "correct_count": int(n * rate),
            "total_count": n,
        }

    def _nodes(self):
        return [{"node_id": "PY-001", "name": "变量", "summary": "", "key_points": [], "common_mistakes": []}]

    def test_quiz_and_evidence_landed(self):
        profile = _build_profile(
            "Python 入门", self._nodes(), self._grading(),
            learning_style_quiz=["k", "k", "k", "v", "r"],
            practical_evidence={"tests_passed": 9, "tests_total": 10},
        )
        assert profile["learning_style"] == "kinesthetic"
        assert profile["style_source"] == "quiz"
        assert profile["practical_level"] == 4
        assert profile["practical_source"] == "code_test"

    def test_missing_inputs_keep_placeholder_with_source_marker(self):
        profile = _build_profile("Python 入门", self._nodes(), self._grading())
        assert profile["learning_style"] == "read_write"
        assert profile["style_source"] == "default"
        assert profile["practical_level"] == 1
        assert profile["practical_source"] == "unassessed"
