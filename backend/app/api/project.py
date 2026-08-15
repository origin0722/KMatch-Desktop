"""
项目代码解析与项目图谱 API 路由

W6 第一批: AST 解析 + 项目图谱生成 (落 Neo4j 四层图谱第2/3层 + 内存返回 G6 结构)。

路由前缀: /api/project
  POST /parse              解析项目代码 → 构建图谱 → 落 Neo4j + 返回 G6 结构
  GET  /graph/{project_id} 查询已落库的项目图谱
  GET  /examples           列出可用示例项目

对齐 backend/app/api/graph.py 风格: _get_kg 守卫 (503) + Pydantic + HTTPException。
B 端项目图谱页 (AntV G6) 对接本组路由。
"""

import uuid
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.code_parser import (
    ParsedProject,
    list_example_projects,
    load_example_project,
    load_text_source,
    parse_project,
)
from app.agents.code_reviewer import review_code
from app.agents.code_tester import run_tests
from app.agents.project_analyzer import analyze_project
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


def _get_kg(request: Request):
    """从 app.state 获取全局 KnowledgeGraph 单例。None → 503。"""
    kg = getattr(request.app.state, "kg", None)
    if kg is None:
        raise HTTPException(status_code=503, detail="知识图谱引擎未就绪（Neo4j 未连接）")
    return kg


# ============================================================
# 请求/响应模型
# ============================================================

class ParseRequest(BaseModel):
    source_type: Literal["example", "text", "files"] = "example"
    project_id: Optional[str] = None     # 缺省: example→example_name; text→text-{uuid8}
    example_name: Optional[str] = None   # source_type=example 时必填
    code: Optional[str] = None           # source_type=text 时必填
    filename: str = "main.py"            # text 源文件名
    sources: Optional[dict] = None       # source_type=files 时必填 {module_name: source}
    write_to_neo4j: bool = True          # False=仅解析返回不落库 (前端预览)


class ProjectGraphResponse(BaseModel):
    project_id: str
    parsed_at: str
    written_to_neo4j: bool
    stats: dict
    nodes: list[dict]
    edges: list[dict]


# ============================================================
# POST /parse
# ============================================================

@router.post("/parse", response_model=ProjectGraphResponse, summary="解析项目代码→构建图谱→落 Neo4j+返回")
def parse_project_api(req: ParseRequest, request: Request):
    # 1. 校验 source_type 字段组合
    if req.source_type == "example":
        if not req.example_name:
            raise HTTPException(status_code=422, detail="source_type=example 时 example_name 必填")
        try:
            sources = load_example_project(req.example_name)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"示例项目不存在: {req.example_name}")
        project_id = req.project_id or req.example_name
    elif req.source_type == "files":
        if not req.sources:
            raise HTTPException(status_code=422, detail="source_type=files 时 sources 必填")
        sources = req.sources
        project_id = req.project_id or f"files-{uuid.uuid4().hex[:8]}"
    else:  # text
        if not req.code or not req.code.strip():
            raise HTTPException(status_code=422, detail="source_type=text 时 code 必填")
        sources = load_text_source(req.code, req.filename)
        project_id = req.project_id or f"text-{uuid.uuid4().hex[:8]}"

    # 2. 解析 (AST + Jedi)
    try:
        parsed = parse_project(project_id, sources)
    except SyntaxError as e:
        raise HTTPException(status_code=422, detail=f"代码语法错误: {e}")
    except Exception as e:
        logger.error("项目解析失败 project=%s", project_id, exc_info=True)
        raise HTTPException(status_code=500, detail=f"项目解析失败: {e}")

    # 3. 落 Neo4j (可选)
    written = False
    if req.write_to_neo4j:
        kg = _get_kg(request)
        try:
            kg.write_project_graph(project_id, parsed.entities, parsed.relations)
            written = True
        except Exception as e:
            logger.error("项目图谱写入失败 project=%s", project_id, exc_info=True)
            raise HTTPException(status_code=500, detail=f"项目图谱写入失败: {e}")

    # 4. 返回 G6 结构
    return _to_g6_response(parsed, written)


# ============================================================
# GET /graph/{project_id}
# ============================================================

@router.get("/graph/{project_id}", response_model=ProjectGraphResponse, summary="查询已落库的项目图谱")
def get_project_graph_api(project_id: str, request: Request):
    kg = _get_kg(request)
    graph = kg.get_project_graph(project_id)
    if graph is None:
        raise HTTPException(status_code=404, detail=f"项目图谱不存在: {project_id}（未解析或已删除）")
    # get_project_graph 已返回 G6 结构，补 stats + parsed_at
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    return ProjectGraphResponse(
        project_id=project_id,
        parsed_at=_first_node_prop(nodes, "parsed_at", ""),
        written_to_neo4j=True,
        stats=_compute_stats_from_g6(nodes, edges),
        nodes=nodes,
        edges=edges,
    )


