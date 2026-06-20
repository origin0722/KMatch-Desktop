"""chat /safety-check 端点 + code_safety 模块单测 (阶段3.1 write_file 审批门)。

验证:
  - 端点对 .py 高危代码返回 safe=False + high severity issue
  - 安全 .py 返回 safe=True
  - 非 .py 文件跳过 AST, checked=False
  - code_safety 直接调用: 危险内建/模块调用/无限循环/语法错误
  - code_reviewer re-export 与 code_safety 同一对象 (向后兼容)
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.agents import code_safety, code_reviewer


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


# ----------------------------------------------------------------
# /api/chat/safety-check 端点
# ----------------------------------------------------------------
def test_safety_check_py_high_risk(client):
    r = client.post("/api/chat/safety-check", json={
        "code": "import os\nos.system('ls')", "filename": "x.py",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["language"] == "python"
    assert body["checked"] is True
    assert body["safe"] is False
    assert any(i["severity"] == "high" for i in body["issues"])


def test_safety_check_py_safe(client):
    r = client.post("/api/chat/safety-check", json={
        "code": "x = 1 + 2\nprint(x)", "filename": "x.py",
    })
    body = r.json()
    assert body["safe"] is True
    assert body["issues"] == []


def test_safety_check_non_python_skipped(client):
    r = client.post("/api/chat/safety-check", json={
        "code": "console.log('eval(exec)')", "filename": "x.js",
    })
    body = r.json()
    assert body["language"] == "non-python"
    assert body["checked"] is False
    assert body["safe"] is True
    assert body["issues"] == []


def test_safety_check_no_filename_defaults_python(client):
    # 不传 filename → 视为 python 检查
    r = client.post("/api/chat/safety-check", json={"code": "exec('x')"})
    body = r.json()
    assert body["checked"] is True
    assert body["safe"] is False


# ----------------------------------------------------------------
# code_safety 模块直接调用
# ----------------------------------------------------------------
def test_dangerous_builtins():
    for code in ["eval('1')", "exec('1')", "compile('1','','exec')"]:
        iss = code_safety.hard_check_code_safety(code)
        assert any(i["severity"] == "high" and i["dimension"] == "security" for i in iss), code


def test_dangerous_module_calls():
    cases = [
        "import os\nos.system('ls')",
        "import subprocess\nsubprocess.run(['ls'])",
        "import pickle\npickle.load(open('x','rb'))",
        "import socket\nsocket.socket()",
    ]
    for code in cases:
        iss = code_safety.hard_check_code_safety(code)
        assert any(i["severity"] == "high" for i in iss), code


def test_while_true_no_break_medium():
    iss = code_safety.hard_check_code_safety("while True:\n    pass")
    assert any(i["severity"] == "medium" for i in iss)


def test_syntax_error_high():
    iss = code_safety.hard_check_code_safety("def broken(:\n  pass")
    assert len(iss) == 1 and iss[0]["severity"] == "high"


def test_safe_code_clean():
    assert code_safety.hard_check_code_safety("x = [i for i in range(10)]") == []


# ----------------------------------------------------------------
# re-export 向后兼容 (tests 仍可 from code_reviewer import)
# ----------------------------------------------------------------
def test_code_reviewer_reexport_identity():
    assert code_reviewer.hard_check_code_safety is code_safety.hard_check_code_safety
    assert code_reviewer._has_break is code_safety._has_break
    assert code_reviewer._DANGEROUS_CALLS is code_safety._DANGEROUS_CALLS
