"""validate_data 工具函数单测 (BUG B4 循环检测崩溃回归)。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.validate_data import check_circular_dependencies


def test_no_cycle_clean():
    nodes = {
        "A": {"prerequisites": []},
        "B": {"prerequisites": ["A"]},
        "C": {"prerequisites": ["B"]},
    }
    assert check_circular_dependencies(nodes) == []


def test_simple_cycle_detected():
    """A↔B 简单环应被检出。"""
    nodes = {
        "A": {"prerequisites": ["B"]},
        "B": {"prerequisites": ["A"]},
    }
    errs = check_circular_dependencies(nodes)
    assert len(errs) >= 1
    assert "循环依赖" in errs[0]


def test_cycle_with_external_inbound_no_crash():
    """B4 核心回归: 环 A↔B + 环外 C 依赖环内 A → 不应 ValueError 崩溃, 应报告环。

    旧实现: 检出 A↔B 环时 return True 早退, A/B 残留 GRAY 未置 BLACK/未 pop;
    C 的 dfs 遇到 A(GRAY) 走 path.index('A') 但 A 不在 C 的 path → ValueError。
    """
    nodes = {
        "A": {"prerequisites": ["B"]},
        "B": {"prerequisites": ["A"]},
        "C": {"prerequisites": ["A"]},  # 环外入边
    }
    errs = check_circular_dependencies(nodes)  # 旧代码此处崩溃
    assert any("循环依赖" in e for e in errs)


def test_self_loop_detected():
    nodes = {"A": {"prerequisites": ["A"]}}
    errs = check_circular_dependencies(nodes)
    assert any("循环依赖" in e for e in errs)


from scripts.validate_data import validate_question, validate_questions_dir


def test_validate_question_orphan_source_node_detected():
    """B7: source_node_id 指向不存在节点 → 报孤儿题错误。"""
    q = {"qid": "Q1", "source_node_id": "PY-999", "type": "choice",
         "question": "q", "options": ["A"], "answer": "A", "difficulty": 2}
    errs = validate_question(q, "Q1", known_node_ids={"PY-001", "PY-005"})
    assert any("孤儿题" in e or "不存在" in e for e in errs)


def test_validate_question_valid_source_node_ok():
    q = {"qid": "Q1", "source_node_id": "PY-005", "type": "choice",
         "question": "q", "options": ["A"], "answer": "A", "difficulty": 2}
    errs = validate_question(q, "Q1", known_node_ids={"PY-001", "PY-005"})
    assert errs == []


def test_validate_question_no_known_ids_skips_refcheck():
    """不传 known_node_ids → 不做引用校验 (向后兼容)。"""
    q = {"qid": "Q1", "source_node_id": "PY-999", "type": "choice",
         "question": "q", "options": ["A"], "answer": "A", "difficulty": 2}
    errs = validate_question(q, "Q1")  # 默认 None
    assert errs == []


def test_validate_node_short_summary_and_name():
    """B13: summary 空串/过短、name 过短应报错 (旧 summary 空串因假值漏报)。"""
    from scripts.validate_data import validate_node
    schema = {"required": ["id", "name", "summary"], "properties": {
        "id": {"pattern": r"^[A-Z]{2}-\d{3}$"},
        "category": {"enum": ["basics"]}}}
    node = {"id": "PY-001", "name": "a", "summary": "", "difficulty": 1,
            "category": "basics", "tags": ["t"], "key_points": ["a", "b", "c"],
            "practice_questions": [{"type": "choice", "question": "q", "answer": "A"}],
            "prerequisites": []}
    errs = validate_node(node, schema, {"PY-001"})
    assert any("summary" in e for e in errs)
    assert any("name" in e for e in errs)


def test_validate_profile_mastery_non_number():
    """B13: mastery 非数值应报错 (旧代码 `0 <= "high"` 抛 TypeError 崩溃)。"""
    from scripts.validate_data import validate_user_profile
    profile = {"profile_id": "UP-1", "name": "x", "theory_level": 2,
               "practical_level": 2, "learning_style": "visual",
               "target_direction": "t", "preferred_pace": "normal", "time_per_week": 6,
               "known_topics": [{"node_id": "PY-001", "mastery": "high"}],  # 非数值
               "weak_topics": [], "weakness_areas": ["a"]}
    errs = validate_user_profile(profile, "p.json")
    assert any("mastery" in e and "非数值" in e for e in errs)


def test_validate_questions_dir_skips_schema_json(tmp_path):
    """questions/ 下的 schema.json (题目结构规范, 非数组) 不应被当题目校验报错。"""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from scripts.validate_data import validate_questions_dir
    qdir = tmp_path / "questions"
    qdir.mkdir()
    (qdir / "schema.json").write_text('{"title": "题目结构规范"}', encoding="utf-8")  # 非数组
    (qdir / "PY-001.json").write_text(
        '[{"qid":"Q1","source_node_id":"PY-001","type":"choice","question":"q","options":["A"],"answer":"A","difficulty":2}]',
        encoding="utf-8")
    total, errs = validate_questions_dir(str(qdir), {"PY-001"})
    assert total == 1
    assert "schema.json" not in errs
