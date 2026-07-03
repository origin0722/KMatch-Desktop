"""代码审查 Agent 单测 — 纯函数 + fake kg + TestClient，免真实 Neo4j/LLM。

覆盖:
  - hard_check_code_safety: 危险调用 (eval/exec/os.system/subprocess/pickle/socket) +
    无限循环风险 + 语法错误
  - review_code 编排: 硬规则 + LLM mock + 加权/打回提示
  - LLM 未配置降级 (仅硬规则)
  - 语义检索降级 (embedding 未配置 → 空知识点)
  - POST /api/project/review API (成功/422/503)
"""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agents import code_reviewer as cr
from app.agents.code_reviewer import hard_check_code_safety, review_code
from app.api import project as project_api


# ============================================================
# hard_check_code_safety
# ============================================================

def test_detects_eval():
    issues = hard_check_code_safety("x = eval('1+1')")
    assert any(i["dimension"] == "security" and "eval" in i["problem"] for i in issues)


def test_detects_exec():
    issues = hard_check_code_safety("exec('print(1)')")
    assert any("exec" in i["problem"] for i in issues)


def test_detects_os_system():
    issues = hard_check_code_safety("import os\nos.system('ls')")
    assert any("os.system" in i["problem"] for i in issues)


def test_detects_subprocess():
    issues = hard_check_code_safety("import subprocess\nsubprocess.run(['ls'])")
    assert any("subprocess.run" in i["problem"] for i in issues)


def test_detects_pickle_load():
    issues = hard_check_code_safety("import pickle\npickle.load(open('x'))")
    assert any("pickle.load" in i["problem"] for i in issues)


def test_detects_socket():
    issues = hard_check_code_safety("import socket\ns = socket.socket()")
    assert any("socket" in i["problem"] for i in issues)


def test_detects_infinite_loop():
    issues = hard_check_code_safety("while True:\n    pass")
    assert any(i["dimension"] == "logic_correctness" and "无限循环" in i["problem"] for i in issues)


def test_loop_with_break_not_flagged():
    code = "while True:\n    if x:\n        break\n"
    issues = hard_check_code_safety(code)
    assert not any("无限循环" in i.get("problem", "") for i in issues)


def test_safe_code_no_issues():
    code = "def add(a, b):\n    return a + b\n"
    issues = hard_check_code_safety(code)
    assert issues == []


def test_syntax_error_flagged():
    issues = hard_check_code_safety("def broken(:\n  pass")
    assert any("语法错误" in i["problem"] for i in issues)
    assert all(i["severity"] == "high" for i in issues)


# ============================================================
# review_code 编排 (fake kg + mock LLM)
# ============================================================

class _FakeKG:
    def __init__(self, nodes=None):
        self._nodes = nodes or []

    def get_node(self, nid):
        for n in self._nodes:
            if (n.get("node_id") or n.get("id")) == nid:
                return n
        return None

    def semantic_search(self, query, top_k=5, difficulty_max=None):
        return self._nodes


def test_review_syntax_error_rejects():
    """语法错误 → 直接判不通过。"""
    result = review_code(_FakeKG(), "def broken(:", "学习列表")
    assert result["passed"] is False
    assert result["verdict"] == "reject"
    assert "语法错误" in result["retry_hint"]


def test_review_hard_issue_lowers_security_score(monkeypatch):
    """危险调用 → security 维度分数下调，overall 受影响。"""
    monkeypatch.setattr(cr, "llm_configured", lambda: False)  # 仅硬规则
    code = "x = eval('1+1')"
    result = review_code(_FakeKG(), code, "学习")
    assert result["dimensions"]["security"]["score"] <= 0.6
    assert any("eval" in i["problem"] for i in result["dimensions"]["security"]["issues"])


