"""KnowledgeGraph 项目图谱方法单测 — mock driver 记录 Cypher 调用，免真实 Neo4j。

覆盖:
  - write_project_graph: DETACH DELETE 先行 + 分 label 三批 CREATE + 关系 UNWIND
  - get_project_graph: 空返回 None；有数据组装 G6 结构 (JSON 字段还原)
  - delete_project_graph: 返回删除数
  - annotate_risk / link_entity_to_knowledge: SET/MERGE Cypher 正确

沿用现有不碰真库风格: fake session 记录 run() 调用断言 Cypher + params。
"""

import json

from app.code_parser.models import CodeEntity, CodeRelation
from app.graph.engine import KnowledgeGraph


class _FakeResult:
    """模拟 neo4j Result: 可迭代 (records) + .single() 取首条。"""

    def __init__(self, records):
        self._records = records or []

    def __iter__(self):
        return iter(self._records)

    def single(self):
        return self._records[0] if self._records else None


class _FakeSession:
    """记录 run() 调用，可预设返回值队列 (每项是 record-dict list)。"""

    def __init__(self):
        self.calls = []          # [(query, params_dict)]
        self._returns = []       # 预设返回值 (每项 list of dict record)

    def run(self, query, **params):
        self.calls.append((query, params))
        if self._returns:
            return _FakeResult(self._returns.pop(0))
        return _FakeResult([])

    def execute_write(self, tx_fn):
        """模拟 Neo4j 事务函数: tx_fn 内的 tx.run 复用本 session 的 run (记录调用)。

        真实 execute_write 把全部 run 纳单事务; 测试只需记录调用序列即可断言 Cypher。
        """
        tx_fn(self)  # tx 即本 session, tx.run → self.run
        return None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FakeDriver:
    def __init__(self):
        self.session_obj = _FakeSession()

    def session(self):
        return self.session_obj


def _make_kg():
    """构造 KnowledgeGraph 实例 (不真连 Neo4j，替换 driver)。"""
    kg = KnowledgeGraph.__new__(KnowledgeGraph)
    kg.driver = _FakeDriver()
    kg.embedding_client = None
    kg.embedding_model = "text-embedding-v2"
    kg.vector_index_name = "knowledge_embeddings"
    return kg


def _sample_entities(pid="p1"):
    return [
        CodeEntity(entity_id=f"PROJ-{pid}-MODULE-main", project_id=pid, kind="module",
                   name="main", qualified_name="main", module_name="main", layer=2,
                   line_start=1, line_end=10, docstring="mod"),
        CodeEntity(entity_id=f"PROJ-{pid}-CLASS-Foo", project_id=pid, kind="class",
                   name="Foo", qualified_name="Foo", module_name="main", layer=2,
                   line_start=2, line_end=8, bases=[], decorators=[]),
        CodeEntity(entity_id=f"PROJ-{pid}-METHOD-Foo.bar", project_id=pid, kind="method",
                   name="bar", qualified_name="Foo.bar", module_name="main", layer=3,
                   line_start=3, line_end=5, params=[{"name": "self"}], return_type="int",
                   is_method=True, parent_class_id=f"PROJ-{pid}-CLASS-Foo",
                   external_calls=[{"name": "print", "line": 4}]),
    ]


def _sample_relations(pid="p1"):
    return [
        CodeRelation(source=f"PROJ-{pid}-MODULE-main", target=f"PROJ-{pid}-CLASS-Foo", type="CONTAINS"),
        CodeRelation(source=f"PROJ-{pid}-CLASS-Foo", target=f"PROJ-{pid}-METHOD-Foo.bar", type="CONTAINS"),
    ]


# ============================================================
# write_project_graph
# ============================================================

def test_write_deletes_old_first():
    kg = _make_kg()
    kg.write_project_graph("p1", _sample_entities(), _sample_relations())
    first_query = kg.driver.session_obj.calls[0][0]
    assert "DETACH DELETE" in first_query
    assert kg.driver.session_obj.calls[0][1] == {"pid": "p1"}


def test_write_creates_by_label():
    kg = _make_kg()
    kg.write_project_graph("p1", _sample_entities(), _sample_relations())
    queries = [c[0] for c in kg.driver.session_obj.calls]
    # 含 Module / Class / Function 三批 CREATE
    assert any(":Module" in q and "UNWIND" in q for q in queries)
    assert any(":Class" in q and "UNWIND" in q for q in queries)
    assert any(":Function" in q and "UNWIND" in q for q in queries)


