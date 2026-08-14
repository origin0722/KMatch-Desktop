"""动态建域 Agent 单测 — 域判定 resolve_direction + 建域 bootstrap_domain + API 接线。

不碰真实 data/knowledge_base (tmp_path 隔离 + 真 schema.json 副本)、不碰 LLM
(按 system prompt 内容分发固定响应的 FakeModel)、不碰 Neo4j (_RecordingKG)。
"""

import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agents import domain_bootstrap as db
from app.api import diagnostics as diag_api

_REPO_SCHEMA = Path(__file__).resolve().parent.parent.parent / "data" / "knowledge_base" / "schema.json"


# ============================================================
# 夹具: 隔离知识库 + FakeModel + RecordingKG
# ============================================================

@pytest.fixture
def kb_base(tmp_path):
    base = tmp_path / "knowledge_base"
    (base / "nodes").mkdir(parents=True)
    (base / "questions").mkdir()
    shutil.copy(_REPO_SCHEMA, base / "schema.json")
    return base


class _FakeModel:
    """按 system prompt 内容分发固定响应 (避免并发 pop 顺序不确定)。"""

    def __init__(self, spec_json, questions_json, classify_json=None):
        self.spec_json = spec_json
        self.questions_json = questions_json
        self.classify_json = classify_json or '{"domain": "new"}'
        self.invoke_count = 0

    def invoke(self, messages):
        self.invoke_count += 1
        system = str(messages[0].content)
        if "动态建域 Agent" in system:
            content = self.spec_json
        elif "出题 Agent" in system:
            content = self.questions_json
        elif "领域分类器" in system:
            content = self.classify_json
        else:
            raise AssertionError(f"未预期的 prompt: {system[:40]}")
        return SimpleNamespace(content=content)


class _RecordingKG:
    def __init__(self):
        self.upserted_nodes = []
        self.upserted_questions = []
        self.embedded_nodes = None

    def upsert_knowledge_node(self, node):
        self.upserted_nodes.append(node)

    def upsert_question(self, q):
        self.upserted_questions.append(q)

    def generate_embeddings(self, nodes, batch_size=20):
        self.embedded_nodes = nodes


def _spec_dict(n=6, prefix="JV", domain="Java"):
    nodes = []
    for i in range(n):
        nodes.append({
            "name": f"概念{i + 1}",
            "difficulty": min(3, i + 1),
            "summary": f"这是关于{domain}概念{i + 1}的概要说明，包含核心思想、适用场景与"
                       "基本用法的两到三句话描述，长度超过三十个字符以满足校验要求。",
            "key_points": ["要点一", "要点二", "要点三"],
            "common_mistakes": ["把概念混淆"],
            "tags": [domain],
            "estimated_minutes": 40,
            # 仅引用更早节点 (概念3 → 概念2); 概念2 故意引用靠后的概念5 测丢弃
            "prerequisite_names": [f"概念{i}"] + ([f"概念{i + 3}"] if i == 2 else []),
        })
    return {"domain_name": domain, "prefix": prefix, "nodes": nodes}


def _questions_json_for(node_ids):
    """全节点 2 题 choice/fill (每批响应都返回全集, 逐批过滤后截断到 2)。"""
    qs = []
    for nid in node_ids:
        qs.append({"node_id": nid, "type": "choice", "question": f"{nid} 选择题",
                   "options": ["A. x", "B. y", "C. z", "D. w"], "answer": "A",
                   "difficulty": 2, "explanation": "基础概念"})
        qs.append({"node_id": nid, "type": "fill", "question": f"{nid} 填空题",
                   "answer": "值", "difficulty": 1, "explanation": "基础概念"})
    return json.dumps(qs, ensure_ascii=False)


@pytest.fixture
def wired(kb_base, monkeypatch):
    """domain_bootstrap 模块接线到隔离 KB + FakeModel + RecordingKG。"""
    monkeypatch.setattr(db, "_kb_base", lambda: kb_base)
    kg = _RecordingKG()
    return SimpleNamespace(base=kb_base, kg=kg, monkeypatch=monkeypatch)


