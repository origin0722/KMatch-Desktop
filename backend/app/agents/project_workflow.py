"""
场景二·项目二次开发 LangGraph 编排 (W6)

此前 code_reviewer / code_tester 能力齐备但只有直调 API (两文件头注释自认
"编排属后续步骤"), workflow_def 的 scene2-project 仅是数据定义无执行器。
本模块补上真实执行器, 兑现赛题「分析-生成-校验-决策」闭环在场景二的多 Agent 编排:

  project_review → (test → test | repair | finish) → repair → finish
                   │        └ 打回循环: 生成的测试代码自身未过 AST 预检
                   │          (infra 失败, 非断言失败) 且 retry<max → 携失败 hint
                   │          定向再生 (correction_hint, 对齐 content_generator 模式)
                   └ 语法级 critical (源码无法审查/测试) → 跳过测试直达修复指引

断言失败 (测试跑通但有用例失败) 是真实项目问题 — 不打回, 进 repair 产出
面向用户的定向修复指引 (LLM 生成, 未配置 LLM 时确定性兜底)。

状态: 复用 AgentState (project_id/project_graph 契约字段自此被真实消费)。
"""

from datetime import datetime
from functools import wraps
from typing import Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from app.agents.code_reviewer import review_code
from app.agents.code_tester import build_test_report, run_tests, TestRunResult
from app.agents.llm import get_default_chat_model, llm_configured, safe_llm_call, use_llm_overrides
from app.agents.state import AgentState
from app.graph.engine import KnowledgeGraph
from app.utils.json_utils import parse_llm_json
from app.utils.logging import get_logger

logger = get_logger(__name__)

# 多文件审查上限 (按文件长度取最大 N 个; 审查是逐文件 LLM 调用, 控成本)
MAX_REVIEW_FILES = 3
# 语法级 critical 判定关键词 (review_code 语法错误时 retry_hint 明示)
_SYNTAX_CRITICAL_MARK = "语法错误"


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def use_llm_overrides_state(fn):
    """节点包装: 入口把 state.llm_overrides set 进 ContextVar (Spec B 透传, 主线程路径)。"""

    @wraps(fn)
    def _wrapper(state):
        overrides = state.get("llm_overrides")
        if overrides:
            from app.agents.llm import _current_overrides
            token = _current_overrides.set(overrides)
            try:
                return fn(state)
            finally:
                _current_overrides.reset(token)
        return fn(state)
    return _wrapper


def _select_review_files(project_files: dict) -> list[tuple[str, str]]:
    """取最大的 N 个文件审查 (大项目全审成本失控; 小项目通常全部入选)。"""
    items = [(k, v) for k, v in (project_files or {}).items() if isinstance(v, str) and v.strip()]
    items.sort(key=lambda kv: len(kv[1]), reverse=True)
    return items[:MAX_REVIEW_FILES]


def _merged_review(reviews: list[dict]) -> dict:
    """多文件审查结果合并: 最差者代表整体 (任一未过即未过)。"""
    if not reviews:
        return {"passed": False, "overall_score": 0.0, "verdict": "reject",
                "retry_hint": "无有效源码可审查", "reviewed_at": _now_iso()}
    passed = all(r.get("passed") for r in reviews)
    worst = min(reviews, key=lambda r: r.get("overall_score", 0.0) or 0.0)
    hints = [r.get("retry_hint") for r in reviews if r.get("retry_hint")]
    return {
        "passed": passed,
        "overall_score": worst.get("overall_score", 0.0),
        "threshold": worst.get("threshold"),
        "dimensions": worst.get("dimensions", {}),
        "verdict": "pass" if passed else (worst.get("verdict") or "reject"),
        "retry_hint": "；".join(dict.fromkeys(hints))[:800],
        "reviewed_at": _now_iso(),
    }


