"""项目解析 API 单测 — TestClient + _FakeKG，免真实 Neo4j/LLM。

覆盖:
  - POST /parse (example): simple_crawler 解析返回 G6 结构 + 写库调用
  - POST /parse (text): 内联代码解析
  - POST /parse (write_to_neo4j=False): 不写库仍返回图
  - 错误: example 不存在 404 / code 缺 422 / kg 未就绪 503 / 语法错误 422
  - GET /graph/{id}: 返回落库图谱 / 不存在 404
  - GET /examples: 列出 simple_crawler + todo_backend
"""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import project as project_api


class _FakeKG:
    """记录 write/get 调用的 fake KnowledgeGraph。"""

    def __init__(self):
        self.written = []          # [(project_id, entities, relations)]
        self.stored_graph = None   # get_project_graph 返回值

    def write_project_graph(self, project_id, entities, relations):
        self.written.append((project_id, entities, relations))

    def get_project_graph(self, project_id):
        return self.stored_graph

    def delete_project_graph(self, project_id):
        return 0


def _build_app(kg=None):
    app = FastAPI()
    app.state.kg = kg  # None → 503
    app.include_router(project_api.router, prefix="/api/project")
    return app


# ============================================================
# POST /parse (example)
# ============================================================

def test_parse_example_returns_graph():
    app = _build_app(_FakeKG())
    client = TestClient(app)

    resp = client.post("/api/project/parse", json={
        "source_type": "example", "example_name": "simple_crawler",
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["project_id"] == "simple_crawler"
    assert data["written_to_neo4j"] is True
    assert data["stats"]["class_count"] == 1
    assert data["stats"]["method_count"] == 5
    assert data["stats"]["module_count"] == 1
    # 含 SimpleCrawler 节点
    assert any(n["group"] == "class" and n["label"] == "SimpleCrawler" for n in data["nodes"])
    # 含 CONTAINS 边
    assert any(e["label"] == "CONTAINS" for e in data["edges"])
    # 含 CALLS 边 (crawl→fetch_page)
    assert any(e["label"] == "CALLS" for e in data["edges"])


def test_parse_example_writes_to_neo4j():
    kg = _FakeKG()
    client = TestClient(_build_app(kg))
    client.post("/api/project/parse", json={"source_type": "example", "example_name": "simple_crawler"})
    assert len(kg.written) == 1
    pid, entities, relations = kg.written[0]
    assert pid == "simple_crawler"
    assert len(entities) > 0
    assert len(relations) > 0


def test_parse_write_to_neo4j_false():
    """write_to_neo4j=False → 不调 write，仍返回图。"""
    kg = _FakeKG()
    client = TestClient(_build_app(kg))
    resp = client.post("/api/project/parse", json={
        "source_type": "example", "example_name": "simple_crawler", "write_to_neo4j": False,
    })
    assert resp.status_code == 200
    assert resp.json()["written_to_neo4j"] is False
    assert len(kg.written) == 0  # 未写库


def test_parse_write_to_neo4j_false_without_kg():
    """write_to_neo4j=False 时 kg 未就绪也不报 503 (无需 kg)。"""
    app = _build_app(kg=None)
    client = TestClient(app)
    resp = client.post("/api/project/parse", json={
        "source_type": "example", "example_name": "simple_crawler", "write_to_neo4j": False,
    })
    assert resp.status_code == 200


# ============================================================
# POST /parse (text)
# ============================================================

def test_parse_text_source():
    code = '''
def add(a: int, b: int) -> int:
    """相加"""
    return a + b

class Calc:
    def run(self):
        return add(1, 2)
'''
    client = TestClient(_build_app(_FakeKG()))
    resp = client.post("/api/project/parse", json={
        "source_type": "text", "code": code, "filename": "calc.py",
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["project_id"].startswith("text-")
    assert data["stats"]["class_count"] == 1
    assert data["stats"]["function_count"] == 1
    assert data["stats"]["method_count"] == 1
    # Calc.run → add (CALLS)
    calls = [e for e in data["edges"] if e["label"] == "CALLS"]
    assert len(calls) >= 1


def test_parse_text_syntax_error_422():
    client = TestClient(_build_app(_FakeKG()))
    resp = client.post("/api/project/parse", json={
        "source_type": "text", "code": "def broken(:\n  pass",
    })
    assert resp.status_code == 422


def test_parse_todo_backend_full():
    """第二个示例项目 (Flask + @dataclass) 也能完整解析，防回归。"""
    client = TestClient(_build_app(_FakeKG()))
    resp = client.post("/api/project/parse", json={
        "source_type": "example", "example_name": "todo_backend", "write_to_neo4j": False,
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # 含 TodoItem (@dataclass) + TodoStorage 两个类
    assert data["stats"]["class_count"] >= 2
    class_names = {n["label"] for n in data["nodes"] if n["group"] == "class"}
    assert "TodoItem" in class_names
    assert "TodoStorage" in class_names
    # TodoItem 有 @dataclass 装饰器
    todo_item = next(n for n in data["nodes"] if n["label"] == "TodoItem")
    assert any("dataclass" in d for d in todo_item["properties"]["decorators"])
    # 含模块级路由函数 (@app.route)
    assert data["stats"]["function_count"] >= 1


# ============================================================
# POST /parse 错误
# ============================================================

def test_parse_invalid_example_404():
    client = TestClient(_build_app(_FakeKG()))
    resp = client.post("/api/project/parse", json={
        "source_type": "example", "example_name": "nonexistent",
    })
    assert resp.status_code == 404


def test_parse_example_missing_name_422():
    client = TestClient(_build_app(_FakeKG()))
    resp = client.post("/api/project/parse", json={"source_type": "example"})
    assert resp.status_code == 422


def test_parse_text_missing_code_422():
    client = TestClient(_build_app(_FakeKG()))
    resp = client.post("/api/project/parse", json={"source_type": "text"})
    assert resp.status_code == 422


def test_parse_kg_not_ready_503():
    """write_to_neo4j=True 但 kg 未就绪 → 503。"""
    app = _build_app(kg=None)
    client = TestClient(app)
    resp = client.post("/api/project/parse", json={
        "source_type": "example", "example_name": "simple_crawler",
    })
    assert resp.status_code == 503


# ============================================================
# GET /graph/{project_id}
# ============================================================

def test_get_graph_returns_stored():
    kg = _FakeKG()
    kg.stored_graph = {
        "project_id": "simple_crawler",
        "nodes": [{
            "id": "PROJ-simple_crawler-CLASS-SimpleCrawler",
            "label": "SimpleCrawler", "group": "class", "layer": 2,
            "properties": {"kind": "class", "parsed_at": "2026-06-18T00:00:00Z",
                           "external_calls": [], "params": []},
        }],
        "edges": [{"source": "m", "target": "c", "label": "CONTAINS"}],
    }
    client = TestClient(_build_app(kg))
    resp = client.get("/api/project/graph/simple_crawler")
    assert resp.status_code == 200
    data = resp.json()
    assert data["project_id"] == "simple_crawler"
    assert data["stats"]["class_count"] == 1
    assert data["parsed_at"] == "2026-06-18T00:00:00Z"


def test_get_graph_not_found_404():
    kg = _FakeKG()
    kg.stored_graph = None
    client = TestClient(_build_app(kg))
    resp = client.get("/api/project/graph/missing")
    assert resp.status_code == 404


def test_get_graph_kg_not_ready_503():
    client = TestClient(_build_app(kg=None))
    resp = client.get("/api/project/graph/anything")
    assert resp.status_code == 503


# ============================================================
# GET /examples
# ============================================================

def test_list_examples():
    client = TestClient(_build_app(_FakeKG()))
    resp = client.get("/api/project/examples")
    assert resp.status_code == 200
    names = {e["name"] for e in resp.json()}
    assert "simple_crawler" in names
    assert "todo_backend" in names


# ============================================================
# POST /api/project/test
# ============================================================

def test_api_test_generate_text(monkeypatch):
    """generate + text 源: mock run_tests 返回报告。"""
    from app.api import project as proj_api
    from app.agents import code_tester as ct

    fake_report = {
        "test_report_id": "r1", "tested_at": "2026-06-18T00:00:00Z",
        "coverage": {"line_coverage": 1.0, "branch_coverage": 0.0, "function_coverage": 1.0},
        "summary": {"total": 1, "passed": 1, "failed": 0, "error": 0, "skipped": 0},
        "failed_tests": [], "risk_nodes": [],
        "regression": {"previously_passing_now_failing": [], "newly_passing": []},
        "rejected": False, "reject_reason": None, "note": None,
    }
    monkeypatch.setattr(proj_api, "run_tests", lambda *a, **k: fake_report)
    client = TestClient(_build_app(_FakeKG()))
    resp = client.post("/api/project/test", json={
        "source_type": "text", "code": "def add(a,b):\n    return a+b\n",
        "target_direction": "加法", "mode": "generate",
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["summary"]["passed"] == 1
    assert "coverage" in data and "failed_tests" in data and "risk_nodes" in data


def test_api_test_baseline(monkeypatch):
    from app.api import project as proj_api
    fake_report = {
        "summary": {"total": 4, "passed": 4, "failed": 0, "error": 0, "skipped": 0},
        "coverage": {}, "failed_tests": [], "risk_nodes": [],
        "regression": {"previously_passing_now_failing": [], "newly_passing": []},
        "rejected": False, "reject_reason": None, "note": None,
        "test_report_id": "r", "tested_at": "t",
    }
    monkeypatch.setattr(proj_api, "run_tests", lambda *a, **k: fake_report)
    client = TestClient(_build_app(_FakeKG()))
    resp = client.post("/api/project/test", json={
        "source_type": "example", "example_name": "simple_crawler",
        "target_direction": "爬虫", "mode": "baseline",
    })
    assert resp.status_code == 200, resp.text


def test_api_test_missing_target_direction_422():
    client = TestClient(_build_app(_FakeKG()))
    resp = client.post("/api/project/test", json={
        "source_type": "text", "code": "x=1", "mode": "generate",
    })
    assert resp.status_code == 422


def test_api_test_text_missing_code_422():
    client = TestClient(_build_app(_FakeKG()))
    resp = client.post("/api/project/test", json={
        "source_type": "text", "target_direction": "学习", "mode": "generate",
    })
    assert resp.status_code == 422


def test_api_test_baseline_no_example_name_422():
    client = TestClient(_build_app(_FakeKG()))
    resp = client.post("/api/project/test", json={
        "target_direction": "学习", "mode": "baseline",
    })
    assert resp.status_code == 422


def test_api_test_example_not_found_404():
    client = TestClient(_build_app(_FakeKG()))
    resp = client.post("/api/project/test", json={
        "source_type": "example", "example_name": "nonexistent",
        "target_direction": "学习", "mode": "generate",
    })
    assert resp.status_code == 404


def test_api_test_kg_not_ready_503():
    """kg 未就绪 → 503 (generate 需检索领域知识)。"""
    app = _build_app(kg=None)
    client = TestClient(app)
    resp = client.post("/api/project/test", json={
        "source_type": "text", "code": "x=1",
        "target_direction": "学习", "mode": "generate",
    })
    assert resp.status_code == 503