# ============================================================
# resolve_direction — 域命中判定
# ============================================================

def test_resolve_miss_when_llm_says_new(wired, monkeypatch):
    monkeypatch.setattr(db, "llm_configured", lambda: True)
    monkeypatch.setattr(db, "_classify_domain", lambda t, r: ("new", None))
    resolution, nodes = db.resolve_direction(wired.kg, "Rust 系统编程", [])
    assert resolution == "miss" and nodes == []


def test_resolve_hit_filters_known_and_semantic_first(wired, monkeypatch):
    monkeypatch.setattr(db, "llm_configured", lambda: True)
    monkeypatch.setattr(db, "_classify_domain", lambda t, r: ("known", "PY"))
    kg = MagicMock()
    kg.semantic_search.return_value = [
        {"node_id": "PY-001", "name": "a", "_similarity": 0.9},
        {"node_id": "PY-002", "name": "b", "_similarity": 0.8},
        {"node_id": "PY-003", "name": "c", "_similarity": 0.7},
        {"node_id": "ML-001", "name": "x", "_similarity": 0.95},  # 异域节点被前缀过滤
    ]
    resolution, nodes = db.resolve_direction(
        kg, "Python 入门", [{"node_id": "PY-002", "mastery": 1.0}])
    assert resolution == "hit"
    ids = [n["node_id"] for n in nodes]
    assert "ML-001" not in ids and "PY-002" not in ids  # 前缀过滤 + 已会剔除
    assert ids == ["PY-001", "PY-003"]


def test_resolve_hit_falls_back_to_difficulty_when_semantic_thin(wired, monkeypatch):
    monkeypatch.setattr(db, "llm_configured", lambda: True)
    monkeypatch.setattr(db, "_classify_domain", lambda t, r: ("known", "DA"))
    kg = MagicMock()
    kg.semantic_search.return_value = []  # 语义检索空 → 难度入口兜底
    kg.get_by_difficulty.return_value = [
        {"node_id": f"DA-{i:03d}", "name": f"n{i}", "difficulty": 1} for i in range(1, 9)
    ] + [{"node_id": "PY-001", "name": "py", "difficulty": 1}]
    resolution, nodes = db.resolve_direction(kg, "数据分析", [])
    assert resolution == "hit"
    assert all(n["node_id"].startswith("DA-") for n in nodes)


def test_resolve_vector_fallback_when_llm_invalid(wired, monkeypatch):
    """LLM 分类失败 → 向量启发式: 最高分过阈值视为命中。"""
    monkeypatch.setattr(db, "llm_configured", lambda: True)
    monkeypatch.setattr(db, "_classify_domain", lambda t, r: ("invalid", None))
    kg = MagicMock()
    kg.embedding_client = object()
    kg.semantic_search.return_value = [
        {"node_id": "PY-001", "_similarity": 0.72}, {"node_id": "PY-002", "_similarity": 0.6},
    ]
    resolution, nodes = db.resolve_direction(kg, "Python", [])
    assert resolution == "hit" and len(nodes) == 2


def test_resolve_vector_below_threshold_is_miss(wired, monkeypatch):
    monkeypatch.setattr(db, "llm_configured", lambda: False)
    kg = MagicMock()
    kg.embedding_client = object()
    kg.semantic_search.return_value = [{"node_id": "PY-001", "_similarity": 0.31}]
    resolution, nodes = db.resolve_direction(kg, "Rust", [])
    assert resolution == "miss" and nodes == []


def test_resolve_unknown_when_no_llm_no_vector(wired, monkeypatch):
    monkeypatch.setattr(db, "llm_configured", lambda: False)
    kg = MagicMock()
    kg.embedding_client = None
    assert db.resolve_direction(kg, "任意", []) == ("unknown", [])