# ============================================================
# POST /review — 代码审查 (场景二 Step 6①)
# ============================================================

class ReviewRequest(BaseModel):
    code: str                          # 用户提交的修改后代码
    target_direction: str              # 开发目标 (检索相关领域知识点 + LLM 上下文)
    knowledge_node_ids: Optional[list[str]] = None  # 用户指定的相关知识点 (可选)
    llm_overrides: dict = None  # Spec B: Agent 独立 key 覆写


@router.post("/review", summary="代码审查: 对照领域规范检查逻辑错误/安全隐患")
def review_project_code_api(req: ReviewRequest, request: Request):
    """场景二 Step 6①: 用户提交修改后代码 → reviewer 代码审查。

    两阶段: AST 安全检查硬规则 + LLM 对照领域规范审查。
    返回 review_results (与内容审核 review_results 同构)。
    """
    if not req.code or not req.code.strip():
        raise HTTPException(status_code=422, detail="code 必填")
    if not req.target_direction or not req.target_direction.strip():
        raise HTTPException(status_code=422, detail="target_direction 必填")

    kg = _get_kg(request)
    try:
        result = review_code(kg, req.code, req.target_direction, req.knowledge_node_ids,
                             llm_overrides=req.llm_overrides)
    except Exception as e:
        logger.error("代码审查失败", exc_info=True)
        raise HTTPException(status_code=500, detail=f"代码审查失败: {e}")
    return result


# ============================================================
# POST /test — 代码测试 (场景二 Step 6②)
# ============================================================

class TestRequest(BaseModel):
    source_type: Literal["example", "text"] = "example"
    example_name: Optional[str] = None      # source_type=example 必填；baseline 模式必填
    code: Optional[str] = None              # source_type=text 必填
    filename: str = "main.py"
    target_direction: str                   # 知识检索 + LLM 上下文
    knowledge_node_ids: Optional[list[str]] = None
    mode: Literal["generate", "baseline"] = "generate"
    project_id: Optional[str] = None        # 已入库项目 (用于风险标注回写)
    llm_overrides: dict = None  # Spec B: Agent 独立 key 覆写


@router.post("/test", summary="代码测试: 生成Pytest并执行，输出通过率/覆盖率+风险标注")
def test_project_code_api(req: TestRequest, request: Request):
    """场景二 Step 6②: 代码测试Agent自动生成 Pytest 并执行。

    两阶段沙箱: AST 安全预检 (源码+测试代码) + subprocess 执行 pytest --cov。
    图谱驱动生成: 基于 code_parser 函数签名 + 领域 common_mistakes。
    返回 06 prompt 测试报告 (通过率/覆盖率/失败用例/风险节点)。
    """
    # 1. 校验字段组合
    if req.mode == "baseline":
        if not req.example_name:
            raise HTTPException(status_code=422, detail="baseline 模式需要 example_name")
        example_name = req.example_name
        sources = {}  # baseline 由 run_tests 从 example 加载
    else:  # generate
        if req.source_type == "example":
            if not req.example_name:
                raise HTTPException(status_code=422, detail="source_type=example 时 example_name 必填")
            try:
                sources = load_example_project(req.example_name)
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail=f"示例项目不存在: {req.example_name}")
            example_name = req.example_name
        else:  # text
            if not req.code or not req.code.strip():
                raise HTTPException(status_code=422, detail="source_type=text 时 code 必填")
            sources = load_text_source(req.code, req.filename)
            example_name = None

    if not req.target_direction or not req.target_direction.strip():
        raise HTTPException(status_code=422, detail="target_direction 必填")

    # 2. kg (generate 模式需检索领域知识；baseline 也用于风险标注回写)
    kg = _get_kg(request)

    module_name = Path(req.filename).stem or "main"
    try:
        result = run_tests(
            kg, sources, req.target_direction, req.knowledge_node_ids,
            mode=req.mode, project_id=req.project_id, module_name=module_name,
            example_name=example_name, llm_overrides=req.llm_overrides,
        )
    except Exception as e:
        logger.error("代码测试失败", exc_info=True)
        raise HTTPException(status_code=500, detail=f"代码测试失败: {e}")
    return result


# ============================================================
# POST /analyze - LLM 深度分析 + 联网搜索 (按需)
# ============================================================