def project_review_node(kg: KnowledgeGraph):
    """代码审查节点: 对 project_files 逐文件调 review_code (并发读图, LLM 串行简控)。"""

    @use_llm_overrides_state
    def _node(state) -> dict:
        files = _select_review_files(state.get("project_files"))
        log = [f"[{_now_iso()}] 🔍 代码审查: {len(files)} 个文件 (cap={MAX_REVIEW_FILES})"]
        overrides = state.get("llm_overrides")
        reviews = []
        for name, code in files:
            try:
                r = review_code(kg, code, state.get("target_direction", ""),
                                llm_overrides=overrides)
                r["file"] = name
                reviews.append(r)
                log.append(f"  - {name}: passed={r.get('passed')} score={r.get('overall_score')}")
            except Exception as e:  # noqa: BLE001 单文件失败不阻断
                logger.warning("pipeline 审查失败 file=%s", name, exc_info=True)
                reviews.append({"file": name, "passed": False, "overall_score": 0.0,
                                "verdict": "reject", "retry_hint": f"审查异常: {e}",
                                "reviewed_at": _now_iso()})
                log.append(f"  - {name}: 审查异常 {e}")
        merged = _merged_review(reviews)
        log.append(f"[{_now_iso()}] 🔍 审查汇总: passed={merged['passed']} score={merged['overall_score']}")
        return {"reviews": reviews, "review_results": merged, "orchestration_log": log}

    return _node


def _is_syntax_critical(reviews: list[dict]) -> bool:
    """任一文件审查命中语法级 critical (retry_hint 含"语法错误") → 跳过测试。"""
    return any(_SYNTAX_CRITICAL_MARK in (r.get("retry_hint") or "") for r in reviews)


def _decide_after_review(state) -> Literal["test", "repair", "finish"]:
    """审查出边: 语法级 critical → repair (跳过测试)；通过 → test (验证行为)；其他 → test。"""
    reviews = state.get("reviews") or []
    if not reviews:
        return "finish"
    # 通过也进 test: 审查通过 ≠ 行为正确, 测试是行为校验 (赛题"分析-校验"闭环)
    if _is_syntax_critical(reviews):
        return "repair"
    return "test"


def test_node(kg: KnowledgeGraph):
    """代码测试节点: run_tests (生成测试 + 沙箱执行)。

    打回再生: state 中已有被拒报告 (rejected) 时, 从其 reject_reason 推导
    correction_hint 定向再生 (条件边不能改状态, hint 在节点内推导)。
    """

    @use_llm_overrides_state
    def _node(state) -> dict:
        prev = state.get("test_report") or {}
        hint = ""
        if prev.get("rejected"):
            hint = (f"上轮生成的测试代码未通过安全预检: {prev.get('reject_reason')}。"
                    "请避免触发高危调用检测, 修正测试代码写法后再生成。")
        log = [f"[{_now_iso()}] 🧪 代码测试: 生成+执行"
               + (f" (第{state.get('retry_count', 0) + 1}次, 定向再生)" if hint else "")]
        overrides = state.get("llm_overrides")
        try:
            report = run_tests(
                kg, state.get("project_files") or {}, state.get("target_direction", ""),
                mode="generate", project_id=state.get("project_id"),
                llm_overrides=overrides, correction_hint=hint,
            )
        except Exception as e:  # noqa: BLE001
            logger.error("pipeline 测试执行失败", exc_info=True)
            report = build_test_report(TestRunResult(success=False, exit_code=0), [], [], [],
                                       rejected=True, reject_reason=f"测试执行异常: {e}")
        sm = report.get("summary") or {}
        log.append(f"[{_now_iso()}] 🧪 测试结果: {sm.get('passed', 0)}/{sm.get('total', 0)} 通过"
                   + (f" (rejected: {report.get('reject_reason')})" if report.get("rejected") else ""))
        # 打回循环计数: 每次 test 执行 +1, _decide_after_test 据此判定超限
        return {"test_report": report, "retry_count": state.get("retry_count", 0) + 1,
                "orchestration_log": log}

    return _node


def _decide_after_test(state) -> Literal["test", "repair", "finish"]:
    """测试出边:
    - 生成测试自身未过 AST 预检 (rejected, infra 失败) 且 retry<max → 打回 test 定向再生
      (循环真实有效: 重生成测试代码, 不依赖用户改代码)
    - rejected 但超限 → repair
    - 有断言失败 (真实项目问题) → repair
    - 全过 / 降级空报告 (LLM 未配置等) → finish
    """
    report = state.get("test_report") or {}
    retry = state.get("retry_count", 0)
    max_r = state.get("max_retries", 2)
    if report.get("rejected"):
        if retry < max_r:
            return "test"
        return "repair"
    failed = report.get("failed_tests") or []
    if failed:
        return "repair"
    return "finish"