def test_dynamic_domain_reused_after_bootstrap(wired, monkeypatch):
    """建域后 domain_registry 收录动态域 → 二次同域学习可命中复用。"""
    monkeypatch.setattr(db, "llm_configured", lambda: True)
    spec = _spec_dict()
    node_ids = [f"JV-{i:03d}" for i in range(1, 7)]
    model = _FakeModel(json.dumps(spec, ensure_ascii=False),
                       _questions_json_for(node_ids))
    monkeypatch.setattr(db, "get_default_chat_model", lambda: model)
    monkeypatch.setattr(db, "_search_context", lambda d, k: "")
    db.bootstrap_domain(wired.kg, "Java")

    registry = db.domain_registry(wired.base)
    assert "JV" in registry and registry["JV"] == "Java"

    monkeypatch.setattr(db, "_classify_domain", lambda t, r: ("known", "JV"))
    kg = MagicMock()
    kg.semantic_search.return_value = []
    kg.get_by_difficulty.return_value = [
        {"node_id": f"JV-{i:03d}", "name": f"j{i}", "difficulty": 1} for i in range(1, 7)
    ]
    resolution, nodes = db.resolve_direction(kg, "Java 入门", [])
    assert resolution == "hit"
    assert all(n["node_id"].startswith("JV-") for n in nodes)


# ============================================================
# bootstrap_domain — 生成 → 校验 → 落库
# ============================================================

def test_bootstrap_happy_path_persists_and_marks(wired, monkeypatch):
    spec = _spec_dict()
    monkeypatch.setattr(db, "llm_configured", lambda: True)
    monkeypatch.setattr(db, "_search_context", lambda d, k: "[Java 教程] JVM 基础……")
    # FakeModel 需先知道运行时分配的 id — 预生成期望 id (隔离 KB 前缀空闲 → JV-001..006)
    node_ids = [f"JV-{i:03d}" for i in range(1, 7)]
    model = _FakeModel(
        json.dumps(spec, ensure_ascii=False), _questions_json_for(node_ids))
    monkeypatch.setattr(db, "get_default_chat_model", lambda: model)

    nodes = db.bootstrap_domain(wired.kg, "Java")

    # 返回: 学习顺序节点 + 动态域标记
    assert [n["id"] for n in nodes] == node_ids
    assert all(n["source"] == "llm_generated" and n["domain_label"] == "Java"
               and n["category"] == db.DYNAMIC_CATEGORY for n in nodes)
    # 前置: 概念1 无前置 (概念0 不存在被丢); 概念2→JV-001; 概念3 仅保留更早引用 JV-002,
    # 靠后引用 概念5 被丢弃 (防环)
    assert nodes[0]["prerequisites"] == []
    assert nodes[1]["prerequisites"] == ["JV-001"]
    assert nodes[2]["prerequisites"] == ["JV-002"]
    # practice_questions 注入 (schema 必填 ≥1)
    assert all(n["practice_questions"] for n in nodes)

    # JSON 真相源落盘: 手动节点文件 + 每节点题目文件
    manual = wired.base / "nodes" / "_manual_nodes.json"
    assert manual.is_file()
    saved = json.loads(manual.read_text(encoding="utf-8"))
    assert {n["id"] for n in saved} == set(node_ids)
    for nid in node_ids:
        qfile = wired.base / "questions" / f"{nid}.json"
        assert qfile.is_file(), f"缺题目文件 {qfile}"
        saved_q = json.loads(qfile.read_text(encoding="utf-8"))
        assert len(saved_q) == 2
        assert saved_q[0]["qid"] == f"Q-JV{nid[-3:]}-001"
        assert saved_q[0]["source_node_id"] == nid

    # Neo4j 同步: 节点 N 次 + 题目 2N 次 + embedding 批量 1 次
    assert len(wired.kg.upserted_nodes) == 6
    assert len(wired.kg.upserted_questions) == 12
    assert wired.kg.embedded_nodes is not None and len(wired.kg.embedded_nodes) == 6


