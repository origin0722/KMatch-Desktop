"""
学习报告 API 路由

POST /api/learning/report
  - interactive 模式可视化报告: 按 session_id 补跑 graph_controller + content_generator
    + reviewer，并做有界审核回环 (W7: reviewer 不通过且未超限 → 携 retry_hint
    定向再生再审, 决策语义复用 orchestrator._decide_after_review, 与 demo workflow 同路由)，
    返回三类可视化数据契约 learning_report。
  - 幂等: 首次补跑后缓存 learning_report，同 session 重复调用直接返回 (省 LLM)。

与 demo 模式互补: demo 模式在 assess 一次返回时内联计算 learning_report 嵌入
AssessResponse；interactive 模式 submit 保持轻量 (仅判分+画像+反馈)，报告数据
由本端点按需触发补跑 (B 端进报告页时调用)。
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.agents.content_generator import content_generator_node
from app.agents.graph_controller import graph_controller_node
from app.agents.llm import llm_configured, use_llm_overrides
from app.agents.orchestrator import _decide_after_review
from app.agents.report_builder import build_learning_report
from app.agents.reviewer import reviewer_node
from app.api.diagnostics import _INTERACTIVE_SESSIONS
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

# W7 有界回环轮数上限 (1 首轮 + 1 打回再生; 与 demo workflow max_retries=3 相比更保守,
# interactive 补跑在请求线程内同步执行, 用户等待敏感)
REPORT_MAX_REVIEW_ROUNDS = 2


class LearningReportRequest(BaseModel):
    """可视化报告请求 (interactive 补跑)。"""

    session_id: str = Field(..., description="assess(interactive) + submit 后的 session_id")
    llm_overrides: dict = Field(default=None, description="Spec B: Agent 独立 key 覆写")


class LearningReportResponse(BaseModel):
    """可视化报告响应: 含完整路径/内容/审核产出 + 三类可视化预计算数据。"""

    session_id: str
    profile: dict = Field(default_factory=dict)
    knowledge_graph: dict = Field(default_factory=dict, description="学习路径图谱 (补跑 graph_controller 产出)")
    generated_content: dict = Field(default_factory=dict, description="生成资源 (补跑 content_generator 产出)")
    review_results: dict = Field(default_factory=dict, description="内容审核报告 (最终轮)")
    review_rounds: list = Field(default_factory=list, description="审核轮次轨迹 [{round, passed, overall_score, verdict}]")
    learning_report: dict = Field(default_factory=dict, description="三类可视化预计算数据契约")
    orchestration_log: list = Field(default_factory=list)


def _get_kg(request: Request):
    """从 app.state 获取全局 KnowledgeGraph 单例 (与 diagnostics/graph/project 一致)。"""
    kg = getattr(request.app.state, "kg", None)
    if kg is None:
        raise HTTPException(status_code=503, detail="知识图谱引擎未就绪（Neo4j 未连接）")
    return kg


def _run_report_pipeline(profile: dict, kg, llm_overrides: dict = None) -> dict:
    """补跑 graph_controller → content_generator ⇄ reviewer (有界审核回环)。

    绕过 LangGraph 直接 fold 调用 node 函数 (签名均为 (state)->partial delta)，
    与 submit/feedback 端点风格一致。orchestration_log 手动追加 (绕过 Annotated reducer)。

    W7 回环: reviewer 不通过且 retry < REPORT_MAX_REVIEW_ROUNDS → 打回 content_generator
    (节点内读 review_results.retry_hint 定向再生) 再审；决策语义复用
    orchestrator._decide_after_review (与 demo workflow 完全同一路由, 不再是两套口径)。
    reviewer 自身维护 retry_count 递增, 循环必然有界。

    Spec B: llm_overrides 随 state 下传 — content_generator 的 ThreadPoolExecutor
    worker 线程不继承路由层 use_llm_overrides 设的 ContextVar, 必须经 state.llm_overrides
    由 _safe_generate 在 worker 内 re-set。graph_controller/reviewer 在主线程,
    路由层 use_llm_overrides 已覆盖 (state 里也有, 节点入口 set 为同一值, 无副作用)。
    """
    state = {
        "user_profile": profile,
        "knowledge_graph": {},
        "generated_content": {},
        "content_phase_entered": False,
        "retry_count": 0,
        "max_retries": REPORT_MAX_REVIEW_ROUNDS,
        "orchestration_log": [f"[{datetime.utcnow().isoformat()}] 📊 学习报告: 开始补跑"],
    }
    if llm_overrides:
        state["llm_overrides"] = llm_overrides
    log = list(state["orchestration_log"])

    def _fold(delta: dict) -> None:
        """把 node 返回的 partial delta 合并进 state，追加其日志段。"""
        nonlocal state, log
        if not isinstance(delta, dict):
            return
        seg = delta.get("orchestration_log", [])
        if seg:
            log.extend(seg)
        # 合并非日志字段 (节点返回的 knowledge_graph/generated_content 等)
        for k, v in delta.items():
            if k == "orchestration_log":
                continue
            state[k] = v

    def _review_round_snapshot(round_no: int) -> dict:
        review = state.get("review_results") or {}
        return {
            "round": round_no,
            "passed": review.get("passed"),
            "overall_score": review.get("overall_score"),
            "verdict": review.get("verdict"),
        }

    # ① 路径组装
    _fold(graph_controller_node(kg)(state))
    # ② 内容生成 (置 content_phase_entered=True，reviewer 据此进内容模式)
    _fold(content_generator_node(kg)(state))
    # ③ 首轮内容审核
    _fold(reviewer_node(kg)(state))
    rounds = [_review_round_snapshot(1)]

    # ④ 有界审核回环 (W7): 不通过且未超限 → 定向再生 → 再审
    while _decide_after_review(state) == "content_generator":
        hint = (state.get("review_results") or {}).get("retry_hint") or ""
        log.append(f"[{datetime.utcnow().isoformat()}] 🔁 审核打回 → 携诊断定向再生 (第 {len(rounds) + 1} 轮)")
        _fold(content_generator_node(kg)(state))
        _fold(reviewer_node(kg)(state))
        rounds.append(_review_round_snapshot(len(rounds) + 1))

    log.append(f"[{datetime.utcnow().isoformat()}] ✅ 学习报告: 补跑完成 (审核 {len(rounds)} 轮)")
    state["orchestration_log"] = log
    state["review_rounds"] = rounds
    return state


@router.post("/report", response_model=LearningReportResponse,
             summary="可视化报告 (interactive 补跑路径+内容+审核回环，返回三类可视化数据)")
def learning_report(req: LearningReportRequest, request: Request):
    """interactive 模式可视化报告。

    B 端在 submit 拿到画像后，进报告页时调用本接口:
      - 首次: 补跑 graph_controller/content_generator/reviewer 有界回环 → 组装 learning_report → 缓存
      - 后续: 命中缓存直接返回 (幂等，省 LLM 调用)

    校验序: session(404) → profile(409) → LLM(503) → kg(503) → 补跑。
    W7: 审核不通过时携 retry_hint 定向再生再审 (≤2 轮)，review_rounds 记录轮次轨迹。
    """
    # ① session 存在
    session = _INTERACTIVE_SESSIONS.get(req.session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"会话 {req.session_id} 不存在或已过期（缓存上限 {len(_INTERACTIVE_SESSIONS)}）",
        )

    # ② profile 已缓存 (submit 后回写)
    profile = session.get("profile")
    if not profile:
        raise HTTPException(
            status_code=409,
            detail="画像未就绪：请先 POST /api/diagnostics/submit 提交答题产出画像",
        )

    # ③ 幂等: 已缓存报告 → 直接返回
    cached = session.get("learning_report_cache")
    if cached:
        logger.info("学习报告命中缓存 session=%s", req.session_id)
        return LearningReportResponse(
            session_id=req.session_id,
            profile=profile,
            knowledge_graph=session.get("knowledge_graph", {}),
            generated_content=session.get("generated_content", {}),
            review_results=session.get("review_results", {}),
            review_rounds=session.get("report_review_rounds", []),
            learning_report=cached,
            orchestration_log=session.get("report_log", []),
        )

    # ④ 环境依赖 — 预检须在 overrides 作用域内 (UI 独立 key 可见, 否则配了也报未配置)
    with use_llm_overrides(req.llm_overrides):
        if not llm_configured():
            raise HTTPException(status_code=503, detail="LLM 未配置，无法补跑内容生成")
    kg = _get_kg(request)

    # ⑤ 补跑 (Spec B: 用 use_llm_overrides 包裹主线程节点; llm_overrides 经 state
    # 下传供 content_generator worker 线程 re-set ContextVar)
    try:
        with use_llm_overrides(req.llm_overrides):
            state = _run_report_pipeline(profile, kg, llm_overrides=req.llm_overrides)
    except Exception as e:
        logger.error("学习报告补跑失败 session=%s", req.session_id, exc_info=True)
        raise HTTPException(status_code=500, detail=f"报告补跑失败: {e}")

    knowledge_graph = state.get("knowledge_graph", {})
    generated_content = state.get("generated_content", {})
    review_results = state.get("review_results", {})
    review_rounds = state.get("review_rounds", [])

    learning_report = build_learning_report(
        profile, knowledge_graph, generated_content, review_results, kg=kg
    )

    # 回写 session 缓存 (供后续 /feedback 及幂等复用)
    session["knowledge_graph"] = knowledge_graph
    session["generated_content"] = generated_content
    session["review_results"] = review_results
    session["report_review_rounds"] = review_rounds
    session["learning_report_cache"] = learning_report
    session["report_log"] = state.get("orchestration_log", [])

    logger.info("学习报告补跑完成 session=%s resources=%d rounds=%d passed=%s",
                req.session_id,
                len(generated_content.get("resources", [])),
                len(review_rounds),
                review_results.get("passed"))

    return LearningReportResponse(
        session_id=req.session_id,
        profile=profile,
        knowledge_graph=knowledge_graph,
        generated_content=generated_content,
        review_results=review_results,
        review_rounds=review_rounds,
        learning_report=learning_report,
        orchestration_log=state.get("orchestration_log", []),
    )
