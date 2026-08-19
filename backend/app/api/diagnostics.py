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
from concurrent.futures import ThreadPoolExecutor
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
from app.agents.domain_bootstrap import bootstrap_domain, resolve_direction
from app.agents import flow_transactions as flow_tx
from app.agents.graph_controller import graph_controller_node
from app.agents.llm import llm_configured, use_llm_overrides
from app.agents.log_events import to_log_event
from app.agents.report_builder import build_learning_report
from app.agents.run_store import list_runs, load_run, save_run
from app.agents import profile_store
from app.agents.workflow_def import (
    evaluate_def_decisions,
    get_workflow,
    list_workflows,
    preflight,
    validate_definition,
    workflow_for,
)
from app.config import settings
from app.utils.logging import get_logger
from app.utils.web_search import search_weak_topics

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
    llm_overrides: dict = Field(default=None, description="Spec B: Agent 学习引擎独立 key 覆写")
    tavily_key: str = Field(default=None, description="Tavily API key (动态建域联网检索资料, 缺省回落 env)")


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
    orchestration_events: list = Field(default_factory=list, description="结构化执行事件 (Phase 0: to_log_event 规范化, interactive 出题阶段为空)")


class SubmitRequest(BaseModel):
    """interactive 答题提交请求。"""

    session_id: str = Field(..., description="assess(interactive) 返回的 session_id")
    answers: list = Field(..., description="逐题作答，顺序与 questions 一致；选择题给选项内容/字母，判断题给'对'/'错'")
    llm_overrides: dict = Field(default=None, description="Spec B: Agent 学习引擎独立 key 覆写")
    learner_key: str | None = Field(None, description="稳定学习者标识 (画像跨次累积/进化档案, 防路径穿越)")


class SubmitResponse(BaseModel):
    """答题提交响应: 判分 + 画像 + 动态反馈 + 专属图谱 + 协同日志。"""

    session_id: str
    profile: dict
    assessment: dict
    feedback: dict = Field(..., description="动态反馈策略: advance/remediate/scaffold")
    knowledge_graph: dict = Field(default_factory=dict, description="专属学习路径图谱 (submit 后由 graph_controller 组装)")
    orchestration_log: list = Field(default_factory=list, description="Agent 协同执行日志 (判分/画像/图谱)")
    orchestration_events: list = Field(default_factory=list, description="结构化执行事件 (Phase 0: to_log_event 规范化)")
    learner_key: str | None = Field(None, description="回显学习者标识 (画像档案)")
    profile_diff: dict | None = Field(None, description="画像版本 diff (跨次进化: recovered/newly_known/newly_weak/regressed)")


class FeedbackRequest(BaseModel):
    """动态反馈内容再生请求 (W5 闭环)。"""

    session_id: str = Field(..., description="assess(interactive) 返回的 session_id")
    strategy: Literal["advance", "remediate", "scaffold"] = Field(..., description="动态反馈策略")
    profile: dict = Field(..., description="submit 返回的画像 (含 weak_topics/theory_level)")
    llm_overrides: dict = Field(default=None, description="Spec B: Agent 学习引擎独立 key 覆写")
    tavily_key: str = Field(default=None, description="Tavily API key (联网搜索薄弱知识点相关网站)")


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


def _persist_run(*, session_id: str, mode: str, request: dict | None = None,
                 orchestration_log: list | None = None, summary: dict | None = None,
                 workflow: dict | None = None) -> None:
    """Phase 1/2: 把一次 run 落盘 (run.json + events.jsonl + 流程定义快照)。失败不影响主流程。"""
    try:
        save_run(
            session_id=session_id,
            mode=mode,
            request=request,
            events=[to_log_event(l) for l in (orchestration_log or [])],
            log=orchestration_log or [],
            summary=summary or {},
            workflow=workflow,
        )
    except Exception as e:  # noqa: BLE001  run 落盘是尽力而为
        logger.warning("run_store 落盘失败 session=%s err=%s", session_id, e)


def _resolve_workflow(req) -> dict:
    """按 mode/scene 解析流程定义 (Phase 2: 流程即数据)。未知/缺失回落场景一。"""
    wf_id = workflow_for(req.mode, req.scene)
    wf = get_workflow(wf_id)
    if wf is None:
        wf = get_workflow("scene1-loop")
    return wf or {"id": "scene1-loop", "name": "场景一·学情闭环", "stages": []}