def test_bootstrap_allocates_free_prefix_on_collision(wired, monkeypatch):
    """提案前缀与内置域冲突 → 从领域名推导 (Java→JA)。"""
    spec = _spec_dict(prefix="PY", domain="Java")
    monkeypatch.setattr(db, "llm_configured", lambda: True)
    monkeypatch.setattr(db, "_search_context", lambda d, k: "")
    node_ids = [f"JA-{i:03d}" for i in range(1, 7)]
    model = _FakeModel(
        json.dumps(spec, ensure_ascii=False), _questions_json_for(node_ids))
    monkeypatch.setattr(db, "get_default_chat_model", lambda: model)

    nodes = db.bootstrap_domain(wired.kg, "Java")
    assert all(n["id"].startswith("JA-") for n in nodes)


def test_bootstrap_retries_then_raises_on_persistently_bad_spec(wired, monkeypatch):
    monkeypatch.setattr(db, "llm_configured", lambda: True)
    monkeypatch.setattr(db, "_search_context", lambda d, k: "")
    bad = json.dumps({"domain_name": "X", "prefix": "XX", "nodes": [{"name": "只有一节点"}]})
    model = _FakeModel(bad, "[]")
    monkeypatch.setattr(db, "get_default_chat_model", lambda: model)

    with pytest.raises(ValueError, match="动态建域失败"):
        db.bootstrap_domain(wired.kg, "冷门领域")
    assert model.invoke_count == 2  # 2 轮各 1 次蓝图 (nodes 不足短路, 不进出题)


def test_bootstrap_requires_llm(wired, monkeypatch):
    monkeypatch.setattr(db, "llm_configured", lambda: False)
    with pytest.raises(ValueError, match="LLM 未配置"):
        db.bootstrap_domain(wired.kg, "Go")


def test_bootstrap_question_validation_failure_retries(wired, monkeypatch):
    """题目缺 answer → 校验失败整轮作废, 第二轮给合法产物成功。"""
    monkeypatch.setattr(db, "llm_configured", lambda: True)
    monkeypatch.setattr(db, "_search_context", lambda d, k: "")
    node_ids = [f"JV-{i:03d}" for i in range(1, 7)]
    bad_qs = json.dumps([
        {"node_id": nid, "type": "fill", "question": "缺答案", "difficulty": 1}
        for nid in node_ids], ensure_ascii=False)
    spec = json.dumps(_spec_dict(), ensure_ascii=False)
    good = _FakeModel(spec, _questions_json_for(node_ids))

    state = {"model": _FakeModel(spec, bad_qs)}

    def _switch_model():
        state["model"] = good
    # 第一轮坏题目 → _finalize 报错; 切好模型后第二轮成功
    orig_finalize = db._finalize_nodes_and_questions
    calls = {"n": 0}

    def spy_finalize(nodes, qmap):
        calls["n"] += 1
        result = orig_finalize(nodes, qmap)
        if calls["n"] == 1:
            _switch_model()
        return result

    monkeypatch.setattr(db, "_finalize_nodes_and_questions", spy_finalize)
    monkeypatch.setattr(db, "get_default_chat_model", lambda: state["model"])

    nodes = db.bootstrap_domain(wired.kg, "Java")
    assert len(nodes) == 6 and calls["n"] == 2


def test_bootstrap_nodes_carry_node_id_for_submit_path(wired, monkeypatch):
    """回归 (CSS 会话实测 BUG): 建域返回节点须含 node_id — submit 的
    _build_profile 直接取 n["node_id"], id-only 形状 KeyError → 500,
    画像/知识图谱全断。"""
    monkeypatch.setattr(db, "llm_configured", lambda: True)
    monkeypatch.setattr(db, "_search_context", lambda d, k: "")
    node_ids = [f"JV-{i:03d}" for i in range(1, 7)]
    model = _FakeModel(json.dumps(_spec_dict(), ensure_ascii=False),
                       _questions_json_for(node_ids))
    monkeypatch.setattr(db, "get_default_chat_model", lambda: model)

    nodes = db.bootstrap_domain(wired.kg, "Java")
    assert all(n.get("node_id") == n["id"] for n in nodes)

    # 走真 _build_profile (不走 mock): 不抛 KeyError 且画像含节点分级
    from app.agents.diagnostics import _build_profile
    grading = {"per_node": {}, "correct_count": 0, "total_count": 6}
    questions = []
    for i, nid in enumerate(node_ids):
        grading["per_node"][nid] = [{"question_index": i, "correct": i % 2 == 0}]
        questions.append({"node_id": nid, "question": f"q{i}", "type": "choice"})
    profile = _build_profile("Java 入门", nodes, grading, questions=questions)
    graded = len(profile["known_topics"]) + len(profile["weak_topics"])
    assert graded == 6
    # search_weak_topics 的 node_map 同样按 node_id 建键
    node_map = {n.get("node_id"): n for n in nodes}
    assert None not in node_map and len(node_map) == 6