def test_review_high_security_veto(monkeypatch):
    """高危安全问题 (eval) 一票否决，即使其他维度满分也不通过。"""
    fake_dims = {dim: {"score": 1.0, "issues": []} for dim in cr.CODE_REVIEW_DIMENSIONS}
    monkeypatch.setattr(cr, "llm_configured", lambda: True)
    monkeypatch.setattr(cr, "llm_review_code", lambda code, td, kn, llm_overrides=None: fake_dims)
    monkeypatch.setattr(cr, "_retrieve_knowledge", lambda kg, td, ids, top_k=5: [])
    result = review_code(_FakeKG(), "x = eval('1+1')", "学习")
    assert result["passed"] is False
    assert "一票否决" in result["retry_hint"]


def test_review_llm_mocked_pass(monkeypatch):
    """LLM mock 返回高分 → 通过。"""
    fake_dims = {dim: {"score": 0.95, "issues": []} for dim in cr.CODE_REVIEW_DIMENSIONS}
    monkeypatch.setattr(cr, "llm_configured", lambda: True)
    monkeypatch.setattr(cr, "llm_review_code", lambda code, td, kn, llm_overrides=None: fake_dims)
    monkeypatch.setattr(cr, "_retrieve_knowledge", lambda kg, td, ids, top_k=5: [])

    code = "def add(a, b):\n    return a + b\n"
    result = review_code(_FakeKG(), code, "学习加法")
    assert result["passed"] is True
    assert result["overall_score"] >= 0.85
    assert result["verdict"] == "pass"


def test_review_llm_mocked_reject_builds_hint(monkeypatch):
    """LLM mock 返回低分 + issues → 不通过，retry_hint 含问题。"""
    fake_dims = {
        "logic_correctness": {"score": 0.4, "issues": [{"problem": "未处理空列表边界"}]},
        "security": {"score": 0.9, "issues": []},
        "code_quality": {"score": 0.9, "issues": []},
        "domain_compliance": {"score": 0.9, "issues": []},
    }
    monkeypatch.setattr(cr, "llm_configured", lambda: True)
    monkeypatch.setattr(cr, "llm_review_code", lambda code, td, kn, llm_overrides=None: fake_dims)
    monkeypatch.setattr(cr, "_retrieve_knowledge", lambda kg, td, ids, top_k=5: [])

    result = review_code(_FakeKG(), "def f():\n    pass", "学习")
    assert result["passed"] is False
    assert "空列表边界" in result["retry_hint"]


def test_review_retrieves_knowledge_by_target(monkeypatch):
    """未指定 node_ids → 按 target_direction 语义检索知识点。"""
    retrieved = []
    monkeypatch.setattr(cr, "llm_configured", lambda: True)
    monkeypatch.setattr(cr, "llm_review_code", lambda code, td, kn, llm_overrides=None: (retrieved.extend(kn), {dim: {"score": 0.95, "issues": []} for dim in cr.CODE_REVIEW_DIMENSIONS})[1])

    nodes = [{"node_id": "PY-012", "name": "列表切片", "key_points": ["切片语法"], "common_mistakes": ["越界"]}]
    result = review_code(_FakeKG(nodes=nodes), "def f():\n    pass", "列表切片")
    assert len(retrieved) == 1
    assert retrieved[0]["node_id"] == "PY-012"


def test_review_uses_specified_node_ids(monkeypatch):
    """指定 knowledge_node_ids → 用 get_node 取，不调语义检索。"""
    used_nodes = []
    monkeypatch.setattr(cr, "llm_configured", lambda: True)
    monkeypatch.setattr(cr, "llm_review_code", lambda code, td, kn, llm_overrides=None: (used_nodes.extend(kn), {dim: {"score": 0.95, "issues": []} for dim in cr.CODE_REVIEW_DIMENSIONS})[1])

    nodes = [{"node_id": "PY-005", "name": "循环", "key_points": ["for"], "common_mistakes": []}]
    kg = _FakeKG(nodes=nodes)
    result = review_code(kg, "for i in range(10):\n    pass", "循环", knowledge_node_ids=["PY-005"])
    assert used_nodes[0]["node_id"] == "PY-005"