def _stage_labels(wf: dict) -> dict:
    """阶段 id → 展示文案 (流程定义驱动 SSE 进度, 改定义即可改文案)。"""
    return {
        s["id"]: s["label"]
        for s in wf.get("stages", [])
        if isinstance(s, dict) and s.get("id") and s.get("label")
    }


def _preflight_or_400(req) -> dict:
    """运行前校验 (坏请求/坏定义在启动前被拒)。返回已解析流程定义。"""
    wf_id = workflow_for(req.mode, req.scene)
    ok, errs = preflight(wf_id, target_direction=req.target_direction,
                         scene=req.scene, max_retries=req.max_retries)
    if not ok:
        raise HTTPException(status_code=400, detail="; ".join(errs))
    wf = get_workflow(wf_id) or get_workflow("scene1-loop")
    return wf


class PreflightRequest(BaseModel):
    """流程运行前校验请求 (Phase 2, 干跑)。"""

    workflow_id: str = Field(..., description="流程定义 id")
    target_direction: str = Field(..., description="拟请求的学习目标方向")
    scene: str = Field("no_project", description="no_project | with_project")
    max_retries: int = Field(3, ge=1, le=5)


@router.get("/workflows", summary="流程定义列表 (Phase 2: 流程即数据)")
def list_workflows_api():
    return {"workflows": [
        {k: w.get(k) for k in ("id", "name", "description", "stages")}
        for w in list_workflows()
    ]}


@router.post("/workflows/preflight", response_model=None, summary="流程运行前校验 (干跑)")
def preflight_api(req: PreflightRequest):
    ok, errs = preflight(
        req.workflow_id,
        target_direction=req.target_direction,
        scene=req.scene,
        max_retries=req.max_retries,
    )
    return {"workflow_id": req.workflow_id, "ok": ok, "errors": errs}


class EvaluateRequest(BaseModel):
    """流程决策确定性求值请求 (Phase 4, 不跑 Agent)。"""

    workflow_id: str = Field(..., description="流程定义 id")
    context: dict = Field(default_factory=dict, description="求值上下文 (如 correct_ratio 等点路径字段)")


@router.post("/workflows/evaluate", summary="流程决策确定性求值 (Phase 4, 不跑 Agent)")
def evaluate_api(req: EvaluateRequest):
    wf = get_workflow(req.workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail=f"流程定义不存在: {req.workflow_id}")
    errs = validate_definition(wf)
    if errs:
        raise HTTPException(status_code=400, detail="; ".join(errs))
    return {
        "workflow_id": req.workflow_id,
        "ok": True,
        "decisions": evaluate_def_decisions(wf, req.context or {}),
    }


@router.get("/workflows/{workflow_id}", summary="流程定义详情 (Phase 2)")
def get_workflow_api(workflow_id: str):
    wf = get_workflow(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail=f"流程定义不存在: {workflow_id}")
    return wf


class DraftRequest(BaseModel):
    """流程定义草稿 (Phase 3b: 未提交编辑, WIP 可过不了严格校验)。"""

    definition: dict = Field(..., description="流程定义草稿 (含 id)")


class CommitRequest(BaseModel):
    """流程定义提交 (Phase 3b: 校验→原子 revision 保存[→AI 审查记录])。"""

    definition: dict = Field(..., description="流程定义 (需通过严格校验, 内置 id 被拒)")
    note: str = Field("", description="提交说明 (审计)")
    reviewed_by: str = Field("", description="审查记录 (可选, 如 current-session agent label)")


class RestoreRequest(BaseModel):
    """流程定义回滚 (Phase 3b)。"""

    revision: str = Field(..., description="目标 revision (来自 revisions 列表)")


@router.put("/workflows/{workflow_id}/draft", summary="保存流程定义草稿 (Phase 3b)")
def save_workflow_draft_api(workflow_id: str, req: DraftRequest):
    """草稿 WIP 不强制通过校验; 返回 warnings/valid 供前端提示。"""
    res = flow_tx.save_draft(req.definition)
    if not res["ok"]:
        raise HTTPException(status_code=400, detail="; ".join(res.get("errors", [])))
    return res


@router.post("/workflows/{workflow_id}/commit", summary="提交发布流程定义 (Phase 3b, revision 化)")
def commit_workflow_api(workflow_id: str, req: CommitRequest):
    res = flow_tx.commit_definition(req.definition, note=req.note, reviewed_by=req.reviewed_by)
    if not res["ok"]:
        # 内置禁改 → 409; 校验失败 → 400
        code = 409 if any("内置" in e for e in res.get("errors", [])) else 400
        raise HTTPException(status_code=code, detail="; ".join(res.get("errors", [])))
    return {"id": res["id"], "revision": res["revision"], "committed": res["committed"]}


