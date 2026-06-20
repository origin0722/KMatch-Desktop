"""
学情检测 API 路由

POST /api/diagnostics/assess
  - mode=demo: 触发完整工作流（学情检测→画像审核→图谱→生成→内容审核），LLM 自动作答
  - mode=interactive: 仅出题返回，等待前端提交答案（不走工作流）

POST /api/diagnostics/submit
  - interactive 答题提交：判分 → 产画像 → 动态反馈（进阶/降维/补前置）
  - 复用 diagnostics 的 _grade/_build_profile/decide_feedback 纯函数
"""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.agents import make_initial_state
from app.agents.content_generator import regenerate_for_feedback
from app.agents.diagnostics import (
    _build_profile,
    _grade,
    decide_feedback,
    prepare_questions,
)
from app.agents.llm import llm_configured
from app.agents.report_builder import build_learning_report
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

# interactive 会话缓存: session_id → {questions, nodes, target_direction, created_at}
# 开发期内存缓存; 生产环境可换 Redis。TTL 由 _evict 控制 (保留最近 100 条)。
_INTERACTIVE_SESSIONS: dict[str, dict] = {}
_MAX_CACHED_SESSIONS = 100


def _cache_session(session_id: str, data: dict) -> None:
    """缓存 interactive 会话题目，LRU 式淘汰。"""
    if len(_INTERACTIVE_SESSIONS) >= _MAX_CACHED_SESSIONS:
        # 淘汰最早的一条
        oldest = min(_INTERACTIVE_SESSIONS, key=lambda k: _INTERACTIVE_SESSIONS[k]["created_at"])
        _INTERACTIVE_SESSIONS.pop(oldest, None)
    _INTERACTIVE_SESSIONS[session_id] = data


class AssessRequest(BaseModel):
    """学情测评请求。"""

    target_direction: str = Field(..., description="学习目标方向（自然语言）", examples=["Python 基础语法入门"])
    mode: str = Field("demo", description="demo=LLM自动作答跑通闭环; interactive=仅返回题目，前端提交答案")
    known_topics: list = Field(default_factory=list, description="用户自报已学节点 [{node_id, mastery}]")
    scene: str = Field("no_project", description="no_project | with_project")
    max_retries: int = Field(3, description="审核打回最大轮数", ge=1, le=5)


class AssessResponse(BaseModel):
    """学情测评响应 (demo 与 interactive 共用)。

    demo 模式: 全字段填充 (走完整工作流)。
    interactive 模式: 仅 session_id + assessment.questions 填充，
    其余为空 (profile/review_results/knowledge_graph/generated_content={},
    orchestration_log=[])，B 端据 assessment.answers 是否为空判阶段。
    """

    session_id: str
    profile: dict = Field(default_factory=dict, description="用户画像 (interactive 出题阶段为空)")
    review_results: dict = Field(default_factory=dict, description="审核报告 (interactive 出题阶段为空)")
    assessment: dict = Field(default_factory=dict, description="测评明细: demo含判分, interactive仅含题目")
    knowledge_graph: dict = Field(default_factory=dict, description="学习路径图谱 (画像审核通过后组装)")
    generated_content: dict = Field(default_factory=dict, description="生成的学习资源 (内容审核通过后交付)")
    learning_report: dict = Field(default_factory=dict, description="可视化报告数据契约 (三类可视化预计算, demo 填充 / interactive 出题阶段为空)")
    orchestration_log: list = Field(default_factory=list, description="执行日志 (interactive 出题阶段为空)")


class SubmitRequest(BaseModel):
    """interactive 答题提交请求。"""

    session_id: str = Field(..., description="assess(interactive) 返回的 session_id")
    answers: list = Field(..., description="逐题作答，顺序与 questions 一致；选择题给选项内容/字母，判断题给'对'/'错'")


class SubmitResponse(BaseModel):
    """答题提交响应: 判分 + 画像 + 动态反馈。"""

    session_id: str
    profile: dict
    assessment: dict
    feedback: dict = Field(..., description="动态反馈策略: advance/remediate/scaffold")


class FeedbackRequest(BaseModel):
    """动态反馈内容再生请求 (W5 闭环)。"""

    session_id: str = Field(..., description="assess(interactive) 返回的 session_id")
    strategy: Literal["advance", "remediate", "scaffold"] = Field(..., description="动态反馈策略")
    profile: dict = Field(..., description="submit 返回的画像 (含 weak_topics/theory_level)")


