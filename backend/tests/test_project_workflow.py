"""场景二 LangGraph 编排单测 (W6) — mock review_code/run_tests, 免真实 LLM/沙箱。

覆盖:
  - project_review_node: 多文件审查合并 (任一未过即未过) + 单文件异常容错
  - happy path: 审查通过 → test 全过 → finish (无 repair)
  - 打回循环: 测试 rejected (infra 失败) → 携 hint 定向再生 → retry 超限 → repair
  - 断言失败: failed_tests → repair (不打回)
  - 语法级 critical: 审查命中"语法错误" → 跳过 test 直达 repair
  - repair: LLM 未配置 → 确定性兜底指引
  - POST /api/project/pipeline 路由: 全链路 mock + 参数校验 422
"""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agents import project_workflow as pw
from app.api import project as project_api


class _FakeKG:
    pass


def _review(passed=True, score=0.9, hint="", file="main.py"):
    return {"passed": passed, "overall_score": score, "verdict": "pass" if passed else "reject",
            "retry_hint": hint, "dimensions": {}, "threshold": 0.85, "file": file}


def _report(rejected=False, reason=None, failed=None, passed=3, total=3):
    return {"rejected": rejected, "reject_reason": reason,
            "summary": {"passed": 0 if rejected else passed, "total": 0 if rejected else total},
            "failed_tests": failed or [], "coverage": {}, "risk_nodes": []}


def _state(max_retries=2, **kw):
    base = {
        "target_direction": "爬虫开发", "project_files": {"main": "print(1)"},
        "reviews": [], "review_results": {}, "test_report": {},
        "repair_guidance": {}, "retry_count": 0, "max_retries": max_retries,
        "orchestration_log": [],
    }
    base.update(kw)
    return base


# ============================================================
# 节点纯逻辑
# ============================================================

def test_merged_review_any_fail_fails():
    merged = pw._merged_review([_review(True, 0.9), _review(False, 0.4, hint="缺安全检查", file="b.py")])
    assert merged["passed"] is False
    assert merged["overall_score"] == 0.4
    assert "缺安全检查" in merged["retry_hint"]


def test_select_review_files_caps():
    files = {f"f{i}": "x" * (10 - i) for i in range(6)}
    picked = pw._select_review_files(files)
    assert len(picked) == pw.MAX_REVIEW_FILES
    assert picked[0][1] == "x" * 10  # 最长者入选


def test_decide_after_review_syntax_critical_skips_test():
    reviews = [_review(False, 0.0, hint="代码存在语法错误，无法完成审查")]
    assert pw._decide_after_review(_state(reviews=reviews)) == "repair"
    assert pw._decide_after_review(_state(reviews=[_review(True)])) == "test"
    assert pw._decide_after_review(_state(reviews=[])) == "finish"


def test_decide_after_test_rejected_loops_then_repairs():
    st = _state(test_report=_report(rejected=True, reason="检测到高危调用"), retry_count=0)
    assert pw._decide_after_test(st) == "test"     # 第1轮 → 打回再生
    st["retry_count"] = 2                           # 达 max_retries
    assert pw._decide_after_test(st) == "repair"


def test_decide_after_test_assertion_failure_goes_repair():
    failed = [{"test_name": "test_fetch_happy_path", "error_type": "AssertionError"}]
    st = _state(test_report=_report(failed=failed, passed=2, total=3))
    assert pw._decide_after_test(st) == "repair"    # 断言失败=真实问题, 不打回


def test_decide_after_test_all_pass_finish():
    st = _state(test_report=_report(passed=3, total=3))
    assert pw._decide_after_test(st) == "finish"


# ============================================================
# 编排整图 (mock review_code / run_tests)
# ============================================================

def test_workflow_happy_path_no_repair(monkeypatch):
    calls = {"review": 0, "test": 0}

    def _fake_review(kg, code, direction, knowledge_node_ids=None, llm_overrides=None):
        calls["review"] += 1
        return _review(True, 0.92)

    def _fake_run_tests(kg, sources, direction, **kw):
        calls["test"] += 1
        assert kw.get("correction_hint") == ""  # 首轮无 hint
        return _report(passed=4, total=4)

    monkeypatch.setattr(pw, "review_code", _fake_review)
    monkeypatch.setattr(pw, "run_tests", _fake_run_tests)

    wf = pw.build_project_workflow(_FakeKG())
    result = wf.invoke(_state(), {"configurable": {"thread_id": "t1"}})
    assert calls == {"review": 1, "test": 1}
    assert result["test_report"]["summary"]["passed"] == 4
    assert not result.get("repair_guidance")  # 全过无修复指引