def repair_node(kg: KnowledgeGraph):
    """综合裁决节点: 审查问题 + 失败用例 → LLM 定向修复指引 (LLM 不可用时确定性兜底)。"""

    @use_llm_overrides_state
    def _node(state) -> dict:
        log = [f"[{_now_iso()}] 🛠 修复指引: 综合审查+测试产出"]
        issues = _collect_issues(state)
        overrides = state.get("llm_overrides")
        guidance = None
        if llm_configured() and issues:
            prompt = _build_repair_prompt(state.get("target_direction", ""), issues)
            model = get_default_chat_model()
            ok, res = safe_llm_call(
                lambda: parse_llm_json(model.invoke(prompt).content),
                overrides=overrides, logger=logger, label="repair_guidance")
            if ok and isinstance(res, dict):
                guidance = {
                    "summary": res.get("summary", ""),
                    "guidance": res.get("guidance", []),
                    "source": "llm",
                }
        if guidance is None:
            guidance = {
                "summary": "按以下问题逐项修复 (LLM 未配置, 系统按审查/测试结果确定性汇总)",
                "guidance": issues,
                "source": "deterministic",
            }
        guidance["generated_at"] = _now_iso()
        log.append(f"[{_now_iso()}] 🛠 修复指引完成: {len(guidance.get('guidance', []))} 条 ({guidance['source']})")
        return {"repair_guidance": guidance, "orchestration_log": log}

    return _node


def _collect_issues(state) -> list[dict]:
    """从审查结果 + 测试报告提取待修复问题清单 (title/detail 结构)。"""
    issues = []
    for r in state.get("reviews") or []:
        if r.get("passed"):
            continue
        issues.append({
            "title": f"代码审查未通过: {r.get('file', '源码')}",
            "detail": r.get("retry_hint") or f"overall_score={r.get('overall_score')}",
            "source": "review",
        })
    report = state.get("test_report") or {}
    if report.get("rejected"):
        issues.append({
            "title": "测试未能执行",
            "detail": report.get("reject_reason") or "rejected",
            "source": "test",
        })
    for f in (report.get("failed_tests") or [])[:10]:
        issues.append({
            "title": f"测试失败: {f.get('test_name', '?')}",
            "detail": f.get("suggestion") or f.get("error_type") or "断言失败",
            "source": "test",
        })
    return issues


def _build_repair_prompt(target_direction: str, issues: list[dict]) -> list:
    from langchain_core.messages import HumanMessage, SystemMessage
    import json as _json
    system = SystemMessage(content=(
        "你是 KMatch 场景二综合裁决 Agent。根据代码审查与代码测试结果, 产出面向开发者的"
        "定向修复指引。严格输出 JSON: "
        '{"summary": "一句话总体判断", "guidance": [{"title": "问题", "detail": "怎么修", '
        '"source": "review|test"}]}。guidance 按优先级排序, 最多 8 条; 只基于给定问题, 不臆造。'
    ))
    user = HumanMessage(content=(
        f"开发目标: {target_direction}\n待修复问题:\n{_json.dumps(issues, ensure_ascii=False, indent=2)}"
    ))
    return [system, user]


def pipeline_finish_node(state) -> dict:
    """结束节点: 汇总与审查/测试来源标记。"""
    review = state.get("review_results") or {}
    report = state.get("test_report") or {}
    sm = report.get("summary") or {}
    tested = not report.get("rejected") and bool(report)
    msg = (f"✅ 场景二流水线结束: 审查 passed={review.get('passed')}"
           + (f", 测试 {sm.get('passed', 0)}/{sm.get('total', 0)}" if tested else "")
           + (", 已产出修复指引" if state.get("repair_guidance") else ""))
    return {"orchestration_log": [f"[{_now_iso()}] {msg}"]}


def build_project_workflow(kg: KnowledgeGraph):
    """构建并编译场景二流水线 (review → test 打回循环 → repair 综合裁决)。"""
    workflow = StateGraph(AgentState)

    workflow.add_node("project_review", project_review_node(kg))
    workflow.add_node("test", test_node(kg))
    workflow.add_node("repair", repair_node(kg))
    workflow.add_node("finish", pipeline_finish_node)

    workflow.set_entry_point("project_review")
    workflow.add_conditional_edges(
        "project_review", _decide_after_review,
        {"test": "test", "repair": "repair", "finish": "finish"},
    )
    workflow.add_conditional_edges(
        "test", _decide_after_test,
        {"test": "test", "repair": "repair", "finish": "finish"},
    )
    workflow.add_edge("repair", "finish")
    workflow.add_edge("finish", END)

    return workflow.compile(checkpointer=MemorySaver())
