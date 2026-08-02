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


@router.post("/web", summary="联网搜索 (Tavily): 任意 query -> web_link 资源")
def web_search_api(req: WebSearchRequest):
    # 优先用前端传入的 key (UI 配置), 否则回退 .env 环境变量
    key = req.tavily_key or settings.TAVILY_API_KEY
    if not key:
        raise HTTPException(
            status_code=503,
            detail="未配置 Tavily API key (在设置页『联网搜索』处配置, 或 .env 设 TAVILY_API_KEY)",
        )
    q = (req.query or "").strip()
    if not q:
        raise HTTPException(status_code=422, detail="query 必填")
    results = search_web(q, key, max_results=req.max_results)
    logger.info("web_search query=%s hits=%d", q, len(results))
    return {"query": q, "results": results}
