"""知识库管理 API 集成测试 — TestClient + _FakeKG + tmp_path 隔离知识库。

覆盖节点/题目 CRUD 全端点: 创建/查询/更新/删除/校验失败/404/409/
ID自动生成/cascade删除/Neo4j同步warning。不碰真实 data/knowledge_base。
"""

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import kb as kb_api
from app.data import kb_store


# ============================================================
# 测试夹具: 隔离知识库 + fake kg
# ============================================================

def _make_base(tmp_path):
    base = tmp_path / "knowledge_base"
    (base / "nodes").mkdir(parents=True)
    (base / "questions").mkdir()
    # schema.json (节点结构, 含 category enum 供 validate_node)
    (base / "schema.json").write_text(json.dumps({
        "required": ["id", "name", "difficulty", "category", "summary",
                     "prerequisites", "key_points", "practice_questions"],
        "properties": {
            "id": {"pattern": r"^[A-Z]{2}-\d{3}$"},
            "category": {"enum": ["基础语法", "数据结构与算法", "面向对象编程",
                                  "Python进阶", "常用库与工具", "项目实战"]},
        }
    }, ensure_ascii=False), encoding="utf-8")
    # 注意: 上面的 pattern 字符串在 JSON 里 \\d 会被解析为 \d
    (base / "questions" / "schema.json").write_text('{"title": "题目规范"}', encoding="utf-8")
    return base


class _FakeKG:
    """记录 CRUD 同步调用的 fake KnowledgeGraph。可注入失败。"""

    def __init__(self):
        self.nodes = {}          # node_id → node (upsert 记录)
        self.questions = {}      # qid → question
        self.fail_on_upsert_node = False
        self.fail_on_upsert_question = False

    def upsert_knowledge_node(self, node):
        if self.fail_on_upsert_node:
            raise RuntimeError("模拟 Neo4j 故障")
        self.nodes[node["id"]] = node

    def delete_knowledge_node(self, node_id):
        return 1 if self.nodes.pop(node_id, None) is not None else 0

    def get_node(self, node_id):
        return self.nodes.get(node_id)

    def upsert_question(self, q):
        if self.fail_on_upsert_question:
            raise RuntimeError("模拟 Neo4j 故障")
        self.questions[q["qid"]] = q

    def delete_question(self, qid):
        return 1 if self.questions.pop(qid, None) is not None else 0

    def get_question(self, qid):
        return self.questions.get(qid)

    def get_questions_by_node(self, node_id):
        return [q for q in self.questions.values() if q.get("source_node_id") == node_id]

    def generate_embeddings(self, nodes):
        pass  # no-op


@pytest.fixture
def app(tmp_path, monkeypatch):
    base = _make_base(tmp_path)
    # 隔离: 把 kb_api 和 kb_store 的 base 指向 tmp
    monkeypatch.setattr(kb_api, "KB_BASE", base)
    kg = _FakeKG()
    app = FastAPI()
    app.state.kg = kg
    app.include_router(kb_api.router, prefix="/api/kb")
    app.state._fake_kg = kg  # 供测试取
    return app


def _client(app):
    return TestClient(app)


def _node_body(nid=None, name="测试节点", **kw):
    body = {
        "name": name, "difficulty": 2, "category": "基础语法",
        "summary": "这是一个用于自动化测试的知识点摘要内容，确保长度超过三十个字符的阈值要求",
        "prerequisites": [], "key_points": ["要点一", "要点二", "要点三"],
        "practice_questions": [{"type": "choice", "question": "q", "options": ["A", "B"], "answer": "A"}],
        "common_mistakes": ["误区一"], "tags": ["测试"], "estimated_minutes": 30,
    }
    if nid:
        body["id"] = nid
    body.update(kw)
    return body


def _q_body(source="PY-001", qid=None, **kw):
    body = {
        "source_node_id": source, "type": "choice",
        "question": "这是一道测试题干内容", "options": ["A. 选项", "B. 选项"],
        "answer": "A", "difficulty": 2,
    }
    if qid:
        body["qid"] = qid
    body.update(kw)
    return body


