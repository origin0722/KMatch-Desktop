"""code_tester 单测 — 纯函数 + fake kg + mock 沙箱，免真实 LLM/Neo4j。

覆盖:
  - _extract_test_code_and_metadata: python/json 块提取
  - _ast_precheck_reject: 源码+测试代码双预检拒绝
  - generate_test_cases: mock LLM + 知识检索 + 降级
  - build_test_report: 06 prompt 全字段映射
  - annotate_failed_entities: 失败→annotate_risk + level 启发式 + link
  - run_tests: mock 沙箱完整报告 + AST 拒绝 + baseline
"""

from unittest.mock import MagicMock

import pytest

from app.agents import code_tester as ct
from app.agents.code_tester import (
    _ast_precheck_reject,
    _extract_test_code_and_metadata,
    annotate_failed_entities,
    build_test_report,
    generate_test_cases,
    run_tests,
)
from app.agents.sandbox import TestCaseResult, TestRunResult
from app.code_parser.models import CodeEntity


# ============================================================
# Fake KG (记录 annotate_risk / link_entity_to_knowledge)
# ============================================================

class _FakeKG:
    def __init__(self, nodes=None):
        self._nodes = nodes or []
        self.risk_annotations = []   # [(entity_id, level, reason)]
        self.links = []              # [(entity_id, knowledge_node_id)]

    def get_node(self, nid):
        for n in self._nodes:
            if (n.get("node_id") or n.get("id")) == nid:
                return n
        return None

    def semantic_search(self, query, top_k=5, difficulty_max=None):
        return self._nodes

    def annotate_risk(self, entity_id, risk_level, reason):
        self.risk_annotations.append((entity_id, risk_level, reason))

    def link_entity_to_knowledge(self, entity_id, knowledge_node_id):
        self.links.append((entity_id, knowledge_node_id))


def _entity(eid="PROJ-p-FUNC-add", kind="function", name="add", module="main",
            line_start=1, line_end=2):
    return CodeEntity(entity_id=eid, project_id="p", kind=kind, name=name,
                      qualified_name=name, module_name=module, layer=2,
                      line_start=line_start, line_end=line_end,
                      params=[{"name": "a"}, {"name": "b"}], return_type="int",
                      source_code="def add(a,b):\n    return a+b\n")


# ============================================================
# _extract_test_code_and_metadata
# ============================================================

def test_extract_code_and_metadata():
    text = '''前文
```python
from main import add
def test_add():
    assert add(1,2)==3
```
```json
{"tests":[{"test_name":"test_add","related_node":"PROJ-p-FUNC-add","related_keypoint":null,"scenario":"happy_path"}]}
```'''
    code, meta = _extract_test_code_and_metadata(text)
    assert "def test_add" in code
    assert len(meta) == 1
    assert meta[0]["related_node"] == "PROJ-p-FUNC-add"


def test_extract_no_json_block():
    text = "```python\ndef test_x():\n    pass\n```"
    code, meta = _extract_test_code_and_metadata(text)
    assert "def test_x" in code
    assert meta == []


# ============================================================
# _ast_precheck_reject
# ============================================================

def test_precheck_rejects_source_eval():
    reason = _ast_precheck_reject("x = eval('1+1')")
    assert reason is not None
    assert "eval" in reason


def test_precheck_rejects_test_code():
    """测试代码含危险调用也拒绝。"""
    reason = _ast_precheck_reject("def add(a,b): return a+b", "import os\nos.system('rm -rf /')")
    assert reason is not None
    assert "os.system" in reason


def test_precheck_safe_passes():
    assert _ast_precheck_reject("def add(a,b): return a+b") is None


# ============================================================
# generate_test_cases
# ============================================================

