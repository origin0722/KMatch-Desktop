"""engine.assemble_learning_path 弱项覆盖逻辑单测 (M5 覆盖率修复回归)。

聚焦弱项补丁纯逻辑: BFS Cypher 用 fake driver 喂空结果 (路径全由弱项补丁决定),
monkeypatch get_prerequisites/get_node 验证修复后契约 —— 弱项节点本身纳入路径。
真实 Neo4j 集成验证由 run_quality_test.py 的覆盖率数字承担。
"""

from unittest.mock import MagicMock

from app.graph.engine import KnowledgeGraph


def _make_kg():
    """构造 KnowledgeGraph (不连 Neo4j), driver 喂空 BFS 结果。"""
    kg = KnowledgeGraph.__new__(KnowledgeGraph)
    kg.driver = MagicMock()
    # BFS Cypher run 返回空 (路径全由弱项补丁决定, 逻辑清晰可断言)
    session = MagicMock()
    result = MagicMock()
    result.__iter__ = lambda self: iter([])
    session.run.return_value = result
    kg.driver.session.return_value.__enter__ = lambda s: session
    kg.driver.session.return_value.__exit__ = lambda *a: None
    return kg


def test_weak_node_itself_included_in_path():
    """修复核心: 弱项节点本身必须出现在路径中 (覆盖率指标)。"""
    kg = _make_kg()
    kg.get_prerequisites = MagicMock(return_value=[])  # 无前置
    kg.get_node = MagicMock(return_value={
        "node_id": "PY-099", "difficulty": 2, "estimated_minutes": 60, "name": "弱项X"})

    path = kg.assemble_learning_path(
        known_ids=["PY-001"], weak_ids=["PY-099"], level=2, max_nodes=10)

    path_ids = [n["node_id"] for n in path]
    assert "PY-099" in path_ids, "弱项节点本身必须纳入路径"


def test_weak_node_prereq_inserted_before_weak():
    """弱项前置依赖应先于弱项节点入路径。"""
    kg = _make_kg()
    kg.get_prerequisites = MagicMock(return_value=[
        {"node_id": "PY-098", "difficulty": 1, "name": "前置"}])
    kg.get_node = MagicMock(return_value={
        "node_id": "PY-099", "difficulty": 2, "estimated_minutes": 60, "name": "弱项X"})

    path = kg.assemble_learning_path(
        known_ids=["PY-001"], weak_ids=["PY-099"], level=2, max_nodes=10)

    path_ids = [n["node_id"] for n in path]
    assert "PY-098" in path_ids
    assert "PY-099" in path_ids
    assert path_ids.index("PY-098") < path_ids.index("PY-099"), "前置须先于弱项"


def test_weak_node_above_difficulty_cap_skipped():
    """弱项难度超 level+2 cap (零基础 level=1 → cap 3) → 跳过弱项本身, 前置仍入。"""
    kg = _make_kg()
    kg.get_prerequisites = MagicMock(return_value=[
        {"node_id": "PY-098", "difficulty": 1, "name": "前置"}])
    kg.get_node = MagicMock(return_value={
        "node_id": "PY-099", "difficulty": 5, "estimated_minutes": 90, "name": "高难弱项"})

    path = kg.assemble_learning_path(
        known_ids=["PY-001"], weak_ids=["PY-099"], level=1, max_nodes=10)

    path_ids = [n["node_id"] for n in path]
    assert "PY-099" not in path_ids, "超 cap 弱项本身不入路径 (避免挫败)"
    assert "PY-098" in path_ids, "前置仍应入路径"


def test_multiple_weak_nodes_all_included():
    """多弱项 (≤3) 全部纳入路径。"""
    kg = _make_kg()
    kg.get_prerequisites = MagicMock(return_value=[])
    weak_nodes = {
        "PY-091": {"node_id": "PY-091", "difficulty": 2, "estimated_minutes": 60, "name": "w1"},
        "PY-092": {"node_id": "PY-092", "difficulty": 2, "estimated_minutes": 60, "name": "w2"},
        "PY-093": {"node_id": "PY-093", "difficulty": 2, "estimated_minutes": 60, "name": "w3"},
    }
    kg.get_node = MagicMock(side_effect=lambda nid: weak_nodes.get(nid))

    path = kg.assemble_learning_path(
        known_ids=["PY-001"], weak_ids=["PY-091", "PY-092", "PY-093"],
        level=2, max_nodes=20)

    path_ids = [n["node_id"] for n in path]
    for wid in ("PY-091", "PY-092", "PY-093"):
        assert wid in path_ids