def test_review_dimensions_always_four():
    """dimensions 始终含四维度 (B 端契约: 不缺 key)。"""
    from app.agents.code_reviewer import _default_code_dims, _normalize_code_dims
    dims = _normalize_code_dims({"logic_correctness": 0.5})  # 扁平/部分
    for dim in cr.CODE_REVIEW_DIMENSIONS:
        assert dim in dims
        assert "score" in dims[dim] and "issues" in dims[dim]


# ============================================================
# API: POST /api/project/review
# ============================================================

def _build_app(kg=None):
    app = FastAPI()
    app.state.kg = kg
    app.include_router(project_api.router, prefix="/api/project")
    return app


def test_api_review_success(monkeypatch):
    monkeypatch.setattr(cr, "llm_configured", lambda: False)
    app = _build_app(_FakeKG())
    client = TestClient(app)
    resp = client.post("/api/project/review", json={
        "code": "def add(a, b):\n    return a + b\n", "target_direction": "学习加法",
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "passed" in data and "dimensions" in data
    assert set(data["dimensions"].keys()) == set(cr.CODE_REVIEW_DIMENSIONS)


def test_api_review_detects_danger(monkeypatch):
    monkeypatch.setattr(cr, "llm_configured", lambda: False)
    app = _build_app(_FakeKG())
    client = TestClient(app)
    resp = client.post("/api/project/review", json={
        "code": "x = eval(input())", "target_direction": "学习",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["passed"] is False
    assert data["dimensions"]["security"]["score"] <= 0.6


def test_api_review_missing_code_422():
    client = TestClient(_build_app(_FakeKG()))
    resp = client.post("/api/project/review", json={"target_direction": "学习"})
    assert resp.status_code == 422


def test_api_review_missing_direction_422():
    client = TestClient(_build_app(_FakeKG()))
    resp = client.post("/api/project/review", json={"code": "x=1"})
    assert resp.status_code == 422


def test_api_review_kg_not_ready_503():
    app = _build_app(kg=None)
    client = TestClient(app)
    resp = client.post("/api/project/review", json={"code": "x=1", "target_direction": "学习"})
    assert resp.status_code == 503


# ============================================================
# B9 回归: _has_break 只统计本层循环的 break
# ============================================================

import ast as _ast
from app.agents.code_reviewer import _has_break


def _while_of(code):
    tree = _ast.parse(code)
    return next(n for n in _ast.walk(tree) if isinstance(n, _ast.While))


def test_has_break_same_level_if():
    assert _has_break(_while_of("while True:\n  if x:\n    break")) is True


def test_has_break_none():
    assert _has_break(_while_of("while True:\n  pass")) is False


def test_has_break_inner_for_break_not_counted():
    """B9 核心: 内层 for 的 break 不算外层 while 的 → while True 应判无 break (假阴性修复)。"""
    assert _has_break(_while_of("while True:\n  for x in y:\n    break")) is False


def test_has_break_nested_function_break_not_counted():
    assert _has_break(_while_of("while True:\n  def f():\n    break")) is False


def test_has_break_inner_while_break_not_counted():
    assert _has_break(_while_of("while True:\n  while z:\n    break")) is False


def test_has_break_same_level_even_with_inner_for():
    code = "while True:\n  if x:\n    break\n  for y in z:\n    break"
    assert _has_break(_while_of(code)) is True


# ============================================================
# B12 回归: _merge_code_issues 仅封顶硬规则命中维度
# ============================================================

from app.agents.code_reviewer import _merge_code_issues


def test_merge_code_issues_only_caps_hard_hit():
    dims = {
        "logic_correctness": {"score": 0.9, "issues": [{"problem": "轻微"}]},  # LLM 带 issue
        "security": {"score": 1.0, "issues": []},
        "code_quality": {"score": 1.0, "issues": []},
        "domain_compliance": {"score": 1.0, "issues": []},
    }
    hard = [{"dimension": "security", "problem": "eval 高危"}]
    result = _merge_code_issues(dims, hard)
    assert result["security"]["score"] == 0.6  # 硬规则命中 → 封顶
    assert result["logic_correctness"]["score"] == 0.9  # LLM 维度保留 (B12)