def test_generate_uses_knowledge_retrieval(monkeypatch):
    """generate 调用知识检索。"""
    kg = _FakeKG(nodes=[{"node_id": "PY-005", "name": "循环", "common_mistakes": ["死循环"]}])
    monkeypatch.setattr(ct, "llm_configured", lambda: True)
    monkeypatch.setattr(ct, "llm_generate_tests",
                        lambda entities, kn, td, mn, llm_overrides=None, correction_hint="": ("def test_x():\n    pass\n",
                                                      [{"test_name": "test_x", "related_node": "e1"}]))
    gen = generate_test_cases(kg, [_entity()], "学习加法", None, "main")
    assert gen["degraded"] is False
    assert gen["test_code"]
    assert len(gen["knowledge_nodes"]) == 1


def test_generate_degraded_when_no_llm(monkeypatch):
    """LLM 未配置 → degraded=True。"""
    monkeypatch.setattr(ct, "llm_configured", lambda: False)
    gen = generate_test_cases(_FakeKG(), [_entity()], "学习", None, "main")
    assert gen["degraded"] is True
    assert gen["test_code"] is None


# ============================================================
# build_test_report
# ============================================================

def _run_result(failed=True):
    cases = []
    if failed:
        cases.append(TestCaseResult(test_name="test_add_bad", classname="test_main",
                                    status="failed", error_type="AssertionError",
                                    message="assert add(1,1) == 3"))
    else:
        cases.append(TestCaseResult(test_name="test_add_ok", classname="test_main",
                                    status="passed"))
    return TestRunResult(
        success=True, exit_code=1 if failed else 0,
        summary={"total": 1, "passed": 0 if failed else 1, "failed": 1 if failed else 0,
                 "error": 0, "skipped": 0},
        cases=cases,
        coverage={"line_coverage": 0.8, "branch_coverage": 0.5, "function_coverage": 1.0},
    )


def test_build_report_full_fields():
    run = _run_result(failed=True)
    meta = [{"test_name": "test_add_bad", "related_node": "PROJ-p-FUNC-add",
             "related_keypoint": "PY-005", "scenario": "happy_path"}]
    nodes = [{"node_id": "PY-005", "common_mistakes": ["未处理空输入"]}]
    report = build_test_report(run, meta, [_entity()], nodes)
    assert report["rejected"] is False
    assert report["summary"]["failed"] == 1
    assert report["coverage"]["line_coverage"] == 0.8
    assert len(report["failed_tests"]) == 1
    ft = report["failed_tests"][0]
    assert ft["error_type"] == "AssertionError"
    assert ft["related_node"] == "PROJ-p-FUNC-add"
    assert ft["related_keypoint"] == "PY-005"
    assert "空输入" in ft["suggestion"]  # 来自 common_mistakes


def test_build_report_rejected():
    report = build_test_report(TestRunResult(success=False, exit_code=0), [], [], [],
                               rejected=True, reject_reason="检测到 eval")
    assert report["rejected"] is True
    assert report["reject_reason"] == "检测到 eval"
    assert report["summary"]["total"] == 0


def test_build_report_assert_parse():
    """expected/actual 从 assert 语句解析。"""
    run = TestRunResult(
        success=True, exit_code=1,
        summary={"total": 1, "passed": 0, "failed": 1, "error": 0, "skipped": 0},
        cases=[TestCaseResult(test_name="t", classname="c", status="failed",
                              error_type="AssertionError", message="assert add(1,1) == 3")],
        coverage={"line_coverage": 0.5, "branch_coverage": 0.0, "function_coverage": 0.0},
    )
    report = build_test_report(run, [], [], [])
    ft = report["failed_tests"][0]
    assert "add(1,1)" in ft["expected"]
    assert "3" in ft["actual"]


# ============================================================
# annotate_failed_entities
# ============================================================

