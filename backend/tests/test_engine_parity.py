"""嵌入式图存储 — 真实数据回归 + 嵌入式↔Neo4j 等价性胶水 (ADR-0008 §9.2)。

- 真实数据回归: 以仓库 data/knowledge_base 只读载入嵌入式, 断言核心不变量 (可随处运行, 不需 Neo4j)。
- 等价性胶水: 同一数据下 embedded vs Neo4j 后端结果一致性抽验; Neo4j 不可达或为空时自动 skip。
"""

from pathlib import Path

import pytest

from app.graph.embedded import EmbeddedGraphStore

# backend/tests/ → 仓库根 → data
REPO_DATA = Path(__file__).resolve().parent.parent.parent / "data"
KB_BASE = REPO_DATA / "knowledge_base"


@pytest.fixture
def real_store(tmp_path: Path) -> EmbeddedGraphStore:
    return EmbeddedGraphStore(kb_dir=KB_BASE, local_dir=tmp_path / "local", embedding_client=None)


# ============================================================
# 真实数据回归 (无需 Neo4j)
# ============================================================

def test_real_data_core_invariants(real_store):
    # 全库规模
    nodes = real_store.get_by_difficulty(1, 5)
    assert len(nodes) >= 200          # 222+ 知识节点
    assert all("node_id" in n and "prerequisites" not in n for n in nodes[:10])

    # 图遍历非空
    entry = real_store.get_by_difficulty(1, 1)
    assert entry
    reach = real_store.get_reachable([entry[0]["node_id"]], max_depth=2)
    assert isinstance(reach, list)

    # 题目存在
    with_questions = [
        n["node_id"] for n in nodes if real_store.get_questions_by_node(n["node_id"])
    ]
    assert with_questions, "真实知识库应有题目"

    # 路径组装: 零基础 → 难度1入口; 有基础 → 后继非空
    base = real_store.assemble_learning_path([], [], level=1, max_nodes=20)
    assert base and all(n["difficulty"] <= 1 for n in base)
    seeded = real_store.assemble_learning_path([entry[0]["node_id"]], [], level=2, max_nodes=20)
    assert seeded

    # 语义降级 (无客户端) 不抛错
    assert real_store.semantic_search("any", top_k=3) == []
    assert real_store.semantic_ready is False


def test_real_data_mutable_roundtrip(real_store):
    """项目图谱 + 掌握状态在真实数据基底上的落盘回读。"""
    real_store.update_node_status("PY-001", "in_progress")
    assert real_store.get_node_status("PY-001") == "in_progress"

    real_store.write_project_graph(
        "parity-smoke",
        [{"entity_id": "m1", "kind": "module", "name": "m", "layer": 2}],
        [],
    )
    g = real_store.get_project_graph("parity-smoke")
    assert g and g["nodes"][0]["id"] == "m1"
    assert real_store.delete_project_graph("parity-smoke") == 1


# ============================================================
# 等价性胶水 (embedded vs Neo4j, 不可达自动 skip)
# ============================================================

def _neo4j_store():
    try:
        from app.graph.engine import KnowledgeGraph
        kg = KnowledgeGraph.from_settings(embedding_client=None)
        if not kg.test_connection():
            kg.close()
            pytest.skip("Neo4j 不可达, 等价性胶水跳过")
        # 要求库里有数据 (未导入则跳过)
        probe = kg.get_by_difficulty(1, 1)
        if not probe:
            kg.close()
            pytest.skip("Neo4j 空库 (未导入数据), 等价性胶水跳过")
        return kg
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"Neo4j 不可用: {e}")


def _norm_ids(items):
    return [n["node_id"] for n in items]


def test_parity_basic_queries(real_store):
    """同数据下 get_node / 前置 / 题目 抽验一致。"""
    kg = _neo4j_store()

    # 取一个难度1节点做锚点
    anchor = real_store.get_by_difficulty(1, 1)[0]["node_id"]
    nid = anchor if kg.get_node(anchor) else kg.get_by_difficulty(1, 1)[0]["node_id"]

    # 节点形状: node_id 归一 + practice_questions 字符串 + 无 prerequisites 属性
    en, nn = real_store.get_node(nid), kg.get_node(nid)
    assert en["node_id"] == nn["node_id"] == nid
    assert isinstance(en["practice_questions"], str) == isinstance(nn["practice_questions"], str)

    # 前置依赖 id 集合一致
    assert _norm_ids(real_store.get_prerequisites(nid)) == _norm_ids(kg.get_prerequisites(nid))

    # 题目配额 (每节点 ≤2) id 集一致
    eq = {q["qid"] for q in real_store.get_questions_for_nodes([nid], max_per_node=2)}
    nq = {q["qid"] for q in kg.get_questions_for_nodes([nid], max_per_node=2)}
    assert eq == nq

    kg.close()


def test_parity_learning_path(real_store):
    """assemble_learning_path 结果一致 (M5 口径锚点)。"""
    kg = _neo4j_store()
    anchor = real_store.get_by_difficulty(1, 1)[0]["node_id"]
    weak = real_store.get_dependents(anchor)
    weak_ids = [w["node_id"] for w in weak[:2]] if weak else []

    e_path = _norm_ids(real_store.assemble_learning_path([anchor], weak_ids, level=2, max_nodes=20))
    n_path = _norm_ids(kg.assemble_learning_path([anchor], weak_ids, level=2, max_nodes=20))
    assert e_path == n_path
    kg.close()
