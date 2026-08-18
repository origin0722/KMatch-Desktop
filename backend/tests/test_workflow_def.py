"""workflow_def 流程定义 单测 (Phase 2: 流程即数据)。

覆盖: 校验规则 (必填/未知字段/未知Agent/依赖序/自依赖/重复id)、discovery 内置+data 扩展、
preflight (坏定义/坏请求启动前被拒)、API 端点 (列表/详情/干跑)。
"""

import copy
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agents import workflow_def as wf
from app.api import diagnostics as diag_api


def _def(wid: str) -> dict:
    """深拷贝内置定义 (测试内可安全改写, 不污染模块级 BUILTIN_WORKFLOWS)。"""
    return copy.deepcopy(wf.BUILTIN_WORKFLOWS[wid])


def test_builtin_defs_are_valid():
    for wid, defn in wf.BUILTIN_WORKFLOWS.items():
        assert wf.validate_definition(defn) == [], f"{wid} 应合法"
        assert defn["id"] == wid


def test_workflow_for_mapping():
    assert wf.workflow_for("demo", "no_project") == "scene1-loop"
    assert wf.workflow_for("demo", "with_project") == "scene2-project"
    assert wf.workflow_for("interactive", "no_project") == "scene1-interactive"


def test_validate_rejects_unknown_top_field():
    defn = _def("scene1-loop")
    defn["hack"] = True
    errs = wf.validate_definition(defn)
    assert any("未知顶级字段" in e for e in errs)


def test_validate_rejects_unknown_agent():
    defn = _def("scene1-loop")
    defn["stages"][0] = dict(defn["stages"][0], agents=["not_an_agent"])
    errs = wf.validate_definition(defn)
    assert any("未知 Agent: not_an_agent" in e for e in errs)


def test_validate_rejects_out_of_order_dependency():
    defn = _def("scene1-loop")
    stages = list(defn["stages"])
    # 让第一阶段的依赖指向最后阶段 (乱序) → 报依赖未知/乱序
    stages[0] = dict(stages[0], dependencies=["review-content"])
    defn["stages"] = stages
    errs = wf.validate_definition(defn)
    assert any("乱序" in e for e in errs)


def test_validate_rejects_self_dependency():
    defn = _def("scene1-loop")
    defn["stages"][0] = dict(defn["stages"][0], dependencies=["diagnostics"])
    errs = wf.validate_definition(defn)
    assert any("不能依赖自身" in e for e in errs)


def test_validate_rejects_duplicate_stage_id():
    defn = _def("scene1-loop")
    stages = list(defn["stages"])
    stages.append(dict(stages[0]))  # 重复 id
    defn["stages"] = stages
    errs = wf.validate_definition(defn)
    assert any("重复" in e for e in errs)


def test_validate_rejects_non_list_stages_and_missing_format():
    assert wf.validate_definition({})  # 非空错误
    assert wf.validate_definition({"format": "x", "stages": "nope"})


def test_get_workflow_builtin_and_unknown(monkeypatch, tmp_path):
    from app.config import settings
    monkeypatch.setattr(settings, "DATA_DIR", Path(tmp_path))
    assert wf.get_workflow("scene1-loop")["id"] == "scene1-loop"
    assert wf.get_workflow("nope") is None


def test_data_dir_extensions_and_no_shadow(monkeypatch, tmp_path):
    from app.config import settings
    monkeypatch.setattr(settings, "DATA_DIR", Path(tmp_path))
    d = Path(tmp_path) / "workflows"
    d.mkdir(parents=True, exist_ok=True)
    custom = {
        "format": "kmatch.workflow", "version": 1, "id": "custom-flow", "name": "自定义",
        "stages": [{"id": "a", "label": "A", "agents": ["diagnostics"], "dependencies": []}],
    }
    (d / "custom-flow.json").write_text(json.dumps(custom), encoding="utf-8")
    # 坏文件: 未知 Agent → 跳过
    (d / "bad.json").write_text(json.dumps({**custom, "id": "bad", "stages": [{"id": "a", "agents": ["ghost"]}]}), encoding="utf-8")
    ids = {x["id"] for x in wf.list_workflows()}
    assert "custom-flow" in ids
    assert "bad" not in ids
    assert "scene1-loop" in ids  # 内置仍在
    assert wf.get_workflow("custom-flow")["id"] == "custom-flow"
    assert wf.get_workflow("bad") is None


def test_preflight_ok_and_failures(monkeypatch, tmp_path):
    from app.config import settings
    monkeypatch.setattr(settings, "DATA_DIR", Path(tmp_path))
    ok, errs = wf.preflight("scene1-loop", target_direction="Python", scene="no_project", max_retries=3)
    assert (ok, errs) == (True, [])
    assert wf.preflight("nope", target_direction="x")[0] is False
    assert wf.preflight("scene1-loop", target_direction="")[0] is False
    assert wf.preflight("scene1-loop", target_direction="x", max_retries=99)[0] is False
    assert wf.preflight("scene1-loop", target_direction="x", scene="hack")[0] is False


# ---------------- API ----------------

def _diag_app() -> FastAPI:
    app = FastAPI()
    app.state.kg = object()
    app.state.workflow = object()
    app.include_router(diag_api.router, prefix="/api/diagnostics")
    return app


def test_workflows_api_list_and_detail(monkeypatch, tmp_path):
    from app.config import settings
    monkeypatch.setattr(settings, "DATA_DIR", Path(tmp_path))
    c = TestClient(_diag_app())
    r = c.get("/api/diagnostics/workflows")
    assert r.status_code == 200
    ids = {x["id"] for x in r.json()["workflows"]}
    assert {"scene1-loop", "scene1-interactive", "scene2-project"} <= ids
    r2 = c.get("/api/diagnostics/workflows/scene1-loop")
    assert r2.status_code == 200 and r2.json()["id"] == "scene1-loop"
    assert c.get("/api/diagnostics/workflows/nope").status_code == 404