# ============================================================
# 节点 CRUD
# ============================================================

def test_create_node_auto_id(app):
    r = _client(app).post("/api/kb/nodes", json=_node_body())
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["node"]["id"] == "PY-001"  # 空库自动从 001
    assert data["warnings"] == []
    # JSON 落地
    assert kb_store.node_id_exists(kb_api.KB_BASE, "PY-001")
    # Neo4j 同步
    assert app.state._fake_kg.nodes.get("PY-001") is not None


def test_create_node_manual_id(app):
    r = _client(app).post("/api/kb/nodes", json=_node_body(nid="ML-001"))
    assert r.status_code == 200
    assert r.json()["node"]["id"] == "ML-001"


def test_create_node_duplicate_id_409(app):
    c = _client(app)
    c.post("/api/kb/nodes", json=_node_body(nid="PY-001"))
    r = c.post("/api/kb/nodes", json=_node_body(nid="PY-001"))
    assert r.status_code == 409


def test_create_node_validation_fail_400(app):
    """category 无效 (Pydantic 不限制 enum, validate_node 拦) → 400。"""
    body = _node_body()
    body["category"] = "不存在的分类"
    r = _client(app).post("/api/kb/nodes", json=body)
    assert r.status_code == 400
    assert "errors" in r.json()["detail"]


def test_get_node_existing(app):
    c = _client(app)
    c.post("/api/kb/nodes", json=_node_body(nid="PY-001", name="变量"))
    r = c.get("/api/kb/nodes/PY-001")
    assert r.status_code == 200
    assert r.json()["node"]["name"] == "变量"


def test_get_node_404(app):
    r = _client(app).get("/api/kb/nodes/PY-999")
    assert r.status_code == 404


def test_update_node_replaces(app):
    c = _client(app)
    c.post("/api/kb/nodes", json=_node_body(nid="PY-001", name="旧名"))
    r = c.put("/api/kb/nodes/PY-001", json=_node_body(nid="PY-001", name="新名"))
    assert r.status_code == 200
    assert r.json()["node"]["name"] == "新名"
    # JSON 原地替换 (不重复)
    assert kb_store.load_node(kb_api.KB_BASE, "PY-001")["name"] == "新名"


def test_update_node_prereqs_rebuilt(app):
    """更新 prerequisites → Neo4j 重建 REQUIRES (upsert 含重建)。"""
    c = _client(app)
    c.post("/api/kb/nodes", json=_node_body(nid="PY-001"))
    c.post("/api/kb/nodes", json=_node_body(nid="PY-002"))
    body = _node_body(nid="PY-002", prerequisites=["PY-001"])
    r = c.put("/api/kb/nodes/PY-002", json=body)
    assert r.status_code == 200
    kg = app.state._fake_kg
    assert kg.nodes["PY-002"]["prerequisites"] == ["PY-001"]


def test_update_node_404(app):
    r = _client(app).put("/api/kb/nodes/PY-999", json=_node_body())
    assert r.status_code == 404


def test_delete_node(app):
    c = _client(app)
    c.post("/api/kb/nodes", json=_node_body(nid="PY-001"))
    r = c.delete("/api/kb/nodes/PY-001")
    assert r.status_code == 200
    assert r.json()["deleted"] is True
    assert not kb_store.node_id_exists(kb_api.KB_BASE, "PY-001")
    assert "PY-001" not in app.state._fake_kg.nodes


def test_delete_node_404(app):
    r = _client(app).delete("/api/kb/nodes/PY-999")
    assert r.status_code == 404


def test_delete_node_cascade_questions(app):
    """cascade=true 连带删该节点题目。"""
    c = _client(app)
    c.post("/api/kb/nodes", json=_node_body(nid="PY-001"))
    c.post("/api/kb/questions", json=_q_body(source="PY-001"))
    r = c.delete("/api/kb/nodes/PY-001?cascade=true")
    assert r.status_code == 200
    assert len(r.json()["deleted_questions"]) == 1