def test_annotate_two_failures_same_entity_high():
    """同 entity 2 失败 → high + annotate_risk 调用。"""
    run = TestRunResult(
        success=True, exit_code=1,
        summary={"total": 2, "passed": 0, "failed": 2, "error": 0, "skipped": 0},
        cases=[
            TestCaseResult(test_name="test_add_a", classname="c", status="failed",
                           message="assert 1==2"),
            TestCaseResult(test_name="test_add_b", classname="c", status="failed",
                           message="assert 3==4"),
        ],
    )
    meta = [{"test_name": "test_add_a", "related_node": "PROJ-p-FUNC-add", "related_keypoint": "PY-005"},
            {"test_name": "test_add_b", "related_node": "PROJ-p-FUNC-add", "related_keypoint": None}]
    kg = _FakeKG(nodes=[{"node_id": "PY-005"}])
    risk_nodes = annotate_failed_entities(kg, "p", run, meta, [{"node_id": "PY-005"}])
    assert len(risk_nodes) == 1
    assert risk_nodes[0]["risk_level"] == "high"
    assert risk_nodes[0]["node_id"] == "PROJ-p-FUNC-add"
    # annotate_risk 调用 1 次 (聚合后)
    assert len(kg.risk_annotations) == 1
    assert kg.risk_annotations[0][1] == "high"
    # link 调用 (有 related_keypoint)
    assert any(l[1] == "PY-005" for l in kg.links)


def test_annotate_one_failure_medium():
    """单失败 → medium。"""
    run = TestRunResult(
        success=True, exit_code=1,
        summary={"total": 1, "passed": 0, "failed": 1, "error": 0, "skipped": 0},
        cases=[TestCaseResult(test_name="t", classname="c", status="failed", message="x")],
    )
    meta = [{"test_name": "t", "related_node": "PROJ-p-FUNC-add"}]
    kg = _FakeKG()
    risk_nodes = annotate_failed_entities(kg, "p", run, meta, [])
    assert risk_nodes[0]["risk_level"] == "medium"


def test_annotate_no_failures_empty():
    run = TestRunResult(success=True, exit_code=0,
                        summary={"total": 1, "passed": 1, "failed": 0, "error": 0, "skipped": 0},
                        cases=[TestCaseResult(test_name="t", classname="c", status="passed")])
    kg = _FakeKG()
    assert annotate_failed_entities(kg, "p", run, [], []) == []
    assert kg.risk_annotations == []


def test_annotate_missing_related_node_uses_entities_not_dict_attrerror():
    """回归: 失败用例 metadata 缺 related_node 时, 应从 test_name 反推 entity_id,
    而非对 knowledge_nodes[dict] 取 .kind 致 AttributeError (BUG A2)。"""
    run = TestRunResult(
        success=True, exit_code=1,
        summary={"total": 1, "passed": 0, "failed": 1, "error": 0, "skipped": 0},
        cases=[TestCaseResult(test_name="test_add_happy", classname="c", status="failed",
                              message="assert 1==2")],
    )
    # metadata 无 related_node (LLM 元数据不可靠的常态)
    meta = [{"test_name": "test_add_happy"}]
    kg = _FakeKG()
    # knowledge_nodes 非空 (dict 列表) — 旧代码在此对 dict 取 .kind 崩溃
    ents = [_entity(eid="PROJ-p-FUNC-add", name="add")]
    risk_nodes = annotate_failed_entities(kg, "p", run, meta, [{"node_id": "PY-005"}], ents)
    assert len(risk_nodes) == 1
    # 反推成功: test_add_happy 含 "add" → entity_id
    assert risk_nodes[0]["node_id"] == "PROJ-p-FUNC-add"


def test_annotate_missing_related_node_no_entities_no_crash():
    """无 entities 可反推时 (baseline 模式/解析失败), related_node=None, 不崩溃。"""
    run = TestRunResult(
        success=True, exit_code=1,
        summary={"total": 1, "passed": 0, "failed": 1, "error": 0, "skipped": 0},
        cases=[TestCaseResult(test_name="test_x", classname="c", status="failed", message="e")],
    )
    meta = [{"test_name": "test_x"}]  # 无 related_node
    kg = _FakeKG()
    # 不传 entities (默认空) — related_node 反推为 None, 不进 by_entity, risk_nodes 空
    risk_nodes = annotate_failed_entities(kg, "p", run, meta, [], None)
    assert risk_nodes == []


# ============================================================
# run_tests (mock 沙箱)
# ============================================================

