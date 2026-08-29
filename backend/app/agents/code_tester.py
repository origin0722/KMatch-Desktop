"""
代码测试 Agent (Code Tester)

场景二 Step 6②: 用户提交修改后代码 → 代码测试Agent自动生成 Pytest 用例并执行，
输出通过率与覆盖率报告，反向标注图谱风险节点。

计划书 W6 A 端 ④「对接代码测试Agent：生成Pytest单元测试用例并执行」。

图谱驱动测试生成 (赛题"知识图谱为共享事实底座"在 code_tester 的体现):
  - 策略1 白盒: 基于 code_parser 提取的 CodeEntity 函数签名 (params/return_type/docstring)
    生成 happy path / 边界 / 异常测试
  - 策略2 误区: 基于领域节点 common_mistakes 生成验证用例
  测试用例基于图谱接口定义生成，而非 LLM 凭空写。

沙箱分层:
  - 第一层 AST 安全预检 (复用 code_reviewer.hard_check_code_safety，完全满足 06 prompt
    "所有代码先经过 AST 安全检查")，源码 + 测试代码双预检
  - 第二层 SubprocessSandboxExecutor 执行 pytest --cov (诚实限制见 sandbox.py)

反向标注闭环:
  失败用例 → related_node (entity_id) → kg.annotate_risk 回写 ProjectEntity risk_level
  → get_project_graph 返回前端 Function 节点染红

本批只做 API 能力 (独立可测)，不编排 with_project workflow。
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.code_reviewer import hard_check_code_safety
from app.agents.knowledge_context import build_knowledge_context
from app.agents.llm import get_default_chat_model, llm_configured, use_llm_overrides
from app.agents.sandbox import (
    SandboxExecutor,
    SubprocessSandboxExecutor,
    select_executor,
    TestCaseResult,
    TestRunResult,
    parse_coverage_json,
)
from app.code_parser import CodeEntity, parse_project
from app.code_parser.loader import EXAMPLE_PROJECTS_DIR
from app.config import settings
from app.graph.engine import KnowledgeGraph
from app.utils.json_utils import parse_llm_json
from app.utils.logging import get_logger

logger = get_logger(__name__)

# 沙箱预算 (诚实标注: 单测 5s 近似为整套 timeout，精确单测超时需 pytest-timeout 未引入)
PER_TEST_TIMEOUT_SEC = 5
MAX_TEST_BUDGET_SEC = 60
# issue-46: baseline 模式 (metadata 空) 无逐用例估算, 用保底预算防整套仅 5s 误判超时
BASELINE_TIMEOUT_SEC = 20


# ============================================================
# 上下文构建 (图谱驱动生成输入)
# ============================================================

def _build_signature_context(entities: list[CodeEntity], module_name: str) -> str:
    """把 CodeEntity 函数签名格式化为 LLM 上下文 — 策略1白盒生成的核心输入。

    只取该模块的 function/method，含 qualified_name/entity_id/params/return_type/docstring/source_code。
    """
    lines = []
    for e in entities:
        if e.module_name != module_name:
            continue
        if e.kind not in ("function", "method"):
            continue
        params_str = ", ".join(
            f"{p['name']}"
            + (f": {p['annotation']}" if p.get("annotation") else "")
            + (f"={p['default']}" if p.get("default") is not None else "")
            for p in e.params
        )
        lines.append(f"### {e.qualified_name} (entity_id: {e.entity_id})")
        lines.append(f"  签名: {e.name}({params_str})"
                     + (f" -> {e.return_type}" if e.return_type else ""))
        if e.docstring:
            lines.append(f"  文档: {e.docstring}")
        if e.source_code:
            # 截断超长源码
            src = e.source_code if len(e.source_code) <= 800 else e.source_code[:800] + "..."
            lines.append(f"  源码:\n{src}")
        lines.append("")
    return "\n".join(lines) if lines else "(无函数)"


def _retrieve_knowledge(kg: KnowledgeGraph, target_direction: str,
                        knowledge_node_ids: Optional[list[str]] = None,
                        top_k: int = 5) -> list[dict]:
    """检索领域知识点: 优先 node_ids (get_node)，否则 semantic_search(target_direction)。"""
    if knowledge_node_ids:
        nodes = []
        for nid in knowledge_node_ids:
            n = kg.get_node(nid)
            if n:
                nodes.append(n)
        return nodes
    try:
        return kg.semantic_search(query=target_direction, top_k=top_k)
    except Exception:
        logger.warning("领域知识语义检索失败，按通用规范生成测试", exc_info=True)
        return []


# ============================================================
# LLM 测试生成 (图谱驱动)
# ============================================================

def llm_generate_tests(entities: list[CodeEntity], knowledge_nodes: list[dict],
                       target_direction: str, module_name: str,
                       llm_overrides: dict = None,
                       correction_hint: str = "") -> tuple[str, list[dict]]:
    """LLM 据图谱函数签名 + common_mistakes 生成 pytest 代码 + 元数据。

    Returns:
        (test_code, test_metadata[]) — metadata: {test_name, related_node, related_keypoint, scenario}

    Spec B: llm_overrides 非空时用独立 key。
    W6: correction_hint 非空时注入上轮失败修正要求 (场景二编排打回循环的定向再生,
    对齐 content_generator 的 retry_hint 模式 — 盲重跑变携带诊断再生)。
    """
    with use_llm_overrides(llm_overrides):
        model = get_default_chat_model()
        correction_block = (
            f"\n\n【上轮失败修正要求——定向再生】\n{correction_hint}\n"
            "重点修正上述问题 (尤其避免再次触发同类失败), 其余结构保持原样。"
            if correction_hint else ""
        )
        system = SystemMessage(content=(
            "你是 KMatch 代码测试 Agent。基于知识图谱中的函数签名（白盒）与领域 common_mistakes，"
            f"为 Python 模块 {module_name} 生成 Pytest 单元测试。"
            "每个被测函数至少生成：正常输入(happy path)、边界值(boundary)、异常输入(exception) 三类用例；"
            "针对每个 common_mistake 额外生成一个验证用例(mistake)。"
            "测试命名严格遵循 test_<function_name>_<scenario>。"
            "测试须 self-contained，从模块 import 被测对象，禁止使用 network/subprocess/os.system/eval/exec/pickle。"
            "先输出完整可执行的 ```python 测试代码块，再输出 ```json 元数据块。"
            + correction_block
        ))
        user = HumanMessage(content=(
            f"模块名: {module_name}\n"
            f"开发目标: {target_direction}\n\n"
            f"待测函数（来自知识图谱接口定义）:\n{_build_signature_context(entities, module_name)}\n\n"
            f"相关领域知识（common_mistakes 用于针对性测试）:\n{build_knowledge_context(knowledge_nodes, include_key_points=False)}\n\n"
            "输出格式:\n"
            "```python\n# 完整测试代码，from " + module_name + " import ...\n```\n"
            "```json\n{\"tests\":[{\"test_name\":\"test_xxx_happy_path\","
            "\"related_node\":\"<entity_id>\",\"related_keypoint\":\"<PY-xxx 或 null>\","
            "\"scenario\":\"happy_path|boundary|exception|mistake\"}]}\n```"
        ))
        resp = model.invoke([system, user])
        text = resp.content if isinstance(resp.content, str) else str(resp.content)
        return _extract_test_code_and_metadata(text)


def _extract_test_code_and_metadata(text: str) -> tuple[str, list[dict]]:
    """从 LLM 响应提取 python 代码块 + json 元数据块。"""
    # python 代码块 (非贪婪取第一个)
    py_match = re.search(r"```python\s*\n(.*?)```", text, re.DOTALL)
    test_code = py_match.group(1).strip() if py_match else ""

    # json 元数据块
    json_match = re.search(r"```json\s*\n(.*?)```", text, re.DOTALL)
    metadata: list[dict] = []
    if json_match:
        try:
            data = json.loads(json_match.group(1).strip())
            metadata = data.get("tests", []) if isinstance(data, dict) else []
        except (ValueError, TypeError):
            metadata = []
    # 兜底: 若无 json 块，尝试整段 parse_llm_json
    if not metadata:
        parsed = parse_llm_json(text)
        if isinstance(parsed, dict):
            metadata = parsed.get("tests", [])
    return test_code, metadata


def generate_test_cases(kg: KnowledgeGraph, entities: list[CodeEntity],
                        target_direction: str, knowledge_node_ids: Optional[list[str]],
                        module_name: str, llm_overrides: dict = None,
                        correction_hint: str = "") -> dict:
    """编排: 知识检索 + LLM 生成 + 降级。

    Returns:
        {test_code, test_metadata, knowledge_nodes, degraded}
        LLM 未配置 → degraded=True, test_code=None。
    """
    knowledge_nodes = _retrieve_knowledge(kg, target_direction, knowledge_node_ids)
    if not llm_configured():
        return {"test_code": None, "test_metadata": [], "knowledge_nodes": knowledge_nodes,
                "degraded": True}
    try:
        test_code, test_metadata = llm_generate_tests(
            entities, knowledge_nodes, target_direction, module_name,
            llm_overrides=llm_overrides, correction_hint=correction_hint,
        )
    except Exception:
        logger.warning("LLM 测试生成失败", exc_info=True)
        return {"test_code": None, "test_metadata": [], "knowledge_nodes": knowledge_nodes,
                "degraded": True}
    return {"test_code": test_code, "test_metadata": test_metadata,
            "knowledge_nodes": knowledge_nodes, "degraded": False}


# ============================================================
# AST 安全预检 (复用 hard_check_code_safety)
# ============================================================

def _ast_precheck_reject(*codes: str) -> Optional[str]:
    """对源码 + 生成测试代码做 AST 安全预检。

    复用 hard_check_code_safety；命中 high severity security 问题 → 返回拒绝原因，否则 None。
    """
    for code in codes:
        if not code:
            continue
        issues = hard_check_code_safety(code)
        high_security = [i for i in issues
                         if i.get("dimension") == "security" and i.get("severity") == "high"]
        if high_security:
            problems = "；".join(i.get("problem", "") for i in high_security)
            return f"检测到高危调用，拒绝执行: {problems}"
    return None


# ============================================================
# 报告组装 (06 prompt 字段映射)
# ============================================================

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _empty_summary() -> dict:
    return {"total": 0, "passed": 0, "failed": 0, "error": 0, "skipped": 0}


def _empty_coverage() -> dict:
    return {"line_coverage": 0.0, "branch_coverage": 0.0, "function_coverage": 0.0}


def _parse_assert_expected_actual(message: Optional[str]) -> tuple[str, str]:
    """从 failure message 启发式解析 assert 语句的 expected/actual (best-effort)。"""
    if not message:
        return "", ""
    # 匹配 assert X == Y / assert X != Y
    m = re.search(r"assert\s+(.+?)\s*(==|!=)\s*(.+)", message)
    if m:
        return m.group(1).strip(), m.group(3).strip().split("\n")[0]
    return "", message.strip().split("\n")[0] if message else ""


def _build_failed_tests(run_result: TestRunResult, test_metadata: list[dict],
                        entities: list[CodeEntity], knowledge_nodes: list[dict]) -> list[dict]:
    """组装 failed_tests[] (06 prompt 字段)。"""
    # test_name → metadata (LLM 生成模式); baseline 模式 metadata 空
    meta_by_name = {m.get("test_name"): m for m in test_metadata if isinstance(m, dict)}
    # entity_id → common_mistakes (用于 suggestion)
    kp_by_id = {}
    for n in knowledge_nodes:
        nid = n.get("node_id") or n.get("id")
        if nid:
            kp_by_id[nid] = n

    failed_tests = []
    for case in run_result.cases:
        if case.status not in ("failed", "error"):
            continue
        meta = meta_by_name.get(case.test_name) or meta_by_name.get(case.test_name.split(".")[-1]) or {}
        expected, actual = _parse_assert_expected_actual(case.message)
        related_node = meta.get("related_node") or _infer_related_node(case, entities)
        related_keypoint = meta.get("related_keypoint")
        scenario = meta.get("scenario", "")

        # suggestion: 优先 common_mistakes，否则 scenario 文案
        suggestion = ""
        if related_keypoint and related_keypoint in kp_by_id:
            mistakes = kp_by_id[related_keypoint].get("common_mistakes", [])
            if mistakes:
                suggestion = f"参考 {related_keypoint} 常见误区: {mistakes[0]}"
        if not suggestion and scenario:
            suggestion = f"检查 {case.test_name} 的 {scenario} 场景"

        failed_tests.append({
            "test_name": case.test_name,
            "status": case.status,
            "error_type": case.error_type,
            "expected": expected,
            "actual": actual,
            "suggestion": suggestion,
            "related_node": related_node,
            "related_keypoint": related_keypoint,
        })
    return failed_tests


def _infer_related_node(case: TestCaseResult, entities: list[CodeEntity]) -> Optional[str]:
    """baseline 模式从 test_name 反推被测函数 → entity_id。

    test_name 形如 test_parse_page_happy_path → 找 parse_page 函数。
    """
    name = case.test_name.split(".")[-1]
    for e in entities:
        if e.kind in ("function", "method") and e.name in name:
            return e.entity_id
    return None


def build_test_report(run_result: TestRunResult, test_metadata: list[dict],
                      entities: list[CodeEntity], knowledge_nodes: list[dict],
                      rejected: bool = False, reject_reason: Optional[str] = None,
                      note: Optional[str] = None) -> dict:
    """组装 06 prompt 测试报告。"""
    if rejected:
        return {
            "test_report_id": str(uuid.uuid4()),
            "tested_at": _now_iso(),
            "coverage": _empty_coverage(),
            "summary": _empty_summary(),
            "failed_tests": [],
            "risk_nodes": [],
            "regression": {"previously_passing_now_failing": [], "newly_passing": []},
            "rejected": True,
            "reject_reason": reject_reason,
            "note": note,
        }

    coverage = run_result.coverage or _empty_coverage()
    # 确保三键齐全
    coverage = {
        "line_coverage": coverage.get("line_coverage", 0.0),
        "branch_coverage": coverage.get("branch_coverage", 0.0),
        "function_coverage": coverage.get("function_coverage", 0.0),
    }
    failed_tests = _build_failed_tests(run_result, test_metadata, entities, knowledge_nodes)

    return {
        "test_report_id": str(uuid.uuid4()),
        "tested_at": _now_iso(),
        "coverage": coverage,
        "summary": run_result.summary,
        "failed_tests": failed_tests,
        "risk_nodes": [],  # 由 annotate_failed_entities 填充
        "regression": {"previously_passing_now_failing": [], "newly_passing": []},
        "rejected": False,
        "reject_reason": None,
        "note": note,
    }


# ============================================================
# 反向标注闭环
# ============================================================

def annotate_failed_entities(kg: KnowledgeGraph, project_id: Optional[str],
                             run_result: TestRunResult, test_metadata: list[dict],
                             knowledge_nodes: list[dict],
                             entities: Optional[list[CodeEntity]] = None) -> list[dict]:
    """失败用例 → kg.annotate_risk + link_entity_to_knowledge，聚合返回 risk_nodes[]。

    risk_level 启发式: 同 entity 失败用例≥2 或该 entity 全部用例失败 → high；否则 medium。
    project_id=None 或实体未落 Neo4j: annotate_risk 的 MATCH 静默无操作，不报错。

    entities: code_parser 解析的 CodeEntity 列表, 用于失败用例 metadata 缺 related_node
    时从 test_name 反推被测函数 (BUG 修复: 此前误传 knowledge_nodes[dict] 当 entities,
    对 dict 取 .kind 致 AttributeError 中断整个测试接口)。
    """
    # entities 缺省空: metadata 完备时无需反推; run_tests 调用必传 parsed.entities
    entities = entities or []
    failed_tests = _build_failed_tests(run_result, test_metadata, entities, knowledge_nodes)
    if not failed_tests:
        return []

    # 聚合: entity_id → [失败 test_name]
    by_entity: dict[str, list[str]] = {}
    keypoints_by_entity: dict[str, Optional[str]] = {}
    for ft in failed_tests:
        eid = ft.get("related_node")
        if not eid:
            continue
        by_entity.setdefault(eid, []).append(ft["test_name"])
        # 取非空 related_keypoint (多条失败可能部分为空，保留有值的)
        kp = ft.get("related_keypoint")
        if kp and not keypoints_by_entity.get(eid):
            keypoints_by_entity[eid] = kp

    risk_nodes = []
    for eid, test_names in by_entity.items():
        n_fail = len(test_names)
        risk_level = "high" if n_fail >= 2 else "medium"
        reason = f"{n_fail}个测试用例未通过: {', '.join(test_names[:3])}"
        recommendation = "重新学习该函数相关知识点并修正实现"

        # 回写 Neo4j (project_id=None 或实体未入库时静默)
        try:
            kg.annotate_risk(eid, risk_level, reason)
        except Exception:
            logger.warning("风险标注写回失败: %s", eid, exc_info=True)
        kp = keypoints_by_entity.get(eid)
        if kp:
            try:
                kg.link_entity_to_knowledge(eid, kp)
            except Exception:
                logger.warning("知识点关联失败: %s→%s", eid, kp, exc_info=True)

        risk_nodes.append({
            "node_id": eid,
            "risk_level": risk_level,
            "reason": reason,
            "recommendation": recommendation,
        })
    return risk_nodes


# ============================================================
# 基线模式
# ============================================================

def _load_baseline_suite(example_name: str) -> tuple[dict[str, str], str]:
    """加载示例项目源码 + test_main.py。

    load_example_project 跳过 test_*.py，这里单独读 test_main.py。
    """
    project_dir = EXAMPLE_PROJECTS_DIR / example_name
    if not project_dir.is_dir():
        raise FileNotFoundError(f"示例项目不存在: {example_name}")
    # 源码 (非 test)
    sources: dict[str, str] = {}
    for py in sorted(project_dir.glob("*.py")):
        if py.name.startswith("test_"):
            continue
        sources[py.stem] = py.read_text(encoding="utf-8")
    # 基线测试
    test_file = project_dir / "test_main.py"
    if not test_file.exists():
        raise FileNotFoundError(f"示例项目 {example_name} 无 test_main.py 基线测试")
    test_code = test_file.read_text(encoding="utf-8")
    return sources, test_code


# ============================================================
# 顶层编排
# ============================================================

def run_tests(kg: KnowledgeGraph, sources: dict[str, str], target_direction: str,
              knowledge_node_ids: Optional[list[str]] = None,
              mode: str = "generate", project_id: Optional[str] = None,
              module_name: str = "main",
              example_name: Optional[str] = None,
              executor: Optional[SandboxExecutor] = None,
              llm_overrides: dict = None,
              correction_hint: str = "") -> dict:
    """顶层编排: 解析→AST预检源码→(生成/基线)→AST预检测试→沙箱执行→报告→反向标注。

    Args:
        sources: {module_name: source} (baseline 模式可由 example_name 加载覆盖)
        example_name: baseline 模式必需，从示例项目加载源码 + test_main.py
        correction_hint: W6 场景二编排打回再生时注入的上轮失败修正要求
    Returns:
        06 prompt 测试报告 dict。
    """
    # 沙箱执行器: 调用方可注入; 否则按 SANDBOX_MODE 选 (auto: Docker 可用则 Docker, 否则子进程)
    if executor is None:
        try:
            executor = select_executor()
        except ValueError as e:
            return build_test_report(
                TestRunResult(success=False, exit_code=0), [], [], [],
                rejected=True, reject_reason=str(e),
            )
    pid = project_id or "test-temp"

    # baseline 模式: 从示例项目加载源码 + 基线测试 (覆盖传入的 sources)
    if mode == "baseline":
        if not example_name:
            return build_test_report(
                TestRunResult(success=False, exit_code=0), [], [], [],
                rejected=True, reject_reason="基线模式需要 example_name",
            )
        try:
            sources, test_code = _load_baseline_suite(example_name)
        except FileNotFoundError:
            return build_test_report(
                TestRunResult(success=False, exit_code=0), [], [], [],
                rejected=True, reject_reason=f"示例项目 {example_name} 或其基线测试不存在",
            )
        module_name = next(iter(sources), "main")

    # 1. 解析代码 → entities
    parsed = parse_project(pid, sources)
    entities = parsed.entities

    # 2. AST 预检源码 (第一层安全)
    reject = _ast_precheck_reject(*sources.values())
    if reject:
        return build_test_report(
            TestRunResult(success=False, exit_code=0), [], entities, [],
            rejected=True, reject_reason=reject,
            note="源码 AST 预检未通过，未执行测试",
        )

    # 3. generate 模式: LLM 生成测试 (baseline 已加载 test_code)
    test_metadata: list[dict] = []
    knowledge_nodes: list[dict] = []
    if mode != "baseline":
        gen = generate_test_cases(kg, entities, target_direction, knowledge_node_ids,
                                  module_name, llm_overrides=llm_overrides,
                                  correction_hint=correction_hint)
        knowledge_nodes = gen["knowledge_nodes"]
        if gen["degraded"]:
            return build_test_report(
                TestRunResult(success=False, exit_code=0), [], entities, knowledge_nodes,
                note="LLM 未配置，测试生成不可用",
            )
        test_code = gen["test_code"]
        test_metadata = gen["test_metadata"]
        if not test_code:
            return build_test_report(
                TestRunResult(success=False, exit_code=0), [], entities, knowledge_nodes,
                note="测试生成失败，未产出有效测试代码",
            )
        # AST 预检测试代码 (LLM 也可能生成危险调用)
        test_reject = _ast_precheck_reject(test_code)
        if test_reject:
            return build_test_report(
                TestRunResult(success=False, exit_code=0), test_metadata, entities, knowledge_nodes,
                rejected=True, reject_reason=test_reject,
                note="生成的测试代码 AST 预检未通过",
            )

    # 4. tempfile 写文件 + 执行
    workdir = Path(tempfile.mkdtemp(prefix="kmatch_test_"))
    try:
        # 写各模块源码
        for mname, src in sources.items():
            (workdir / f"{mname}.py").write_text(src, encoding="utf-8")
        test_filename = f"test_{module_name}.py"
        (workdir / test_filename).write_text(test_code, encoding="utf-8")

        # 5. 估算 timeout (issue-46: baseline/metadata 为空时用保底预算, 防小套件 5s 误判超时)
        if test_metadata:
            timeout = min(PER_TEST_TIMEOUT_SEC * max(len(test_metadata), 1), MAX_TEST_BUDGET_SEC)
        else:
            timeout = min(BASELINE_TIMEOUT_SEC, MAX_TEST_BUDGET_SEC)

        # 6. 执行 (重新解析以拿含 source_code 的 entities 供 function coverage)
        run_result = executor.run(workdir, module_name, test_filename,
                                  cov_module=module_name, timeout=timeout)

        # coverage function 覆盖率需 entities (用沙箱返回的 coverage 重算 function)
        if run_result.coverage and run_result.coverage.get("files") is not None:
            # SubprocessSandboxExecutor 已算 (但未传 entities)；这里补算 function_coverage
            try:
                import json as _json
                cov_path = workdir / "coverage.json"
                if cov_path.exists():
                    from app.agents.sandbox import _compute_function_coverage, _summarize_files
                    raw = _json.loads(cov_path.read_text(encoding="utf-8"))
                    files = raw.get("files", {})
                    func_cov = _compute_function_coverage(entities, files)
                    if func_cov is not None:
                        run_result.coverage["function_coverage"] = round(func_cov, 4)
            except Exception:
                pass

        # 7. 报告
        note = None
        if not run_result.success and run_result.timed_out:
            note = f"测试执行超时 ({timeout}s)，可能存在无限循环"
        elif not run_result.success:
            note = f"测试执行异常: {run_result.error or run_result.stderr[:200]}"
        report = build_test_report(run_result, test_metadata, entities, knowledge_nodes, note=note)

        # 8. 反向标注
        report["risk_nodes"] = annotate_failed_entities(
            kg, project_id, run_result, test_metadata, knowledge_nodes, entities,
        )
        return report
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