def test_workflows_api_preflight(monkeypatch, tmp_path):
    from app.config import settings
    monkeypatch.setattr(settings, "DATA_DIR", Path(tmp_path))
    c = TestClient(_diag_app())
    ok = c.post("/api/diagnostics/workflows/preflight",
                json={"workflow_id": "scene1-loop", "target_direction": "Python"}).json()
    assert ok["ok"] is True and ok["errors"] == []
    bad = c.post("/api/diagnostics/workflows/preflight",
                 json={"workflow_id": "scene1-loop", "target_direction": ""}).json()
    assert bad["ok"] is False


# ---------------- Phase 4: 逻辑门 / 决策确定性求值 ----------------

def test_evaluate_gate_predicates():
    ctx = {"a": 1, "b": 0, "lst": [1, 2], "empty": [], "s": "x", "none": None}
    # truthy
    assert wf.evaluate_gate({"on": "a", "predicate": "truthy"}, ctx) is True
    assert wf.evaluate_gate({"on": "b", "predicate": "truthy"}, ctx) is False
    assert wf.evaluate_gate({"on": "missing", "predicate": "truthy"}, ctx) is False
    # falsy
    assert wf.evaluate_gate({"on": "b", "predicate": "falsy"}, ctx) is True
    assert wf.evaluate_gate({"on": "a", "predicate": "falsy"}, ctx) is False
    assert wf.evaluate_gate({"on": "missing", "predicate": "falsy"}, ctx) is True
    # nonEmpty
    assert wf.evaluate_gate({"on": "lst", "predicate": "nonEmpty"}, ctx) is True
    assert wf.evaluate_gate({"on": "empty", "predicate": "nonEmpty"}, ctx) is False
    assert wf.evaluate_gate({"on": "none", "predicate": "nonEmpty"}, ctx) is False
    assert wf.evaluate_gate({"on": "missing", "predicate": "nonEmpty"}, ctx) is False
    # 嵌套点路径
    assert wf.evaluate_gate({"on": "sub.deep", "predicate": "truthy"}, {"sub": {"deep": True}}) is True
    assert wf.evaluate_gate({"on": "sub.deep", "predicate": "truthy"}, {"sub": {}}) is False


def test_strategy_decision_matches_decide_feedback_thresholds():
    """流程定义里的 strategy 决策与 decide_feedback 语义严格一致 (见 diagnostics.py 注释)。"""
    sc = wf.BUILTIN_WORKFLOWS["scene1-interactive"]
    dec = sc["decisions"][0]
    assert dec["id"] == "strategy"
    assert wf.evaluate_decision(dec, {"correct_ratio": 0.85}) == "advance"
    assert wf.evaluate_decision(dec, {"correct_ratio": 0.8}) == "advance"   # ≥0.8
    assert wf.evaluate_decision(dec, {"correct_ratio": 0.75}) == "remediate"  # ≥0.5 & <0.8
    assert wf.evaluate_decision(dec, {"correct_ratio": 0.5}) == "remediate"  # ≥0.5
    assert wf.evaluate_decision(dec, {"correct_ratio": 0.499}) == "scaffold"  # <0.5
    assert wf.evaluate_decision(dec, {"correct_ratio": 0}) == "scaffold"


def test_decision_missing_field_falls_to_else():
    sc = wf.BUILTIN_WORKFLOWS["scene1-interactive"]
    dec = sc["decisions"][0]
    assert wf.evaluate_decision(dec, {}) == "scaffold"  # 缺 correct_ratio → else
    assert wf.evaluate_decision(dec, {"correct_ratio": "not-a-number"}) == "scaffold"
    assert wf.evaluate_decision({}, {}) is None  # 非对象/空决策 → None


def test_def_decisions_result_shape():
    sc = wf.BUILTIN_WORKFLOWS["scene1-loop"]
    out = wf.evaluate_def_decisions(sc, {"correct_ratio": 0.9})
    assert out == [{"id": "strategy", "label": "反馈策略", "chosen": "advance"}]


def test_validate_decisions_rules():
    base = wf.BUILTIN_WORKFLOWS["scene1-loop"]
    # 未知比较算子
    bad1 = {
        "decisions": [{"id": "d", "on": "x", "rules": [{"when": {"FOO": 1}, "then": "a"}]}],
    }
    # else 与 when 互斥
    bad2 = {
        "decisions": [{"id": "d", "on": "x", "rules": [{"when": {"gte": 1}, "then": "a", "else": "b"}]}],
    }
    # 两条 else
    bad3 = {
        "decisions": [{"id": "d", "on": "x", "rules": [{"else": "a"}, {"else": "b"}]}],
    }
    # 未知字段
    bad4 = {"decisions": [{"id": "d", "on": "x", "rules": [{"then": "a"}], "hack": 1}]}
    for b in (bad1, bad2, bad3, bad4):
        defn = dict(base, decisions=b["decisions"])
        assert wf.validate_definition(defn), f"{b} 应校验失败"


def test_workflows_api_evaluate(monkeypatch, tmp_path):
    from app.config import settings
    monkeypatch.setattr(settings, "DATA_DIR", Path(tmp_path))
    c = TestClient(_diag_app())
    r = c.post("/api/diagnostics/workflows/evaluate",
               json={"workflow_id": "scene1-loop", "context": {"correct_ratio": 0.9}})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["decisions"][0] == {"id": "strategy", "label": "反馈策略", "chosen": "advance"}
    assert c.post("/api/diagnostics/workflows/evaluate",
                  json={"workflow_id": "nope", "context": {}}).status_code == 404