class _MockExecutor:
    """固定返回的沙箱 mock。"""

    def __init__(self, run_result):
        self._run_result = run_result
        self.calls = []

    def run(self, workdir, module_name, test_filename, cov_module, timeout=30):
        self.calls.append((workdir, module_name, test_filename, cov_module, timeout))
        return self._run_result


def test_run_tests_generate_mocked(monkeypatch):
    """generate 模式: mock 生成 + mock 沙箱 → 完整报告 + 标注。"""
    monkeypatch.setattr(ct, "llm_configured", lambda: True)
    monkeypatch.setattr(ct, "generate_test_cases", lambda kg, e, td, ids, mn, llm_overrides=None, correction_hint="": {
        "test_code": "from main import add\ndef test_add():\n    assert add(1,2)==3\n",
        "test_metadata": [{"test_name": "test_add", "related_node": "PROJ-p-FUNC-add"}],
        "knowledge_nodes": [], "degraded": False,
    })
    run_result = TestRunResult(
        success=True, exit_code=0,
        summary={"total": 1, "passed": 1, "failed": 0, "error": 0, "skipped": 0},
        cases=[TestCaseResult(test_name="test_add", classname="test_main", status="passed")],
        coverage={"line_coverage": 1.0, "branch_coverage": 0.0, "function_coverage": 1.0},
    )
    executor = _MockExecutor(run_result)
    sources = {"main": "def add(a,b):\n    return a+b\n"}
    report = run_tests(_FakeKG(), sources, "学习加法", mode="generate",
                       module_name="main", executor=executor)
    assert report["rejected"] is False
    assert report["summary"]["passed"] == 1
    assert executor.calls  # 沙箱被调用


def test_run_tests_ast_reject_source():
    """源码含 eval → rejected。"""
    executor = _MockExecutor(TestRunResult(success=False, exit_code=0))
    sources = {"main": "x = eval('1+1')\n"}
    report = run_tests(_FakeKG(), sources, "学习", mode="generate",
                       module_name="main", executor=executor)
    assert report["rejected"] is True
    assert "eval" in report["reject_reason"]
    assert executor.calls == []  # 沙箱未调用


def test_run_tests_llm_degraded(monkeypatch):
    """LLM 未配置 → 零用例 + note。"""
    monkeypatch.setattr(ct, "llm_configured", lambda: False)
    executor = _MockExecutor(TestRunResult(success=False, exit_code=0))
    sources = {"main": "def add(a,b):\n    return a+b\n"}
    report = run_tests(_FakeKG(), sources, "学习", mode="generate",
                       module_name="main", executor=executor)
    assert report["summary"]["total"] == 0
    assert "LLM 未配置" in (report["note"] or "")
    assert executor.calls == []


def test_run_tests_baseline(monkeypatch):
    """baseline 模式: 加载示例项目基线测试，不调 LLM。"""
    called_llm = []
    monkeypatch.setattr(ct, "llm_configured", lambda: True)
    monkeypatch.setattr(ct, "generate_test_cases",
                        lambda *a, **k: called_llm.append(1) or {"degraded": True})
    run_result = TestRunResult(
        success=True, exit_code=0,
        summary={"total": 1, "passed": 1, "failed": 0, "error": 0, "skipped": 0},
        cases=[TestCaseResult(test_name="test_x", classname="test_main", status="passed")],
        coverage={"line_coverage": 0.9, "branch_coverage": 0.5, "function_coverage": 0.8},
    )
    executor = _MockExecutor(run_result)
    report = run_tests(_FakeKG(), {}, "学习", mode="baseline",
                       example_name="simple_crawler", executor=executor)
    # baseline 不调 generate_test_cases
    assert called_llm == []
    assert report["rejected"] is False
    assert executor.calls  # 沙箱被调用执行基线测试


def test_run_tests_baseline_no_example_name():
    """baseline 无 example_name → rejected。"""
    executor = _MockExecutor(TestRunResult(success=False, exit_code=0))
    report = run_tests(_FakeKG(), {}, "学习", mode="baseline", executor=executor)
    assert report["rejected"] is True
    assert "example_name" in report["reject_reason"]
