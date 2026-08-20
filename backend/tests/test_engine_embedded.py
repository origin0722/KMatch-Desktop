"""嵌入式图存储后端 (EmbeddedGraphStore) 单测 — 端用户免 Docker 核心。

覆盖: 只读查询/图遍历/题目/路径组装/项目图谱/状态/向量语义(载入+降级)/KB 同步刷新。
不碰真实 data/knowledge_base (tmp_path 隔离)。
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.graph.embedded import EmbeddedGraphStore


# ============================================================
# 夹具: 合成迷你知识库
# ============================================================

_NODES = [
    {"id": "PY-001", "name": "变量与类型", "difficulty": 1, "category": "基础语法",
     "summary": "变量与基本类型", "prerequisites": [], "key_points": ["a"],
     "practice_questions": [{"question": "x"}], "common_mistakes": [], "tags": ["基础", "变量"],
     "estimated_minutes": 10},
    {"id": "PY-002", "name": "函数", "difficulty": 2, "category": "基础语法",
     "summary": "函数定义与调用", "prerequisites": ["PY-001"], "key_points": ["b"],
     "practice_questions": [], "common_mistakes": [], "tags": ["函数"],
     "estimated_minutes": 20},
    {"id": "PY-003", "name": "迭代器", "difficulty": 3, "category": "Python进阶",
     "summary": "迭代器协议", "prerequisites": ["PY-002"], "key_points": [],
     "practice_questions": [], "common_mistakes": [], "tags": ["进阶", "迭代"],
     "estimated_minutes": 25},
    {"id": "PY-004", "name": "类", "difficulty": 2, "category": "面向对象编程",
     "summary": "类与对象", "prerequisites": ["PY-001", "PY-002"], "key_points": [],
     "practice_questions": [], "common_mistakes": [], "tags": ["类"],
     "estimated_minutes": 20},
    {"id": "PY-005", "name": "装饰器", "difficulty": 4, "category": "Python进阶",
     "summary": "装饰器原理", "prerequisites": ["PY-004"], "key_points": [],
     "practice_questions": [], "common_mistakes": [], "tags": ["进阶"],
     "estimated_minutes": 30},
]

_QUESTIONS = [
    {"qid": "Q-PY001-001", "source_node_id": "PY-001", "type": "choice",
     "question": "q1", "options": ["A", "B"], "answer": "A", "difficulty": 1,
     "hint": "", "explanation": "e"},
    {"qid": "Q-PY001-002", "source_node_id": "PY-001", "type": "fill",
     "question": "q2", "options": [], "answer": "x", "difficulty": 2,
     "hint": "", "explanation": "e"},
    {"qid": "Q-PY002-001", "source_node_id": "PY-002", "type": "choice",
     "question": "q3", "options": ["C"], "answer": "C", "difficulty": 1,
     "hint": "", "explanation": "e"},
]


@pytest.fixture
def kb(tmp_path: Path) -> Path:
    base = tmp_path / "knowledge_base"
    (base / "nodes").mkdir(parents=True)
    (base / "questions").mkdir()
    (base / "nodes" / "py.json").write_text(
        json.dumps(_NODES, ensure_ascii=False), encoding="utf-8")
    (base / "questions" / "PY-001.json").write_text(
        json.dumps([_QUESTIONS[0], _QUESTIONS[1]], ensure_ascii=False), encoding="utf-8")
    (base / "questions" / "PY-002.json").write_text(
        json.dumps([_QUESTIONS[2]], ensure_ascii=False), encoding="utf-8")
    return base


@pytest.fixture
def store(kb: Path, tmp_path: Path) -> EmbeddedGraphStore:
    return EmbeddedGraphStore(kb_dir=kb, local_dir=tmp_path / "local", embedding_client=None)


# ============================================================
# P1 只读: 形状契约 + 查询 + 遍历
# ============================================================

def test_get_node_shape(store):
    """镜像 Neo4j 输出: node_id 归一, 不注入 prerequisites, practice_questions 为 JSON 字符串。"""
    n = store.get_node("PY-001")
    assert n["node_id"] == "PY-001"
    assert "id" not in n
    assert "prerequisites" not in n          # 前置以边不注入返回
    assert isinstance(n["practice_questions"], str)  # Neo4j 落 JSON 字符串
    assert json.loads(n["practice_questions"])[0]["question"] == "x"
    assert n["difficulty"] == 1
    assert store.get_node("GHOST") is None


def test_get_by_category_difficulty_tags(store):
    cats = store.get_by_category("基础语法")
    assert [n["node_id"] for n in cats] == ["PY-001", "PY-002"]  # 难度升序

    diffs = store.get_by_difficulty(2, 3)
    assert {n["node_id"] for n in diffs} == {"PY-002", "PY-003", "PY-004"}

    tags = store.get_by_tags(["进阶"])
    assert {n["node_id"] for n in tags} == {"PY-003", "PY-005"}


def test_traversal(store):
    prereq = store.get_prerequisites("PY-004")
    assert [n["node_id"] for n in prereq] == ["PY-001", "PY-002"]  # 难度升序

    deps = store.get_dependents("PY-001")
    assert {n["node_id"] for n in deps} == {"PY-002", "PY-004"}

    reach = store.get_reachable(["PY-001"], max_depth=2)
    assert {n["node_id"] for n in reach} == {"PY-002", "PY-003", "PY-004", "PY-005"}
    # 难度升序: PY-002(2)==PY-004(2), PY-003(3), PY-005(4)
    assert [n["node_id"] for n in reach[-2:]] == ["PY-003", "PY-005"]
    assert store.get_reachable([], 3) == []


def test_questions(store):
    qs = store.get_questions("PY-001", types=["choice"], limit=1)
    assert [q["qid"] for q in qs] == ["Q-PY001-001"]
    assert qs[0]["node_id"] == "PY-001"      # node_id=source_node_id 注入
    assert qs[0]["options"] == ["A", "B"]    # options list 保持

    quota = store.get_questions_for_nodes(["PY-001", "PY-002"], types=["choice"], max_per_node=1)
    assert {q["qid"] for q in quota} == {"Q-PY001-001", "Q-PY002-001"}

    assert store.get_question("Q-PY001-002")["type"] == "fill"
    assert store.get_question("GHOST") is None
    assert {q["qid"] for q in store.get_questions_by_node("PY-001")} == {
        "Q-PY001-001", "Q-PY001-002"}


# ============================================================
# P2 路径组装
# ============================================================

def test_assemble_zero_base(store):
    path = store.assemble_learning_path([], [], level=1, max_nodes=20)
    assert [n["node_id"] for n in path] == ["PY-001"]  # 仅难度 1 入口
    assert all(n["difficulty"] <= 1 for n in path)


def test_assemble_weak_patch(store):
    path = store.assemble_learning_path([], weak_ids=["PY-004"], level=2, max_nodes=20)
    ids = [n["node_id"] for n in path]
    assert "PY-004" in ids           # 弱项本身入路径 (M5 覆盖率锚点)
    assert "PY-001" in ids           # 前置依赖已就位
    assert all(n["difficulty"] <= 4 for n in path)  # difficulty_cap = min(5, level+2)


def test_assemble_from_known(store):
    path = store.assemble_learning_path(["PY-001"], [], level=2, max_nodes=20)
    ids = [n["node_id"] for n in path]
    assert "PY-001" not in ids       # 已掌握过滤
    assert "PY-002" in ids           # BFS 后继


# ============================================================
# P3 可变数据: 项目图谱 / 状态 / KB 同步
# ============================================================

def _entity(eid, kind, name, layer=2):
    return {"entity_id": eid, "kind": kind, "name": name, "layer": layer,
            "params": [{"name": "x"}], "external_calls": [["print"]], "line_start": 1}


def _rel(typ, src, tgt, line=None, resolved=None):
    r = SimpleNamespace(type=typ, source=src, target=tgt)
    if line is not None:
        r.line = line
        r.resolved = resolved
    return r


def test_project_graph_roundtrip(store):
    store.write_project_graph(
        "p1",
        [_entity("m1", "module", "mod", 2), _entity("f1", "function", "func", 3)],
        [_rel("CONTAINS", "m1", "f1"), _rel("CALLS", "f1", "m1", line=5, resolved=True)],
    )
    # 幂等重写不残留
    store.write_project_graph(
        "p1",
        [_entity("m1", "module", "mod", 2), _entity("f1", "function", "func", 3)],
        [_rel("CONTAINS", "m1", "f1"), _rel("CALLS", "f1", "m1", line=5, resolved=True)],
    )
    g = store.get_project_graph("p1")
    assert g["project_id"] == "p1"
    assert {n["id"] for n in g["nodes"]} == {"m1", "f1"}
    node = next(n for n in g["nodes"] if n["id"] == "m1")
    assert node["group"] == "module"
    assert node["properties"]["params"] == [{"name": "x"}]   # JSON 字符串还原
    call = next(e for e in g["edges"] if e["label"] == "CALLS")
    assert call["line"] == 5 and call["resolved"] is True

    # 风险标注 + 关联知识点
    store.annotate_risk("f1", "high", "未处理异常")
    store.link_entity_to_knowledge("f1", "PY-002")
    g = store.get_project_graph("p1")
    fnode = next(n for n in g["nodes"] if n["id"] == "f1")
    assert fnode["properties"]["risk_level"] == "high"
    assert "PY-002" in fnode["properties"]["related_to"]

    assert store.delete_project_graph("p1") == 2
    assert store.get_project_graph("p1") is None
    assert store.delete_project_graph("p1") == 0


def test_status_persist(store):
    store.update_node_status("PY-001", "mastered")
    assert store.get_node_status("PY-001") == "mastered"
    with pytest.raises(ValueError):
        store.update_node_status("PY-001", "hacked")
    # 新实例读回一致
    s2 = EmbeddedGraphStore(kb_dir=store.kb_dir, local_dir=store.local_dir)
    assert s2.get_node_status("PY-001") == "mastered"
    assert s2.get_node_status("PY-002") is None


def test_status_second_write_no_deadlock(store):
    """回归: 状态文件已存在时的第二次写 — 曾因 _read_status 与 update_node_status
    嵌套获取同一非可重入锁而自锁死锁 (PUT /status 超时), 现应秒回。"""
    store.update_node_status("PY-001", "mastered")      # 首写: 建文件
    store.update_node_status("PY-002", "in_progress")   # 二写: 文件已存在 (曾死锁)
    assert store.get_node_status("PY-001") == "mastered"
    assert store.get_node_status("PY-002") == "in_progress"


def test_kb_sync_refresh(store):
    # 新增节点: JSON 已写 → upsert 刷新内存
    store.upsert_knowledge_node({
        "id": "PY-099", "name": "新概念", "difficulty": 1, "category": "基础语法",
        "summary": "", "prerequisites": ["PY-001"], "key_points": [],
        "practice_questions": [], "common_mistakes": [], "tags": ["新"], "estimated_minutes": 5,
    })
    n = store.get_node("PY-099")
    assert n is not None and n["name"] == "新概念"
    assert "PY-099" in {x["node_id"] for x in store.get_dependents("PY-001")}

    assert store.delete_knowledge_node("PY-099") == 1
    assert store.get_node("PY-099") is None
    assert "PY-099" not in {x["node_id"] for x in store.get_dependents("PY-001")}
    assert store.delete_knowledge_node("PY-099") == 0


# ============================================================
# P4 向量语义: 载入 + 余弦 + 降级
# ============================================================

class _FakeEmbeddingClient:
    """模拟 openai 客户端: client.embeddings.create(...) → data[0].embedding。"""

    def __init__(self, vec):
        self.embeddings = _FakeEmbeddings(vec)


class _FakeEmbeddings:
    def __init__(self, vec):
        self._vec = vec

    def create(self, model, input):
        return _EmbResp(self._vec)


class _EmbResp:
    def __init__(self, vec):
        self.data = [_EmbDatum(vec)]


class _EmbDatum:
    def __init__(self, vec):
        self.embedding = vec


def test_semantic_search_with_cached_vectors(kb: Path, tmp_path: Path):
    # 预置 3 维向量缓存: PY-001=[1,0,0], PY-002=[0,1,0], PY-005=[0,0,1]
    local = tmp_path / "local"
    local.mkdir(parents=True)
    (local / "embeddings.json").write_text(json.dumps({
        "model": "t", "items": {
            "PY-001": [1.0, 0.0, 0.0],
            "PY-002": [0.0, 1.0, 0.0],
            "PY-005": [0.0, 0.0, 1.0],
        }}, ensure_ascii=False), encoding="utf-8")
    client = _FakeEmbeddingClient([0.9, 0.3, 0.0])  # 最近: PY-001
    s = EmbeddedGraphStore(kb_dir=kb, local_dir=local, embedding_client=client)
    assert s.semantic_ready is True
    res = s.semantic_search("靠近变量的查询", top_k=3)
    assert res[0]["node_id"] == "PY-001"
    assert res[0]["_similarity"] > res[1]["_similarity"]
    # difficulty_max 过滤: 仅保留难度 1 的 PY-001
    filtered = s.semantic_search("q", top_k=3, difficulty_max=1)
    assert [n["node_id"] for n in filtered] == ["PY-001"]


def test_semantic_degraded_no_client(store):
    assert store.semantic_ready is False      # 无客户端
    assert store.semantic_search("anything") == []


def test_semantic_degraded_no_vectors(kb: Path, tmp_path: Path):
    client = _FakeEmbeddingClient([1.0, 0.0, 0.0])
    s = EmbeddedGraphStore(kb_dir=kb, local_dir=tmp_path / "local", embedding_client=client)
    assert s.semantic_search("q", top_k=3) == []   # 无本地向量 → 降级


def test_hybrid_graph_only(store):
    """无语义向量时 hybrid 降级为纯图检索, 不抛错。"""
    res = store.hybrid_retrieve(known_ids=["PY-001"], weak_ids=["PY-004"], top_k=10)
    assert res and all(n["_source"] == "graph" for n in res)
    assert all(n["node_id"] not in {"PY-001"} for n in res)


def test_questions_nested_domain_dirs(kb: Path, tmp_path: Path):
    """真实题库含嵌套子目录 (questions/DA/ 等, 见 import_knowledge_base.rglob)。

    回归: 旧实现只扫顶层 glob('*.json') → 嵌套域题目漏载 → 该域「题库为空」。
    """
    nested = kb / "questions" / "DA"
    nested.mkdir()
    (nested / "Q-DA001-001.json").write_text(json.dumps([
        {"qid": "Q-DA001-001", "source_node_id": "DA-001", "type": "choice",
         "question": "嵌套域题目", "options": ["A"], "answer": "A", "difficulty": 1,
         "hint": "", "explanation": "e"}], ensure_ascii=False), encoding="utf-8")
    s = EmbeddedGraphStore(kb_dir=kb, local_dir=tmp_path / "local2", embedding_client=None)
    q = s.get_question("Q-DA001-001")
    assert q is not None and q["node_id"] == "DA-001"
    assert {x["qid"] for x in s.get_questions_by_node("DA-001")} == {"Q-DA001-001"}
    assert {x["qid"] for x in s.get_questions_for_nodes(["DA-001"], max_per_node=1)} == {"Q-DA001-001"}