@router.get("/workflows/{workflow_id}/revisions", summary="流程定义 revision 列表 (Phase 3b)")
def list_workflow_revisions_api(workflow_id: str):
    return {"workflow_id": workflow_id, "revisions": flow_tx.list_revisions(workflow_id)}


@router.post("/workflows/{workflow_id}/restore", summary="回滚流程定义到指定 revision (Phase 3b)")
def restore_workflow_api(workflow_id: str, req: RestoreRequest):
    res = flow_tx.restore_revision(workflow_id, req.revision)
    if not res["ok"]:
        code = 404 if any("revision 不存在" in e for e in res.get("errors", [])) else 400
        raise HTTPException(status_code=code, detail="; ".join(res.get("errors", [])))
    return {"id": res["id"], "restored": res["restored"], "definition": res["definition"]}


@router.get("/runs/{session_id}", summary="读取一次 run 记录 (Phase 1: 复盘/续跑)")
def get_run(session_id: str):
    """返回已落盘的 run 记录 (含请求 meta/汇总/完整结构化事件/原始日志)。"""
    data = load_run(session_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"run {session_id} 不存在")
    return data["run"]


@router.get("/runs", summary="最近 run 摘要列表 (Phase 1: 历史运行入口)")
def get_runs(limit: int = 20):
    runs = list_runs(limit)
    return {"count": len(runs), "runs": runs}