def test_workflow_rejected_loop_then_repair(monkeypatch):
    seen_hints = []

    def _fake_review(kg, code, direction, knowledge_node_ids=None, llm_overrides=None):
        return _review(True, 0.9)

    def _fake_run_tests(kg, sources, direction, **kw):
        seen_hints.append(kw.get("correction_hint") or "")
        if len(seen_hints) == 1:
            return _report(rejected=True, reason="检测到高危调用，拒绝执行")  # 首轮 rejected → 打回
        return _report(failed=[{"test_name": "test_fetch_happy_path", "error_type": "AssertionError"}],
                       passed=2, total=3)  # 再生后可执行, 但有断言失败 → repair

    monkeypatch.setattr(pw, "review_code", _fake_review)
    monkeypatch.setattr(pw, "run_tests", _fake_run_tests)
    # LLM 未配置 → repair 走确定性兜底
    monkeypatch.setattr(pw, "llm_configured", lambda: False)

    wf = pw.build_project_workflow(_FakeKG())
    result = wf.invoke(_state(max_retries=2), {"configurable": {"thread_id": "t2"}})
    assert len(seen_hints) == 2                                  # 打回了 1 次
    assert "高危调用" in seen_hints[1]                            # 二轮携带 hint (定向再生)
    assert result["repair_guidance"]["source"] == "deterministic"
    assert result["retry_count"] == 2


def test_workflow_rejected_then_regen_passes_finishes(monkeypatch):
    """打回再生后全部通过 → 直接 finish, 不产 repair (循环收敛)。"""
    calls = {"n": 0}

    def _fake_review(kg, code, direction, knowledge_node_ids=None, llm_overrides=None):
        return _review(True, 0.9)

    def _fake_run_tests(kg, sources, direction, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            return _report(rejected=True, reason="生成的测试代码 AST 预检未通过")
        return _report(passed=3, total=3)

    monkeypatch.setattr(pw, "review_code", _fake_review)
    monkeypatch.setattr(pw, "run_tests", _fake_run_tests)

    wf = pw.build_project_workflow(_FakeKG())
    result = wf.invoke(_state(max_retries=2), {"configurable": {"thread_id": "t2b"}})
    assert calls["n"] == 2
    assert not result.get("repair_guidance")


def test_workflow_syntax_critical_skips_test(monkeypatch):
    def _fake_review(kg, code, direction, knowledge_node_ids=None, llm_overrides=None):
        return _review(False, 0.0, hint="代码存在语法错误，无法完成审查，请修正语法后重新提交")

    def _fail_test(*a, **kw):
        raise AssertionError("语法级 critical 不应执行测试")

    monkeypatch.setattr(pw, "review_code", _fake_review)
    monkeypatch.setattr(pw, "run_tests", _fail_test)
    monkeypatch.setattr(pw, "llm_configured", lambda: False)

    wf = pw.build_project_workflow(_FakeKG())
    result = wf.invoke(_state(), {"configurable": {"thread_id": "t3"}})
    assert result["repair_guidance"]["source"] == "deterministic"
    assert any("语法" in g["detail"] or "语法" in g["title"] for g in result["repair_guidance"]["guidance"])


def test_workflow_assertion_failure_produces_guidance(monkeypatch):
    monkeypatch.setattr(pw, "review_code", lambda *a, **kw: _review(True, 0.88))
    failed = [{"test_name": "test_parse_boundary", "suggestion": "空输入未处理"}]
    monkeypatch.setattr(pw, "run_tests", lambda *a, **kw: _report(failed=failed, passed=2, total=3))
    monkeypatch.setattr(pw, "llm_configured", lambda: False)

    wf = pw.build_project_workflow(_FakeKG())
    result = wf.invoke(_state(), {"configurable": {"thread_id": "t4"}})
    g = result["repair_guidance"]
    assert g["source"] == "deterministic"
    assert any("test_parse_boundary" in i["title"] for i in g["guidance"])


# ============================================================
# POST /api/project/pipeline 路由
# ============================================================

def _build_app():
    app = FastAPI()
    app.state.kg = _FakeKG()
    app.include_router(project_api.router, prefix="/api/project")
    return app


def test_pipeline_api_full_run(monkeypatch):
    monkeypatch.setattr(pw, "review_code", lambda *a, **kw: _review(True, 0.9))
    monkeypatch.setattr(pw, "run_tests", lambda *a, **kw: _report(passed=2, total=2))
    monkeypatch.setattr(pw, "llm_configured", lambda: False)

    client = TestClient(_build_app())
    resp = client.post("/api/project/pipeline", json={
        "source_type": "text", "code": "def add(a, b):\n    return a + b\n",
        "target_direction": "计算器模块", "max_retries": 2,
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["review_results"]["passed"] is True
    assert data["test_report"]["summary"]["total"] == 2
    assert data["session_id"].startswith("proj-")
    assert any("场景二" in line for line in data["orchestration_log"])


def test_pipeline_api_validation(monkeypatch):
    client = TestClient(_build_app())
    # code 缺失 → 422
    resp = client.post("/api/project/pipeline", json={"target_direction": "x"})
    assert resp.status_code == 422
    # target_direction 缺失 → 422
    resp = client.post("/api/project/pipeline", json={"code": "print(1)"})
    assert resp.status_code == 422