# ============================================================
# API 接线 — /assess interactive
# ============================================================

def _api_app(monkeypatch, resolution, bootstrap_result=None, llm_on=True):
    diag_api._INTERACTIVE_SESSIONS.clear()
    monkeypatch.setattr(
        diag_api, "resolve_direction",
        lambda kg, target, known: (resolution, bootstrap_result or []),
    )
    if bootstrap_result is not None:
        monkeypatch.setattr(
            diag_api, "bootstrap_domain",
            lambda kg, direction, tavily_key=None: bootstrap_result,
        )
    monkeypatch.setattr(diag_api, "llm_configured", lambda: llm_on)
    captured = {}

    def _prepare(kg, target, known, nodes=None, seed=None):
        captured["nodes"] = nodes
        return ([{"node_id": "JV-001", "question": "q", "answer": "A", "type": "choice",
                  "difficulty": 2, "explanation": "e"}],
                nodes or [{"node_id": "JV-001", "name": "n", "difficulty": 2}])

    monkeypatch.setattr(diag_api, "prepare_questions", _prepare)
    app = FastAPI()
    app.state.kg = MagicMock()
    app.include_router(diag_api.router, prefix="/api/diagnostics")
    return TestClient(app), captured


def test_assess_miss_triggers_bootstrap_and_uses_new_nodes(monkeypatch):
    new_nodes = [{"id": "JV-001", "name": "n", "difficulty": 2}]
    client, captured = _api_app(monkeypatch, "miss", bootstrap_result=new_nodes)
    resp = client.post("/api/diagnostics/assess", json={
        "target_direction": "Java 入门", "mode": "interactive"})
    assert resp.status_code == 200, resp.text
    assert captured["nodes"] == new_nodes  # 新域节点直接作为出题候选
    data = resp.json()
    assert len(data["assessment"]["questions"]) == 1
    assert "answer" not in data["assessment"]["questions"][0]  # BUG-033 剥离答案


def test_assess_hit_passes_direction_nodes(monkeypatch):
    dir_nodes = [{"node_id": "PY-003", "name": "n", "difficulty": 1}]
    client, captured = _api_app(monkeypatch, "hit", bootstrap_result=None)
    # hit 路径不走 bootstrap_result; 单独设 hit 节点
    monkeypatch.setattr(
        diag_api, "resolve_direction", lambda kg, t, k: ("hit", dir_nodes))
    resp = client.post("/api/diagnostics/assess", json={
        "target_direction": "Python 入门", "mode": "interactive"})
    assert resp.status_code == 200
    assert captured["nodes"] == dir_nodes


def test_assess_miss_without_llm_returns_503(monkeypatch):
    client, _ = _api_app(monkeypatch, "miss", bootstrap_result=None, llm_on=False)
    resp = client.post("/api/diagnostics/assess", json={
        "target_direction": "Rust 系统编程", "mode": "interactive"})
    assert resp.status_code == 503
    assert "暂未收录" in resp.json()["detail"]


def test_assess_unknown_falls_back_to_legacy(monkeypatch):
    client, captured = _api_app(monkeypatch, "unknown")
    resp = client.post("/api/diagnostics/assess", json={
        "target_direction": "Python", "mode": "interactive"})
    assert resp.status_code == 200
    assert captured["nodes"] is None  # 未传 nodes → prepare_questions 内部旧选点