def test_write_serializes_list_of_map_to_json():
    """params / external_calls (list of map) 序列化为 JSON 字符串。"""
    kg = _make_kg()
    kg.write_project_graph("p1", _sample_entities(), _sample_relations())
    # 找 Function 批的 rows
    for query, params in kg.driver.session_obj.calls:
        if ":Function" in query:
            rows = params["rows"]
            func_row = next(r for r in rows if r["kind"] == "method")
            # params 已序列化为字符串
            assert isinstance(func_row["params"], str)
            assert json.loads(func_row["params"]) == [{"name": "self"}]
            assert isinstance(func_row["external_calls"], str)
            assert json.loads(func_row["external_calls"]) == [{"name": "print", "line": 4}]
            break


def test_write_creates_relations():
    kg = _make_kg()
    kg.write_project_graph("p1", _sample_entities(), _sample_relations())
    queries = [c[0] for c in kg.driver.session_obj.calls]
    assert any(":CONTAINS" in q for q in queries)


def test_write_skips_empty_batches():
    """无某类实体时跳过对应 CREATE (不传空 UNWIND)。"""
    kg = _make_kg()
    # 只有 module，无 class/function
    entities = [_sample_entities()[0]]
    kg.write_project_graph("p1", entities, [])
    queries = [c[0] for c in kg.driver.session_obj.calls]
    assert any(":Module" in q for q in queries)
    # 无 Class/Function 批
    assert not any(":Class" in q for q in queries)
    assert not any(":Function" in q for q in queries)


# ============================================================
# get_project_graph
# ============================================================

def test_get_returns_none_when_empty():
    kg = _make_kg()
    # node_result 返回空
    assert kg.get_project_graph("p1") is None


def test_get_assembles_g6_structure():
    kg = _make_kg()
    session = kg.driver.session_obj
    # 预设节点返回
    session._returns = [[
        {"n": {
            "entity_id": "PROJ-p1-CLASS-Foo", "project_id": "p1", "kind": "class",
            "name": "Foo", "qualified_name": "Foo", "module_name": "main", "layer": 2,
            "line_start": 2, "line_end": 8, "docstring": None,
            "params": "[]", "return_type": None, "bases": [], "decorators": [],
            "source_code": None, "is_method": False, "parent_class_id": None,
            "external_calls": "[]", "risk_level": None, "risk_reason": None,
        }},
    ]]
    # 边返回 (第二个 run)
    session._returns.append([{
        "source": "PROJ-p1-MODULE-main", "target": "PROJ-p1-CLASS-Foo",
        "type": "CONTAINS", "line": None, "resolved": None,
    }])

    result = kg.get_project_graph("p1")
    assert result is not None
    assert result["project_id"] == "p1"
    assert len(result["nodes"]) == 1
    node = result["nodes"][0]
    assert node["id"] == "PROJ-p1-CLASS-Foo"
    assert node["group"] == "class"
    assert node["layer"] == 2
    # JSON 字段还原为 list
    assert node["properties"]["params"] == []
    assert node["properties"]["external_calls"] == []
    assert len(result["edges"]) == 1
    assert result["edges"][0]["label"] == "CONTAINS"


# ============================================================
# delete_project_graph
# ============================================================

def test_delete_returns_count():
    kg = _make_kg()
    session = kg.driver.session_obj
    session._returns = [[{"c": 5}]]
    count = kg.delete_project_graph("p1")
    assert count == 5
    assert "DETACH DELETE" in session.calls[0][0]


# ============================================================
# annotate_risk / link_entity_to_knowledge (下批预留接口)
# ============================================================

def test_annotate_risk_sets_properties():
    kg = _make_kg()
    kg.annotate_risk("PROJ-p1-METHOD-Foo.bar", "medium", "测试未通过")
    query, params = kg.driver.session_obj.calls[0]
    assert "risk_level" in query
    assert "risk_reason" in query
    assert "risk_annotated_at" in query
    assert params["level"] == "medium"
    assert params["reason"] == "测试未通过"
    assert params["eid"] == "PROJ-p1-METHOD-Foo.bar"


def test_link_entity_to_knowledge_merges():
    kg = _make_kg()
    kg.link_entity_to_knowledge("PROJ-p1-METHOD-Foo.bar", "PY-012")
    query, params = kg.driver.session_obj.calls[0]
    assert "RELATED_TO" in query
    assert "MERGE" in query
    assert params["eid"] == "PROJ-p1-METHOD-Foo.bar"
    assert params["kid"] == "PY-012"