def test_weak_in_known_set_not_re_added():
    """弱项已在 known_set → 不重复加入 (known 优先)。"""
    kg = _make_kg()
    kg.get_prerequisites = MagicMock(return_value=[])
    kg.get_node = MagicMock(return_value={
        "node_id": "PY-099", "difficulty": 2, "estimated_minutes": 60, "name": "弱项X"})

    path = kg.assemble_learning_path(
        known_ids=["PY-099"], weak_ids=["PY-099"], level=2, max_nodes=10)

    path_ids = [n["node_id"] for n in path]
    assert path_ids.count("PY-099") == 0, "已知弱项不再加入路径 (已在 known_set)"


def test_weak_prereq_above_difficulty_cap_skipped():
    """B1: 弱项前置难度超 level+2 cap → 前置也跳过 (避免前置比弱项还难)。

    level=1 → cap=3; 弱项难度2 (可入), 前置难度4 (超 cap) → 前置不入路径。
    """
    kg = _make_kg()
    kg.get_prerequisites = MagicMock(return_value=[
        {"node_id": "PY-098", "difficulty": 4, "name": "高难前置"}])
    kg.get_node = MagicMock(return_value={
        "node_id": "PY-099", "difficulty": 2, "estimated_minutes": 60, "name": "弱项X"})

    path = kg.assemble_learning_path(
        known_ids=["PY-001"], weak_ids=["PY-099"], level=1, max_nodes=10)

    path_ids = [n["node_id"] for n in path]
    assert "PY-098" not in path_ids, "超 cap 前置应跳过 (BUG B1)"
    assert "PY-099" in path_ids, "弱项本身难度2 ≤ cap3 仍入路径"


# ============================================================
# 优化回归: generate_embeddings 批量 UNWIND 写回 + None 跳过
# ============================================================


class _FakeEmbResp:
    def __init__(self, n):
        self.data = [type("D", (), {"embedding": [0.1 * i, 0.2]})() for i in range(n)]


class _FakeEmbClient:
    def __init__(self):
        self.embeddings = type("E", (), {"create": self._create})()
    def _create(self, model, input):
        return _FakeEmbResp(len(input))


def _make_kg_with_driver():
    kg = KnowledgeGraph.__new__(KnowledgeGraph)
    kg.driver = MagicMock()
    kg.embedding_client = None
    kg.embedding_model = "test-emb"
    kg.vector_index_name = "idx"
    session = MagicMock()
    kg.driver.session.return_value.__enter__ = lambda s: session
    kg.driver.session.return_value.__exit__ = lambda *a: None
    return kg, session


def test_generate_embeddings_unwind_batch_single_run():
    """UNWIND 批量写: N 节点 1 批 → 仅 1 次 s.run (旧实现 N 次)。"""
    kg, session = _make_kg_with_driver()
    kg.embedding_client = _FakeEmbClient()
    nodes = [{"node_id": f"PY-{i:03d}", "name": f"n{i}", "summary": "s"} for i in range(5)]
    kg.generate_embeddings(nodes, batch_size=20)
    # 1 批 → 1 次 run (UNWIND), 而非 5 次
    assert session.run.call_count == 1
    # 确认用了 UNWIND
    query = session.run.call_args[0][0]
    assert "UNWIND" in query
    rows = session.run.call_args[1]["rows"]
    assert len(rows) == 5


def test_generate_embeddings_skips_none_node_id():
    """node_id/id 都缺的节点跳过, 不写回 (防 MATCH {id:None} 误覆盖)。"""
    kg, session = _make_kg_with_driver()
    kg.embedding_client = _FakeEmbClient()
    nodes = [
        {"node_id": "PY-001", "name": "ok", "summary": "s"},
        {"name": "无id节点", "summary": "s"},  # 无 node_id/id
        {"node_id": "PY-002", "name": "ok2", "summary": "s"},
    ]
    kg.generate_embeddings(nodes, batch_size=20)
    # 只 2 个有效节点入 rows
    rows = session.run.call_args[1]["rows"]
    ids_written = [r["id"] for r in rows]
    assert ids_written == ["PY-001", "PY-002"]
    assert None not in ids_written


def test_generate_embeddings_no_client_skips():
    """未配置 embedding_client → 跳过, 不查 driver。"""
    kg, session = _make_kg_with_driver()
    kg.generate_embeddings([{"node_id": "PY-001", "name": "n", "summary": "s"}])
    session.run.assert_not_called()
