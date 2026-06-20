"""
知识图谱查询 API 路由

对齐 data/prompts/03_graph_controller_agent.txt 的查询接口定义。
直接复用 KnowledgeGraph engine 的方法，B 端第3周 G6 图谱渲染组件对接本组路由。

路由前缀: /api/graph
  GET  /node/{node_id}                 按节点 ID 查询
  GET  /category/{category}            按分类查询
  GET  /difficulty                     按难度区间查询 (?min_d=&max_d=)
  GET  /tags                           按标签查询 (?tags=a,b)
  GET  /prerequisites/{node_id}        查询节点前置依赖
  GET  /dependents/{node_id}           查询依赖该节点的后继
  GET  /search                         语义向量检索 (?q=&top_k=)
  POST /hybrid                         图遍历+向量混合检索
  POST /path                           组装个性化学习路径
  PUT  /status/{node_id}               更新节点掌握状态
"""

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

# 节点掌握状态合法值 (对齐 engine.update_node_status)
_VALID_STATUSES = {"mastered", "in_progress", "unlearned", "difficult"}


def _get_kg(request: Request):
    """从 app.state 获取全局 KnowledgeGraph 单例。"""
    kg = getattr(request.app.state, "kg", None)
    if kg is None:
        raise HTTPException(status_code=503, detail="知识图谱引擎未就绪（Neo4j 未连接）")
    return kg


# ============================================================
# 查询类
# ============================================================

@router.get("/node/{node_id}", summary="按节点 ID 查询")
def get_node(node_id: str, request: Request):
    kg = _get_kg(request)
    node = kg.get_node(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"节点 {node_id} 不存在")
    return node


@router.get("/category/{category}", summary="按分类查询节点列表")
def get_by_category(category: str, request: Request):
    kg = _get_kg(request)
    return kg.get_by_category(category)


@router.get("/difficulty", summary="按难度区间查询")
def get_by_difficulty(
    request: Request,
    min_d: int = Query(1, ge=1, le=5, description="最低难度"),
    max_d: int = Query(5, ge=1, le=5, description="最高难度"),
):
    if min_d > max_d:
        raise HTTPException(status_code=400, detail="min_d 不能大于 max_d")
    kg = _get_kg(request)
    return kg.get_by_difficulty(min_d, max_d)


@router.get("/tags", summary="按标签查询 (任一命中)")
def get_by_tags(
    request: Request,
    tags: str = Query(..., description="逗号分隔的标签，如 基础语法,循环"),
):
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    if not tag_list:
        raise HTTPException(status_code=400, detail="tags 不能为空")
    kg = _get_kg(request)
    return kg.get_by_tags(tag_list)


@router.get("/prerequisites/{node_id}", summary="查询节点前置依赖")
def get_prerequisites(node_id: str, request: Request):
    kg = _get_kg(request)
    if kg.get_node(node_id) is None:
        raise HTTPException(status_code=404, detail=f"节点 {node_id} 不存在")
    return kg.get_prerequisites(node_id)


@router.get("/dependents/{node_id}", summary="查询依赖该节点的后继")
def get_dependents(node_id: str, request: Request):
    kg = _get_kg(request)
    if kg.get_node(node_id) is None:
        raise HTTPException(status_code=404, detail=f"节点 {node_id} 不存在")
    return kg.get_dependents(node_id)


@router.get("/search", summary="语义向量检索")
def semantic_search(
    request: Request,
    q: str = Query(..., min_length=2, description="自然语言查询"),
    top_k: int = Query(5, ge=1, le=50),
    difficulty_max: int = Query(None, ge=1, le=5, description="可选难度上限过滤"),
):
    kg = _get_kg(request)
    if kg.embedding_client is None:
        raise HTTPException(
            status_code=503,
            detail="语义检索不可用（Embedding 客户端未配置），请使用图遍历类查询",
        )
    nodes = kg.semantic_search(q, top_k=top_k, difficulty_max=difficulty_max)
    return {"query": q, "count": len(nodes), "nodes": nodes}


# ============================================================
# 混合检索 / 路径组装 (POST，请求体)
# ============================================================

class HybridRequest(BaseModel):
    known_ids: list[str] = Field(default_factory=list, description="已掌握节点 ID")
    weak_ids: list[str] = Field(default_factory=list, description="薄弱节点 ID")
    level: int = Field(3, ge=1, le=5, description="目标难度等级")
    top_k: int = Field(10, ge=1, le=50)


class PathRequest(BaseModel):
    known_ids: list[str] = Field(default_factory=list, description="已掌握节点 ID")
    weak_ids: list[str] = Field(default_factory=list, description="薄弱节点 ID")
    level: int = Field(2, ge=1, le=5, description="目标难度等级")
    max_nodes: int = Field(20, ge=1, le=20, description="路径节点数上限")


@router.post("/hybrid", summary="图遍历+向量混合检索")
def hybrid_retrieve(req: HybridRequest, request: Request):
    """推荐学习候选节点: 图遍历 (精确) + 向量语义 (模糊) 合并排序。"""
    kg = _get_kg(request)
    nodes = kg.hybrid_retrieve(
        known_ids=req.known_ids,
        weak_ids=req.weak_ids,
        level=req.level,
        top_k=req.top_k,
    )
    return {"count": len(nodes), "nodes": nodes}


@router.post("/path", summary="组装个性化学习路径")
def assemble_path(req: PathRequest, request: Request):
    """输入已掌握/薄弱节点，输出按依赖拓扑+难度排序的渐进式学习路径。"""
    kg = _get_kg(request)
    path = kg.assemble_learning_path(
        known_ids=req.known_ids,
        weak_ids=req.weak_ids,
        level=req.level,
        max_nodes=req.max_nodes,
    )
    total_minutes = sum(n.get("estimated_minutes", 0) or 0 for n in path)
    return {
        "path_length": len(path),
        "estimated_total_hours": round(total_minutes / 60, 1),
        "nodes": path,
    }


# ============================================================
# 状态管理
# ============================================================

class StatusUpdate(BaseModel):
    status: str = Field(..., description="mastered | in_progress | unlearned | difficult")


@router.put("/status/{node_id}", summary="更新节点掌握状态")
def update_status(node_id: str, body: StatusUpdate, request: Request):
    if body.status not in _VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"无效状态 '{body.status}'，有效值: {sorted(_VALID_STATUSES)}",
        )
    kg = _get_kg(request)
    if kg.get_node(node_id) is None:
        raise HTTPException(status_code=404, detail=f"节点 {node_id} 不存在")
    kg.update_node_status(node_id, body.status)
    return {"node_id": node_id, "status": body.status, "updated": True}