class FeedbackResponse(BaseModel):
    """动态反馈内容再生响应。"""

    session_id: str
    strategy: str
    resources: list = Field(default_factory=list, description="针对性再生内容列表")
    node_count: int = Field(0, description="目标节点数")


def _get_kg(request: Request) -> "KnowledgeGraph":  # noqa: F821
    """从 app.state 获取全局 KnowledgeGraph 单例（main.py lifespan 注入）。"""
    kg = getattr(request.app.state, "kg", None)
    if kg is None:
        raise HTTPException(status_code=503, detail="知识图谱引擎未就绪（Neo4j 未连接）")
    return kg


def _get_workflow(request: Request):
    """从 app.state 获取预编译的 LangGraph 工作流（main.py lifespan 注入）。"""
    workflow = getattr(request.app.state, "workflow", None)
    if workflow is None:
        raise HTTPException(status_code=503, detail="多 Agent 工作流未就绪（KG 未连接或编译失败）")
    return workflow


@router.post("/assess", response_model=AssessResponse, summary="学情测评（demo 跑全流程 / interactive 仅出题）")
def assess(req: AssessRequest, request: Request):
    """触发学情测评。

    - **demo**: LLM 自动作答跑通完整工作流（学情检测→画像审核→图谱→生成→内容审核），适合 Postman/curl 验证。
    - **interactive**: 仅出题返回 `assessment.questions`（其余字段为空），前端答题后调 `POST /submit` 判分。
    """
    kg = _get_kg(request)

    # --- interactive 模式: 仅出题，不走工作流 ---
    if req.mode == "interactive":
        try:
            questions, nodes = prepare_questions(kg, req.target_direction, req.known_topics)
        except ValueError as e:
            raise HTTPException(status_code=503, detail=str(e))
        except Exception as e:
            logger.error("interactive 出题失败", exc_info=True)
            raise HTTPException(status_code=500, detail=f"出题失败: {e}")

        session_id = str(uuid.uuid4())
        _cache_session(session_id, {
            "questions": questions,
            "nodes": nodes,
            "target_direction": req.target_direction,
            "known_topics": req.known_topics,
            "created_at": datetime.utcnow().isoformat(),
        })
        logger.info("interactive 出题 session=%s 题数=%d", session_id, len(questions))

        # BUG-033: 出题阶段剥离正确答案 answer + 解析 explanation (含答案线索),
        # 避免提前泄露给前端 (缓存保留完整题目供 submit 判分)。
        _STRIP_KEYS = {"answer", "explanation", "created_at", "source_node_id"}
        questions_for_client = [
            {k: v for k, v in q.items() if k not in _STRIP_KEYS} for q in questions
        ]
        return AssessResponse(
            session_id=session_id,
            assessment={
                "questions": questions_for_client,
                "answers": [],
                "per_node": {},
                "correct_count": 0,
                "total_count": len(questions),
            },
        )

    # --- demo 模式: 走完整工作流 ---
    workflow = _get_workflow(request)
    initial = make_initial_state(
        target_direction=req.target_direction,
        mode=req.mode,
        known_topics=req.known_topics,
        scene=req.scene,
        max_retries=req.max_retries,
    )

    logger.info("收到测评请求 session=%s direction=%s mode=%s",
                initial["session_id"], req.target_direction, req.mode)

    try:
        config = {"configurable": {"thread_id": initial["session_id"]}}
        result = workflow.invoke(initial, config)
    except Exception as e:
        logger.error("测评流程执行失败", exc_info=True)
        raise HTTPException(status_code=500, detail=f"测评流程执行失败: {e}")

    # demo 模式内联计算可视化报告 (三类可视化预计算)，供 B 端 Dashboard/Learning 渲染。
    # interactive 模式报告由 POST /api/learning/report 按需补跑 (submit 保持轻量)。
    report = build_learning_report(
        result.get("user_profile", {}),
        result.get("knowledge_graph", {}),
        result.get("generated_content", {}),
        result.get("review_results", {}),
    )

    return AssessResponse(
        session_id=initial["session_id"],
        profile=result.get("user_profile", {}),
        review_results=result.get("review_results", {}),
        assessment=result.get("assessment", {}),
        knowledge_graph=result.get("knowledge_graph", {}),
        generated_content=result.get("generated_content", {}),
        learning_report=report,
        orchestration_log=result.get("orchestration_log", []),
    )


