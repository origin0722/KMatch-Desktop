"""engine Question 查询方法单测 — get_questions / get_questions_for_nodes / _question_from_record。

用 mock driver session 验证 Cypher 构造、type/difficulty 筛选、options 反序列化、
max_per_node 配额、node_id 注入。免真实 Neo4j。
"""

from unittest.mock import MagicMock

from app.graph.engine import KnowledgeGraph


def _make_kg_with_records(records):
    """构造 KnowledgeGraph,mock driver.session().run 返回固定 records。

    records: list of dict (每 dict 是一个 record['q'] 的题目属性)。
    engine 用 r['q'] 取题目, 故 mock record 的 __getitem__('q') 返回该 dict。
    """
    kg = KnowledgeGraph.__new__(KnowledgeGraph)  # 跳过 __init__ (不连 Neo4j)
    kg.driver = MagicMock()
    session = MagicMock()

    class _Rec:
        def __init__(self, qdict):
            self._q = qdict
        def __getitem__(self, key):
            return self._q  # engine 只取 r['q']

    result = MagicMock()
    result.__iter__ = lambda self: iter([_Rec(r) for r in records])
    session.run.return_value = result
    kg.driver.session.return_value.__enter__ = lambda s: session
    kg.driver.session.return_value.__exit__ = lambda *a: None
    return kg, session


def test_question_from_record_injects_node_id():
    """_question_from_record: source_node_id → node_id 别名 (供 _grade 分组)。"""
    kg = KnowledgeGraph.__new__(KnowledgeGraph)
    q = kg._question_from_record({
        "qid": "Q1", "source_node_id": "PY-005", "type": "choice",
        "question": "q", "options": ["A", "B"], "answer": "A", "difficulty": 2,
    })
    assert q["node_id"] == "PY-005"
    assert q["options"] == ["A", "B"]


def test_question_from_record_options_str_deserializes():
    """options 存字符串 → json.loads 还原 list。"""
    kg = KnowledgeGraph.__new__(KnowledgeGraph)
    q = kg._question_from_record({
        "qid": "Q1", "source_node_id": "PY-005", "type": "choice",
        "options": '["A", "B"]', "answer": "A", "difficulty": 2,
    })
    assert q["options"] == ["A", "B"]


def test_question_from_record_no_options_defaults_empty():
    """无 options (fill/code 题) → 空 list。"""
    kg = KnowledgeGraph.__new__(KnowledgeGraph)
    q = kg._question_from_record({
        "qid": "Q1", "source_node_id": "PY-005", "type": "fill", "answer": "x",
    })
    assert q["options"] == []


def test_get_questions_constructs_cypher_with_filters():
    """get_questions 传 type/difficulty → Cypher 含对应 WHERE 子句。"""
    records = [{"qid": "Q1", "source_node_id": "PY-005", "type": "choice",
                "options": ["A"], "answer": "A", "difficulty": 2}]
    kg, session = _make_kg_with_records(records)
    kg.get_questions("PY-005", types=["choice"], difficulty_min=1, difficulty_max=3, limit=5)
    cypher = session.run.call_args[0][0]
    params = session.run.call_args[0][1]
    assert "q.type IN $types" in cypher
    assert "q.difficulty >= $dmin" in cypher
    assert "q.difficulty <= $dmax" in cypher
    assert "LIMIT 5" in cypher
    assert params["types"] == ["choice"]
    assert params["node_id"] == "PY-005"


def test_get_questions_no_filters_minimal_where():
    """无筛选 → Cypher 无额外 WHERE (仅 MATCH)。"""
    records = []
    kg, session = _make_kg_with_records(records)
    kg.get_questions("PY-005")
    cypher = session.run.call_args[0][0]
    assert "WHERE" not in cypher


def test_get_questions_for_nodes_passes_node_ids():
    """get_questions_for_nodes → UNWIND 风格, 传 node_ids + max_per_node。"""
    records = [{"qid": "Q1", "source_node_id": "PY-005", "type": "choice",
                "options": [], "answer": "A", "difficulty": 2}]
    kg, session = _make_kg_with_records(records)
    kg.get_questions_for_nodes(["PY-005", "PY-008"], types=["choice"], max_per_node=3)
    cypher = session.run.call_args[0][0]
    params = session.run.call_args[0][1]
    assert "n.id IN $node_ids" in cypher
    assert "q.type IN $types" in cypher
    assert "$max_per_node" in cypher
    assert params["node_ids"] == ["PY-005", "PY-008"]
    assert params["max_per_node"] == 3


def test_get_questions_for_nodes_empty_returns_empty():
    kg = KnowledgeGraph.__new__(KnowledgeGraph)
    kg.driver = MagicMock()
    assert kg.get_questions_for_nodes([]) == []
    kg.driver.session.assert_not_called()