@router.post("/assess", response_model=AssessResponse, summary="学情测评（demo 跑全流程 / interactive 仅出题）")
def assess(req: AssessRequest, request: Request):
    """触发学情测评。

    - **demo**: LLM 自动作答跑通完整工作流（学情检测→画像审核→图谱→生成→内容审核），适合 Postman/curl 验证。
    - **interactive**: 仅出题返回 `assessment.questions`（其余字段为空），前端答题后调 `POST /submit` 判分。
    """
    kg = _get_kg(request)

    # --- interactive 模式: 仅出题，不走工作流 ---
    if req.mode == "interactive":
        # Spec B: 前端 UI 配置的 key 经 req.llm_overrides 覆写, 必须在此建 ContextVar —
        # 否则 prepare_questions 里的 llm_configured()/动态建域判定读不到, 导致 UI 配置后
        # 仍报 "LLM 未配置且题库为空,无法出题" (与 submit/regenerate 的 use_llm_overrides 用法对齐)。
        with use_llm_overrides(req.llm_overrides):
            try:
                # 域判定 (阶段16): 目标命中既有域 → 方向相关选点; 未命中 → 动态建域;
                # LLM/向量都不可用 → 回退旧选点行为 (零基础难度入口)。
                nodes = None
                resolution, dir_nodes = resolve_direction(kg, req.target_direction, req.known_topics)
                if resolution == "miss":
                    if not llm_configured():
                        raise ValueError(
                            f"学习领域「{req.target_direction}」暂未收录, 且未配置 LLM 无法动态建域; "
                            "请在设置中配置 AI 后重试, 或选择已收录方向 (Python/数据分析/机器学习等)")
                    logger.info("学习目标未命中既有域, 触发动态建域: %s", req.target_direction)
                    nodes = bootstrap_domain(
                        kg, req.target_direction, tavily_key=req.tavily_key or settings.TAVILY_API_KEY)
                elif resolution == "hit" and dir_nodes:
                    nodes = dir_nodes
                questions, nodes = prepare_questions(kg, req.target_direction, req.known_topics, nodes=nodes)
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
    wf = _preflight_or_400(req)  # Phase 2: 流程定义/请求运行前校验 (坏定义启动前被拒)
    initial = make_initial_state(
        target_direction=req.target_direction,
        mode=req.mode,
        known_topics=req.known_topics,
        scene=req.scene,
        max_retries=req.max_retries,
        llm_overrides=req.llm_overrides,
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
        orchestration_events=[to_log_event(l) for l in result.get("orchestration_log", [])],
    )
    # Phase 1/2: 落盘 run 记录 (复盘/续跑耐久 + 流程定义快照溯源)
    _persist_run(
        session_id=initial["session_id"],
        mode="demo",
        request={
            "target_direction": req.target_direction,
            "scene": req.scene,
            "max_retries": req.max_retries,
            "workflow_id": wf.get("id"),
        },
        orchestration_log=result.get("orchestration_log", []),
        summary={
            "theory_level": result.get("user_profile", {}).get("theory_level"),
            "path_nodes": len(result.get("knowledge_graph", {}).get("learning_path", []))
            if result.get("knowledge_graph") else 0,
            "resources_count": len(result.get("generated_content", {}).get("resources", []))
            if result.get("generated_content") else 0,
            "review_passed": bool(result.get("review_results", {}).get("passed")),
        },
        workflow=wf,
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
    wf = _preflight_or_400(req)  # Phase 2: 运行前校验 (坏定义/坏请求启动前被拒)
    stage_labels = _stage_labels(wf)

    # interactive 模式不需要流式 (出题快), 仍走原 /assess
    if req.mode == "interactive":
        raise HTTPException(status_code=400, detail="interactive 模式请用 POST /assess (出题快无需流式)")

    initial = make_initial_state(
        target_direction=req.target_direction,
        mode="demo",
        known_topics=req.known_topics,
        scene=req.scene,
        max_retries=req.max_retries,
        llm_overrides=req.llm_overrides,
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
                    # Phase 2: 流程定义驱动进度文案 (阶段 label 优先, 可改定义不改代码)
                    message = stage_labels.get(node_name) or _NODE_PROGRESS.get(node_name, node_name)
                    yield _sse("progress", {
                        "node": node_name,
                        "message": message,
                        "log_tail": log_tail,
                        "log_events": [to_log_event(l) for l in log_tail],
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
                "orchestration_events": [to_log_event(l) for l in final_state.get("orchestration_log", [])],
            }
            # Phase 1/2: 落盘 run 记录 (SSE done + 流程定义快照)
            _persist_run(
                session_id=session_id,
                mode="demo",
                request={
                    "target_direction": req.target_direction,
                    "scene": req.scene,
                    "max_retries": req.max_retries,
                    "workflow_id": wf.get("id"),
                },
                orchestration_log=final_state.get("orchestration_log", []),
                summary={
                    "theory_level": final_state.get("user_profile", {}).get("theory_level"),
                    "path_nodes": len(final_state.get("knowledge_graph", {}).get("learning_path", []))
                    if final_state.get("knowledge_graph") else 0,
                    "resources_count": len(final_state.get("generated_content", {}).get("resources", []))
                    if final_state.get("generated_content") else 0,
                    "review_passed": bool(final_state.get("review_results", {}).get("passed")),
                },
                workflow=wf,
            )
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


@router.post("/submit", response_model=SubmitResponse, summary="提交答题（interactive 模式判分+动态反馈+图谱组装）")
def submit(req: SubmitRequest, request: Request):
    """提交 interactive 模式的答题，后端判分并产出画像 + 动态反馈策略。

    流程: 取缓存题目 → _grade 判分 → _build_profile 画像 → decide_feedback 动态反馈。
    """
    kg = _get_kg(request)  # 前置检查 + 供 graph_controller 组装路径

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

    orchestration_log = []
    knowledge_graph = {}
    try:
        with use_llm_overrides(req.llm_overrides):
            grading = _grade(questions, answers)
            profile = _build_profile(target, nodes, grading, questions=questions)
        feedback = decide_feedback(grading["correct_count"], grading["total_count"])

        # 记录判分 + 画像协同日志 (供前端 StageAgent 展示)
        ts = datetime.utcnow().isoformat()
        orchestration_log.append(
            f"[{ts}] 🔧 学情检测: 判分 {grading['correct_count']}/{grading['total_count']}"
        )
        orchestration_log.append(
            f"[{ts}] 📋 画像构建: theory_level={profile.get('theory_level')} "
            f"weak={len(profile.get('weak_topics', []))} known={len(profile.get('known_topics', []))}"
        )

        # 复用 graph_controller 节点组装专属学习路径 (同 demo 工作流, 产出 knowledge_graph + log)
        graph_node = graph_controller_node(kg)
        graph_update = graph_node({"user_profile": profile})
        knowledge_graph = graph_update.get("knowledge_graph", {})
        orchestration_log.extend(graph_update.get("orchestration_log", []))
    except Exception as e:
        logger.error("答题判分失败 session=%s", req.session_id, exc_info=True)
        raise HTTPException(status_code=500, detail=f"判分失败: {e}")

    logger.info("答题提交 session=%s 正确率=%d/%d 策略=%s 路径节点=%d",
                req.session_id, grading["correct_count"], grading["total_count"], feedback["strategy"],
                len(knowledge_graph.get("learning_path", [])))

    # 回写画像 + 图谱到 session 缓存，供 POST /api/learning/report 补跑报告时读取
    session["profile"] = profile
    session["knowledge_graph"] = knowledge_graph

    # 画像跨次累积/进化 (档案): 复用之前画像 → 加权合并掌握度 → 落库 → 返回版本 diff
    profile_diff = None
    learner_key = None
    if req.learner_key:
        try:
            key = profile_store.safe_key(req.learner_key)
            prev = profile_store.load_profile(key)
            evolved, diff = profile_store.merge_profiles(prev, profile)
            if prev is not None:
                profile = evolved
                session["profile"] = profile  # 进化版画像写回 session, 供学习报告补跑读取
            profile_store.save_profile(key, profile)
            profile_diff = diff
            learner_key = req.learner_key
        except Exception as e:  # noqa: BLE001  画像档案尽力而为, 不影响判分主流程
            logger.warning("画像档案 merge 失败 learner=%r err=%s", getattr(req, 'learner_key', None), e)

    # Phase 1/2: 落盘 run 记录 (interactive submit + 流程定义快照 + 画像版本 diff)
    # 注意: 必须在 return 之前调用 (此前的写法在 return 之后 → 死代码, interactive run 从未落盘)。
    _persist_run(
        session_id=req.session_id,
        mode="interactive",
        request={"target_direction": target, "workflow_id": "scene1-interactive"},
        orchestration_log=orchestration_log,
        summary={
            "correct_count": grading["correct_count"],
            "total_count": grading["total_count"],
            "strategy": feedback["strategy"],
            "theory_level": profile.get("theory_level"),
            "path_nodes": len(knowledge_graph.get("learning_path", [])) if knowledge_graph else 0,
            **({"profile_diff": profile_diff, "learner_key": learner_key} if profile_diff else {}),
        },
        workflow=get_workflow("scene1-interactive"),
    )

    return SubmitResponse(
        session_id=req.session_id,
        profile=profile,
        learner_key=learner_key,
        profile_diff=profile_diff,
        assessment={
            "questions": questions,
            "answers": answers,
            "per_node": grading["per_node"],
            "correct_count": grading["correct_count"],
            "total_count": grading["total_count"],
        },
        feedback=feedback,
        knowledge_graph=knowledge_graph,
        orchestration_log=orchestration_log,
        orchestration_events=[to_log_event(l) for l in orchestration_log],
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

    # Tavily 联网搜索与 LLM 再生并行: Tavily 不依赖 LLM/override, 后台线程先行,
    # 主线程并行做 LLM 再生 (二者串行则 +7s, 并行后 wall-clock ≈ LLM 耗时)。
    tavily_key = req.tavily_key or settings.TAVILY_API_KEY
    tavily_future = None
    tavily_pool = None
    if tavily_key:
        tavily_pool = ThreadPoolExecutor(max_workers=1)
        tavily_future = tavily_pool.submit(
            search_weak_topics, req.profile, tavily_key, nodes=session.get("nodes"),
            direction=session.get("target_direction"))

    try:
        with use_llm_overrides(req.llm_overrides):
            result = regenerate_for_feedback(req.strategy, req.profile, learning_path, kg)
    except Exception as e:
        logger.error("feedback 再生失败 session=%s", req.session_id, exc_info=True)
        if tavily_pool is not None:
            tavily_pool.shutdown(wait=False)
        raise HTTPException(status_code=500, detail=f"内容再生失败: {e}")

    # 收 Tavily 结果 (LLM 耗时 ~15-30s > Tavily ~7s, 此处通常已就绪)
    if tavily_future is not None:
        try:
            web_resources = tavily_future.result(timeout=30)
        except Exception:
            logger.warning("feedback Tavily 搜索异常", exc_info=True)
            web_resources = []
        tavily_pool.shutdown(wait=False)
        if web_resources:
            result.setdefault("resources", []).extend(web_resources)

    logger.info("feedback 再生 session=%s strategy=%s resources=%d",
                req.session_id, req.strategy, len(result.get("resources", [])))

    return FeedbackResponse(
        session_id=req.session_id,
        strategy=req.strategy,
        resources=result["resources"],
        node_count=result["node_count"],
    )