# ============================================================
# SSE 流式测评 (demo 模式, 推进度防前端超时)
# ============================================================

# 节点名 → 人类可读进度文案 (前端展示)
_NODE_PROGRESS = {
    "diagnostics": "学情检测中（出题→自动作答→判分）",
    "reviewer": "审核中（画像/内容审核）",
    "graph_controller": "组装个性化学习路径中",
    "content_generator": "生成学习内容中（讲义/实操/测试题，最耗时）",
    "finish": "组装可视化报告",
}


def _sse(event: str, data: dict) -> str:
    """格式化 SSE 事件: event: <name>\ndata: <json>\n\n"""
    import json as _json
    return f"event: {event}\ndata: {_json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/assess/stream", summary="学情测评（demo SSE 流式，逐步推送进度，防超时）")
def assess_stream(req: AssessRequest, request: Request):
    """demo 模式 SSE 流式测评。

    解决 demo 全流程 2-4 分钟超前端 60s 超时问题: 用 Server-Sent Events 逐步推送
    节点进度, 前端实时展示 "学情检测中→生成内容中→...", 跑完推最终结果。

    事件流:
      event: start   data: {session_id}
      event: progress data: {node, message, log_tail}
      event: done    data: {完整 AssessResponse}
      event: error   data: {detail}

    前端用 EventSource 或 fetch + ReadableStream 消费。注意 SSE 是 GET 友好,
    但本端点用 POST (带 JSON body), 前端需用 fetch 而非 EventSource。
    """
    import json as _json

    kg = _get_kg(request)
    workflow = _get_workflow(request)

    # interactive 模式不需要流式 (出题快), 仍走原 /assess
    if req.mode == "interactive":
        raise HTTPException(status_code=400, detail="interactive 模式请用 POST /assess (出题快无需流式)")

    initial = make_initial_state(
        target_direction=req.target_direction,
        mode="demo",
        known_topics=req.known_topics,
        scene=req.scene,
        max_retries=req.max_retries,
    )
    session_id = initial["session_id"]
    config = {"configurable": {"thread_id": session_id}}
    logger.info("SSE 测评开始 session=%s direction=%s", session_id, req.target_direction)

    def _event_stream():
        yield _sse("start", {"session_id": session_id, "target_direction": req.target_direction})
        final_state = {}
        try:
            # stream_mode="updates": 每个节点完成时产出 {node_name: state_update}
            for chunk in workflow.stream(initial, config, stream_mode="updates"):
                # chunk 形如 {"diagnostics": {...}} 或 {"reviewer": {...}}
                for node_name, update in chunk.items():
                    if not isinstance(update, dict):
                        continue
                    final_state.update(update)
                    # 取 orchestration_log 尾部 (节点产出的日志)
                    log_tail = []
                    ol = update.get("orchestration_log")
                    if isinstance(ol, list) and ol:
                        log_tail = ol[-3:]
                    message = _NODE_PROGRESS.get(node_name, node_name)
                    yield _sse("progress", {
                        "node": node_name,
                        "message": message,
                        "log_tail": log_tail,
                    })
        except Exception as e:
            logger.error("SSE 测评流程失败 session=%s", session_id, exc_info=True)
            yield _sse("error", {"detail": f"测评流程失败: {e}"})
            return

        # 组装最终结果 (同 /assess demo 分支)
        try:
            report = build_learning_report(
                final_state.get("user_profile", {}),
                final_state.get("knowledge_graph", {}),
                final_state.get("generated_content", {}),
                final_state.get("review_results", {}),
            )
            result = {
                "session_id": session_id,
                "profile": final_state.get("user_profile", {}),
                "review_results": final_state.get("review_results", {}),
                "assessment": final_state.get("assessment", {}),
                "knowledge_graph": final_state.get("knowledge_graph", {}),
                "generated_content": final_state.get("generated_content", {}),
                "learning_report": report,
                "orchestration_log": final_state.get("orchestration_log", []),
            }
            yield _sse("done", result)
            logger.info("SSE 测评完成 session=%s", session_id)
        except Exception as e:
            logger.error("SSE 结果组装失败 session=%s", session_id, exc_info=True)
            yield _sse("error", {"detail": f"结果组装失败: {e}"})

    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # nginx 不缓冲 (开发期无 nginx, 备用)
        },
    )


