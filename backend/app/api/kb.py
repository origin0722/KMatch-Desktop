"""知识库管理 API 路由 (CRUD: 知识节点 + 题目)。

JSON 为源, 写后同步 Neo4j: 写操作先改 JSON (真相源), 成功后同步单节点/题目到 Neo4j。
Neo4j 同步失败不回滚 JSON (可重导修复), API 返回 warning。

路由前缀: /api/kb
  知识节点:
    POST   /nodes                 创建 (ID 自动递增或手动)
    GET    /nodes/{node_id}       查单个
    PUT    /nodes/{node_id}       全量更新 (含 prerequisites 重建)
    DELETE /nodes/{node_id}       删除 (?cascade=true 连带删其题目)
  题目:
    POST   /questions             创建 (qid 自动递增)
    GET    /questions/{qid}       查单个
    PUT    /questions/{qid}       更新
    DELETE /questions/{qid}       删除

校验复用 scripts/validate_data.py (validate_node/validate_question)。
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.config import settings
from app.data import kb_store
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()

# 知识库根目录 (data/knowledge_base)
KB_BASE = Path(settings.DATA_DIR) / "knowledge_base"


def _get_kg(request: Request):
    """从 app.state 获取全局 KnowledgeGraph 单例。Neo4j 未就绪返 503。

    注意: KG 未就绪时 CRUD 仍可写 JSON (真相源), 但无法同步 Neo4j。
    本守卫保持 503 以与现有路由一致; 若需"仅 JSON 模式"可放宽, 但当前不放宽。
    """
    kg = getattr(request.app.state, "kg", None)
    if kg is None:
        raise HTTPException(status_code=503, detail="知识图谱引擎未就绪（Neo4j 未连接）")
    return kg


# 导入校验函数 (scripts 在 backend/scripts, 需加入 sys.path)
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
from scripts.validate_data import load_schema, validate_node, validate_question  # noqa: E402


def _schema() -> dict:
    """加载知识节点 schema (缓存可后续优化, 当前每次读)。"""
    return load_schema(KB_BASE / "schema.json")


def _all_node_ids() -> set:
    return set(kb_store.list_all_node_ids(KB_BASE))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ============================================================
# Pydantic 模型
# ============================================================

class KnowledgeNodeCreate(BaseModel):
    """创建知识节点 (id 可选, 缺省自动递增)。"""
    id: Optional[str] = Field(None, description="节点 ID (缺省自动递增, 如 PY-093)")
    name: str = Field(..., min_length=2, max_length=60)
    difficulty: int = Field(..., ge=1, le=5)
    category: str
    summary: str = Field(..., min_length=30, max_length=500)
    prerequisites: list[str] = Field(default_factory=list)
    key_points: list[str] = Field(..., min_length=3, max_length=8)
    practice_questions: list[dict] = Field(default_factory=list)
    common_mistakes: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    estimated_minutes: int = Field(20, ge=5, le=240)


class KnowledgeNodeUpdate(KnowledgeNodeCreate):
    """更新知识节点 (id 由路径提供, body.id 忽略)。"""
    id: Optional[str] = None  # 路径为准, body 的 id 忽略


class QuestionCreate(BaseModel):
    """创建题目 (qid 可选, 缺省自动递增)。"""
    qid: Optional[str] = Field(None, description="题目 ID (缺省自动递增, 如 Q-PY001-004)")
    source_node_id: str = Field(..., description="所属知识点 ID (须已存在)")
    type: str = Field(..., description="choice | fill | code")
    question: str = Field(..., min_length=5)
    options: Optional[list[str]] = None
    answer: str
    difficulty: int = Field(..., ge=1, le=5)
    hint: Optional[str] = None
    explanation: Optional[str] = None


class QuestionUpdate(QuestionCreate):
    qid: Optional[str] = None  # 路径为准


# ============================================================
# 知识节点 CRUD
# ============================================================

@router.post("/nodes", summary="创建知识节点")
def create_node(body: KnowledgeNodeCreate, request: Request):
    kg = _get_kg(request)
    # ID: 传则用 (校验唯一), 不传则自动递增
    prefix = "PY"
    if body.id:
        nid = body.id
        if kb_store.node_id_exists(KB_BASE, nid):
            raise HTTPException(status_code=409, detail=f"节点 {nid} 已存在")
        # 推断前缀 (用于题目 qid 生成)
        import re
        m = re.match(r"^([A-Z]{2})-\d{3}$", nid)
        if m:
            prefix = m.group(1)
    else:
        nid = kb_store.next_node_id(KB_BASE, prefix)
    node = body.model_dump(exclude_none=False)
    node["id"] = nid
    node["created_at"] = _now_iso()

    # 校验 (复用 validate_data)
    errors = validate_node(node, _schema(), _all_node_ids() | {nid})
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})

    # 写 JSON (真相源)
    kb_store.save_node(KB_BASE, node)
    # 同步 Neo4j (失败不回滚 JSON, 返 warning)
    warnings = _sync_node_to_neo4j(kg, node)
    return {"node": _node_response(node), "warnings": warnings}


@router.get("/nodes/{node_id}", summary="查询单个知识节点")
def get_node(node_id: str, request: Request):
    kg = _get_kg(request)
    node = kg.get_node(node_id)  # 从 Neo4j 读 (运行时图)
    if node is None:
        # 回退读 JSON (Neo4j 未同步时)
        node = kb_store.load_node(KB_BASE, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"节点 {node_id} 不存在")
    return {"node": _node_response(node)}


@router.put("/nodes/{node_id}", summary="更新知识节点 (全量, 含 prerequisites 重建)")
def update_node(node_id: str, body: KnowledgeNodeUpdate, request: Request):
    kg = _get_kg(request)
    if not kb_store.node_id_exists(KB_BASE, node_id):
        raise HTTPException(status_code=404, detail=f"节点 {node_id} 不存在")
    node = body.model_dump(exclude_none=False)
    node["id"] = node_id  # 路径为准
    # 保留原 created_at
    old = kb_store.load_node(KB_BASE, node_id) or {}
    node["created_at"] = old.get("created_at", _now_iso())

    errors = validate_node(node, _schema(), _all_node_ids())
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})

    kb_store.save_node(KB_BASE, node)
    warnings = _sync_node_to_neo4j(kg, node)
    return {"node": _node_response(node), "warnings": warnings}


@router.delete("/nodes/{node_id}", summary="删除知识节点")
def delete_node(node_id: str, request: Request,
                cascade: bool = Query(False, description="连带删除该节点的题目")):
    kg = _get_kg(request)
    if not kb_store.node_id_exists(KB_BASE, node_id):
        raise HTTPException(status_code=404, detail=f"节点 {node_id} 不存在")

    deleted_questions = []
    if cascade:
        # 删该节点全部题目 (JSON + Neo4j)
        qs = kb_store.load_questions_for_node(KB_BASE, node_id)
        for q in qs:
            qid = q.get("qid")
            if qid:
                kb_store.delete_question(KB_BASE, qid)
                try:
                    kg.delete_question(qid)
                except Exception:
                    logger.warning("Neo4j 删题失败 %s", qid, exc_info=True)
                deleted_questions.append(qid)

    kb_store.delete_node(KB_BASE, node_id)
    warnings = []
    try:
        kg.delete_knowledge_node(node_id)
    except Exception as e:
        logger.warning("Neo4j 删节点失败 %s", node_id, exc_info=True)
        warnings.append(f"Neo4j 删除失败: {e} (JSON 已删, 下次 import 修复)")
    return {"node_id": node_id, "deleted": True, "deleted_questions": deleted_questions,
            "warnings": warnings}


# ============================================================
# 题目 CRUD
# ============================================================

@router.post("/questions", summary="创建题目")
def create_question(body: QuestionCreate, request: Request):
    kg = _get_kg(request)
    # source_node_id 须存在
    if not kb_store.node_id_exists(KB_BASE, body.source_node_id):
        raise HTTPException(status_code=400, detail=f"source_node_id {body.source_node_id} 不存在")

    qid = body.qid
    if qid:
        if kb_store.find_question(KB_BASE, qid) is not None:
            raise HTTPException(status_code=409, detail=f"题目 {qid} 已存在")
    else:
        qid = kb_store.next_question_id(KB_BASE, body.source_node_id)

    question = body.model_dump(exclude_none=False)
    question["qid"] = qid
    question["created_at"] = _now_iso()

    errors = validate_question(question, qid, known_node_ids=_all_node_ids())
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})

    kb_store.save_question(KB_BASE, question)
    warnings = _sync_question_to_neo4j(kg, question)
    return {"question": question, "warnings": warnings}


@router.get("/questions/{qid}", summary="查询单个题目")
def get_question(qid: str, request: Request):
    kg = _get_kg(request)
    q = kg.get_question(qid)
    if q is None:
        found = kb_store.find_question(KB_BASE, qid)
        q = found[2] if found else None
    if q is None:
        raise HTTPException(status_code=404, detail=f"题目 {qid} 不存在")
    return {"question": q}


@router.put("/questions/{qid}", summary="更新题目")
def update_question(qid: str, body: QuestionUpdate, request: Request):
    kg = _get_kg(request)
    found = kb_store.find_question(KB_BASE, qid)
    if found is None:
        raise HTTPException(status_code=404, detail=f"题目 {qid} 不存在")
    question = body.model_dump(exclude_none=False)
    question["qid"] = qid
    old = found[2]
    question["created_at"] = old.get("created_at", _now_iso())

    if not kb_store.node_id_exists(KB_BASE, question["source_node_id"]):
        raise HTTPException(status_code=400, detail=f"source_node_id {question['source_node_id']} 不存在")

    errors = validate_question(question, qid, known_node_ids=_all_node_ids())
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})

    kb_store.save_question(KB_BASE, question)
    warnings = _sync_question_to_neo4j(kg, question)
    return {"question": question, "warnings": warnings}


@router.delete("/questions/{qid}", summary="删除题目")
def delete_question(qid: str, request: Request):
    kg = _get_kg(request)
    if kb_store.find_question(KB_BASE, qid) is None:
        raise HTTPException(status_code=404, detail=f"题目 {qid} 不存在")
    kb_store.delete_question(KB_BASE, qid)
    warnings = []
    try:
        kg.delete_question(qid)
    except Exception as e:
        logger.warning("Neo4j 删题失败 %s", qid, exc_info=True)
        warnings.append(f"Neo4j 删除失败: {e} (JSON 已删, 下次 import 修复)")
    return {"qid": qid, "deleted": True, "warnings": warnings}


# ============================================================
# 辅助: Neo4j 同步 + 响应格式化
# ============================================================

def _sync_node_to_neo4j(kg, node: dict) -> list[str]:
    """同步节点到 Neo4j + 重算 embedding。失败返 warning 列表 (不抛)。"""
    warnings = []
    try:
        kg.upsert_knowledge_node(node)
    except Exception as e:
        logger.warning("Neo4j 同步节点失败 %s", node.get("id"), exc_info=True)
        warnings.append(f"Neo4j 同步失败: {e} (JSON 已写, 下次 import 修复)")
    # embedding 重算 (内容变 → 向量过时)
    try:
        kg.generate_embeddings([node])
    except Exception as e:
        logger.warning("embedding 重算失败 %s", node.get("id"), exc_info=True)
        warnings.append(f"embedding 重算失败: {e} (非阻塞, 可重导修复)")
    return warnings


def _sync_question_to_neo4j(kg, question: dict) -> list[str]:
    warnings = []
    try:
        kg.upsert_question(question)
    except Exception as e:
        logger.warning("Neo4j 同步题目失败 %s", question.get("qid"), exc_info=True)
        warnings.append(f"Neo4j 同步失败: {e} (JSON 已写, 下次 import 修复)")
    return warnings


def _node_response(node: dict) -> dict:
    """格式化节点响应: practice_questions 若为 str (Neo4j 读回) 则反序列化为 list。"""
    pq = node.get("practice_questions")
    if isinstance(pq, str):
        try:
            node = {**node, "practice_questions": json.loads(pq)}
        except Exception:
            pass
    return node