def test_delete_node_no_cascade_keeps_questions(app):
    """默认 cascade=false, 节点删但题目 JSON 保留 (孤儿题, 由 validate 兜底)。"""
    c = _client(app)
    c.post("/api/kb/nodes", json=_node_body(nid="PY-001"))
    c.post("/api/kb/questions", json=_q_body(source="PY-001"))
    r = c.delete("/api/kb/nodes/PY-001")
    assert r.status_code == 200
    assert r.json()["deleted_questions"] == []
    # 题目仍在 JSON
    assert kb_store.find_question(kb_api.KB_BASE, "Q-PY001-001") is not None


# ============================================================
# 题目 CRUD
# ============================================================

def test_create_question_auto_qid(app):
    c = _client(app)
    c.post("/api/kb/nodes", json=_node_body(nid="PY-001"))
    r = c.post("/api/kb/questions", json=_q_body(source="PY-001"))
    assert r.status_code == 200, r.text
    assert r.json()["question"]["qid"] == "Q-PY001-001"


def test_create_question_source_node_missing_400(app):
    r = _client(app).post("/api/kb/questions", json=_q_body(source="PY-999"))
    assert r.status_code == 400


def test_create_question_validation_fail_400(app):
    c = _client(app)
    c.post("/api/kb/nodes", json=_node_body(nid="PY-001"))
    body = _q_body(source="PY-001")
    body["type"] = "invalid_type"
    r = c.post("/api/kb/questions", json=body)
    assert r.status_code == 400


def test_get_question(app):
    c = _client(app)
    c.post("/api/kb/nodes", json=_node_body(nid="PY-001"))
    c.post("/api/kb/questions", json=_q_body(source="PY-001"))
    r = c.get("/api/kb/questions/Q-PY001-001")
    assert r.status_code == 200


def test_get_question_404(app):
    r = _client(app).get("/api/kb/questions/Q-PY001-999")
    assert r.status_code == 404


def test_update_question(app):
    c = _client(app)
    c.post("/api/kb/nodes", json=_node_body(nid="PY-001"))
    c.post("/api/kb/questions", json=_q_body(source="PY-001"))
    body = _q_body(source="PY-001", question="更新后的题干内容")
    r = c.put("/api/kb/questions/Q-PY001-001", json=body)
    assert r.status_code == 200
    assert r.json()["question"]["question"] == "更新后的题干内容"


def test_delete_question(app):
    c = _client(app)
    c.post("/api/kb/nodes", json=_node_body(nid="PY-001"))
    c.post("/api/kb/questions", json=_q_body(source="PY-001"))
    r = c.delete("/api/kb/questions/Q-PY001-001")
    assert r.status_code == 200
    assert kb_store.find_question(kb_api.KB_BASE, "Q-PY001-001") is None


# ============================================================
# Neo4j 同步失败 warning
# ============================================================

def test_create_node_neo4j_sync_fail_returns_warning(app):
    """Neo4j upsert 失败 → JSON 仍写, 返 warning (不回滚)。"""
    app.state._fake_kg.fail_on_upsert_node = True
    r = _client(app).post("/api/kb/nodes", json=_node_body(nid="PY-001"))
    assert r.status_code == 200  # 不阻塞
    assert len(r.json()["warnings"]) > 0
    # JSON 已写 (真相源)
    assert kb_store.node_id_exists(kb_api.KB_BASE, "PY-001")


def test_kg_not_ready_503(tmp_path, monkeypatch):
    """kg 未就绪 → 503。"""
    base = _make_base(tmp_path)
    monkeypatch.setattr(kb_api, "KB_BASE", base)
    app = FastAPI()
    app.state.kg = None  # 未就绪
    app.include_router(kb_api.router, prefix="/api/kb")
    r = TestClient(app).post("/api/kb/nodes", json=_node_body())
    assert r.status_code == 503