@router.post("/submit", response_model=SubmitResponse, summary="提交答题（interactive 模式判分+动态反馈）")
def submit(req: SubmitRequest, request: Request):
    """提交 interactive 模式的答题，后端判分并产出画像 + 动态反馈策略。

    流程: 取缓存题目 → _grade 判分 → _build_profile 画像 → decide_feedback 动态反馈。
    """
    _get_kg(request)  # 前置检查: Neo4j 是否就绪

    # _grade 调 LLM 判分，未配置时提前 503 (与 assess interactive 一致)
    if not llm_configured():
        raise HTTPException(status_code=503, detail="LLM 未配置，无法判分（请配置 LLM_API_KEY）")

    session = _INTERACTIVE_SESSIONS.get(req.session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"会话 {req.session_id} 不存在或已过期（interactive 题目缓存上限 {_MAX_CACHED_SESSIONS}）",
        )

    questions = session["questions"]
    nodes = session["nodes"]
    target = session["target_direction"]

    # 答案数量对齐 (缺失补空串，多余截断)
    answers = (list(req.answers) + [""] * len(questions))[: len(questions)]

    try:
        grading = _grade(questions, answers)
        profile = _build_profile(target, nodes, grading, questions=questions)
        feedback = decide_feedback(grading["correct_count"], grading["total_count"])
    except Exception as e:
        logger.error("答题判分失败 session=%s", req.session_id, exc_info=True)
        raise HTTPException(status_code=500, detail=f"判分失败: {e}")

    logger.info("答题提交 session=%s 正确率=%d/%d 策略=%s",
                req.session_id, grading["correct_count"], grading["total_count"], feedback["strategy"])

    # 回写画像到 session 缓存，供 POST /api/learning/report 补跑报告时读取 (仅需 session_id)
    session["profile"] = profile

    return SubmitResponse(
        session_id=req.session_id,
        profile=profile,
        assessment={
            "questions": questions,
            "answers": answers,
            "per_node": grading["per_node"],
            "correct_count": grading["correct_count"],
            "total_count": grading["total_count"],
        },
        feedback=feedback,
    )


@router.post("/feedback", response_model=FeedbackResponse, summary="动态反馈内容再生（按策略针对性生成）")
def feedback(req: FeedbackRequest, request: Request):
    """按动态反馈策略针对性再生学习内容 (W4 计划⑤闭环)。

    B 端在 submit 拿到 feedback.strategy 后，调用本接口获取针对性内容:
      - remediate: 弱项节点的降维讲义 (换角度重讲)
      - scaffold:  弱项前置基础节点的入门讲义
      - advance:   路径下一节点的进阶挑战题
    """
    # 参数校验顺序: strategy(Pydantic Literal→422) → session(404) → LLM(503) → KG(503) → 再生
    # 先查 session (纯内存, 无副作用), 再查环境依赖
    session = _INTERACTIVE_SESSIONS.get(req.session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"会话 {req.session_id} 不存在或已过期（缓存上限 {_MAX_CACHED_SESSIONS}）",
        )
    if not llm_configured():
        raise HTTPException(status_code=503, detail="LLM 未配置，无法再生内容")
    kg = _get_kg(request)  # scaffold 策略需 kg.get_prerequisites

    # learning_path 用缓存的出题节点 (interactive 模式未跑 graph_controller,
    # 出题候选节点即当前学习范围)
    learning_path = session.get("nodes", [])

    try:
        result = regenerate_for_feedback(req.strategy, req.profile, learning_path, kg)
    except Exception as e:
        logger.error("feedback 再生失败 session=%s", req.session_id, exc_info=True)
        raise HTTPException(status_code=500, detail=f"内容再生失败: {e}")

    logger.info("feedback 再生 session=%s strategy=%s resources=%d",
                req.session_id, req.strategy, len(result["resources"]))

    return FeedbackResponse(
        session_id=req.session_id,
        strategy=req.strategy,
        resources=result["resources"],
        node_count=result["node_count"],
    )
