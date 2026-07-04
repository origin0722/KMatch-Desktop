"""
Agent 学习引擎 API 路由 (Spec B)

POST /api/agents/ping
  用请求体 llm_overrides 构造 ChatOpenAI 发一句 "ping"，验证 key/baseUrl/model 可用。
  供设置页「测试连接」按钮调用。不依赖 Neo4j / workflow。
"""

import asyncio

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.agents.llm import get_chat_model
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


class PingRequest(BaseModel):
    """测试连接请求：Agent 独立 LLM 配置覆写。"""
    llm_overrides: dict = Field(..., description="api_key/base_url/model 覆写")


@router.post("/ping", summary="测试 Agent 独立 LLM 配置连通性")
async def agents_ping(req: PingRequest):
    """用 req.llm_overrides 构造 ChatOpenAI 发一句 'ping'，验证可用。

    ChatOpenAI.invoke 是同步阻塞调用，用 asyncio.to_thread 包裹避免阻塞事件循环。
    """
    overrides = req.llm_overrides or {}
    try:
        model = get_chat_model(overrides=overrides)
        resp = await asyncio.to_thread(model.invoke, "ping")
        content = getattr(resp, "content", "") or ""
        return {"ok": True, "content": str(content)[:100]}
    except Exception as exc:
        logger.warning("agent ping 失败: %s", exc)
        return {"ok": False, "error": str(exc)}
