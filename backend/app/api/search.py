"""联网搜索 API (Tavily) - 供 AI 助手 web_search 工具调用, 结果落学习资源模块。

独立于 diagnostics 的 search_weak_topics (画像薄弱点批量搜): 本路由接受任意 query,
返回 [{title, url, snippet}] web_link 资源, 供 AI 助手按用户知识点掌握主动联网搜索,
减少幻觉 (呼应赛题学习资源 + 二次开发场景 AI 垂直领域知识检索)。

Tavily key 优先用前端传入 (UI 配置, 存 localStorage), 否则回退 settings.TAVILY_API_KEY
(.env 环境变量)。两者皆无时 503。
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.utils.web_search import search_web
from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


class WebSearchRequest(BaseModel):
    query: str = Field(..., description="搜索词")
    max_results: int = Field(3, ge=1, le=8, description="返回条数 (1-8)")
    tavily_key: str | None = Field(None, description="前端 UI 配置的 Tavily key (优先于环境变量)")


class WeakTopicsSearchRequest(BaseModel):
    """按画像薄弱点批量联网搜索 (资源页一键丰富)。

    topics: [{node_id, name}] — 前端从学情画像 weak_topics 取, name 可读名用于搜索词。
    max_per_topic: 每点返回条数 (1-5), 默认 3 — 让联网资源更丰富。
    direction: 学习目标方向 (如 Python/数据分析), 拼进搜索词锚定领域。
    """
    topics: list[dict] = Field(..., description="薄弱点 [{node_id, name}]")
    max_per_topic: int = Field(3, ge=1, le=5)
    direction: str | None = Field(None)
    tavily_key: str | None = Field(None)


@router.post("/web", summary="联网搜索 (Tavily): 任意 query -> web_link 资源")
def web_search_api(req: WebSearchRequest):
    # 优先用前端传入的 key (UI 配置), 否则回退 .env 环境变量
    key = req.tavily_key or settings.TAVILY_API_KEY
    if not key:
        raise HTTPException(
            status_code=503,
            detail="未配置 Tavily API key —— 请在 设置 → 联网搜索 填入 Key（安装包端用户同样适用）",
        )
    q = (req.query or "").strip()
    if not q:
        raise HTTPException(status_code=422, detail="query 必填")
    results = search_web(q, key, max_results=req.max_results)
    logger.info("web_search query=%s hits=%d", q, len(results))
    return {"query": q, "results": results}


@router.post("/weak-topics", summary="按画像薄弱点批量联网搜索 -> web_link 资源 (资源页一键丰富)")
def weak_topics_search_api(req: WeakTopicsSearchRequest):
    """对多个薄弱知识点逐个 Tavily 搜索, 每条带 target_node_id 可溯源。

    资源页"按薄弱点批量搜索"按钮调用: 一次拉回 3-5 个薄弱点的教程, 让联网资源 tab
    从"几篇"变成"十几篇"。key 解析同 /web。
    """
    key = req.tavily_key or settings.TAVILY_API_KEY
    if not key:
        raise HTTPException(
            status_code=503,
            detail="未配置 Tavily API key —— 请在 设置 → 联网搜索 填入 Key（安装包端用户同样适用）",
        )
    topics = [t for t in (req.topics or []) if isinstance(t, dict) and t.get("node_id")]
    if not topics:
        raise HTTPException(status_code=422, detail="topics 为空 (无薄弱点)")
    resources = []
    for t in topics[:5]:
        node_id = t.get("node_id", "")
        name = (t.get("name") or "").strip() or node_id
        query = f"{req.direction} {name} 教程 讲解 示例" if req.direction else f"{name} 教程 讲解 示例"
        for r in search_web(query, key, max_results=req.max_per_topic):
            resources.append({
                "content_type": "web_link",
                "title": r["title"],
                "url": r["url"],
                "content": r["snippet"],
                "target_node_id": node_id,
            })
    logger.info("weak_topics_search topics=%d resources=%d", len(topics), len(resources))
    return {"topics": len(topics), "results": resources}