class AnalyzeRequest(BaseModel):
    project_id: str
    tavily_key: Optional[str] = None    # None 时用 settings.TAVILY_API_KEY


@router.post("/analyze", summary="LLM 深度分析项目图谱 + 联网搜索技术栈学习资源")
def analyze_project_api(req: AnalyzeRequest, request: Request):
    """按需触发: 从 Neo4j 取项目图谱 -> LLM 分析架构 -> 联网搜技术栈教程。

    不在自动解析流程中, 需用户手动点击"深度分析"按钮。
    返回 {summary, architecture, complexity, recommendations, tech_stack, web_resources}。
    """
    if not req.project_id or not req.project_id.strip():
        raise HTTPException(status_code=422, detail="project_id 必填")

    kg = _get_kg(request)
    try:
        result = analyze_project(kg, req.project_id, tavily_key=req.tavily_key)
    except ValueError as e:
        msg = str(e)
        if "不存在" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=503, detail=msg)
    except Exception as e:
        logger.error("项目深度分析失败 project=%s", req.project_id, exc_info=True)
        raise HTTPException(status_code=500, detail=f"项目深度分析失败: {e}")
    return result


# ============================================================
# GET /examples
# ============================================================

@router.get("/examples", summary="列出可用示例项目")
def list_examples():
    return list_example_projects()


# ============================================================
# 辅助: ParsedProject → G6 响应
# ============================================================

def _to_g6_response(parsed: ParsedProject, written: bool) -> ProjectGraphResponse:
    """ParsedProject → ProjectGraphResponse (G6 友好)。"""
    nodes = []
    for e in parsed.entities:
        nodes.append({
            "id": e.entity_id,
            "label": e.name,
            "group": e.kind,          # G6 据 group 着色
            "layer": e.layer,         # 供分层布局
            "properties": {
                "name": e.name,
                "kind": e.kind,
                "qualified_name": e.qualified_name,
                "module_name": e.module_name,
                "docstring": e.docstring,
                "params": e.params,
                "return_type": e.return_type,
                "bases": e.bases,
                "decorators": e.decorators,
                "line_start": e.line_start,
                "line_end": e.line_end,
                "source_code": e.source_code,
                "is_method": e.is_method,
                "parent_class_id": e.parent_class_id,
                "external_calls": e.external_calls,
                "risk_level": e.risk_level,
                "risk_reason": e.risk_reason,
            },
        })

    edges = []
    for r in parsed.relations:
        edge = {"source": r.source, "target": r.target, "label": r.type}
        if r.type == "CALLS":
            edge["line"] = r.line
            edge["resolved"] = r.resolved
        edges.append(edge)

    return ProjectGraphResponse(
        project_id=parsed.project_id,
        parsed_at=parsed.parsed_at,
        written_to_neo4j=written,
        stats=_compute_stats(parsed),
        nodes=nodes,
        edges=edges,
    )


def _compute_stats(parsed: ParsedProject) -> dict:
    kinds = [e.kind for e in parsed.entities]
    ext_count = sum(len(e.external_calls) for e in parsed.entities)
    return {
        "module_count": kinds.count("module"),
        "class_count": kinds.count("class"),
        "function_count": kinds.count("function"),
        "method_count": kinds.count("method"),
        "contains_count": sum(1 for r in parsed.relations if r.type == "CONTAINS"),
        "call_count": sum(1 for r in parsed.relations if r.type == "CALLS"),
        "inheritance_count": sum(1 for r in parsed.relations if r.type == "INHERITS"),
        "external_call_count": ext_count,
        "relation_count": len(parsed.relations),
    }


def _compute_stats_from_g6(nodes: list[dict], edges: list[dict]) -> dict:
    """从 get_project_graph 返回的 G6 结构算 stats (无 ParsedProject 时)。"""
    groups = [n.get("group") for n in nodes]
    labels = [e.get("label") for e in edges]
    ext_count = sum(len(n.get("properties", {}).get("external_calls") or []) for n in nodes)
    return {
        "module_count": groups.count("module"),
        "class_count": groups.count("class"),
        "function_count": groups.count("function"),
        "method_count": groups.count("method"),
        "contains_count": labels.count("CONTAINS"),
        "call_count": labels.count("CALLS"),
        "inheritance_count": labels.count("INHERITS"),
        "external_call_count": ext_count,
        "relation_count": len(edges),
    }


def _first_node_prop(nodes: list[dict], key: str, default="") -> str:
    """从首个节点的 properties 取某属性 (parsed_at 等)。"""
    for n in nodes:
        props = n.get("properties") or {}
        v = props.get(key)
        if v:
            return v
    return default
