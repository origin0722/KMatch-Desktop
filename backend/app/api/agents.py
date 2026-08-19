"""
Agent 学习引擎 API 路由 (Spec B)

POST /api/agents/ping
  用请求体 llm_overrides 构造客户端发一句 "ping"，验证 key/baseUrl/model 可用。
  protocol=openai → ChatOpenAI; protocol=anthropic → AsyncAnthropic。
  供设置页「统一 API 设置」/「Agent 独立 key」的「测试连通性」按钮调用。不依赖 Neo4j / workflow。
"""

import asyncio

from fastapi import APIRouter
from pydantic import BaseModel, Field

from anthropic import AsyncAnthropic
from app.agents.llm import get_chat_model
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


class PingRequest(BaseModel):
    """测试连接请求：LLM 配置覆写 + 协议 (openai | anthropic)。"""
    llm_overrides: dict = Field(..., description="api_key/base_url/model 覆写")
    protocol: str = Field("openai", description="协议分支: openai | anthropic")


@router.post("/ping", summary="测试 LLM 配置连通性 (openai | anthropic)")
async def agents_ping(req: PingRequest):
    """用 req.llm_overrides 构造客户端发一句 'ping'，验证可用。

    ChatOpenAI.invoke 是同步阻塞调用，用 asyncio.to_thread 包裹避免阻塞事件循环；
    AsyncAnthropic.messages.create 本身异步，直接 await。
    """
    overrides = req.llm_overrides or {}
    try:
        if req.protocol == "anthropic":
            client = AsyncAnthropic(api_key=overrides.get("api_key"))
            resp = await client.messages.create(
                model=overrides.get("model"),
                max_tokens=8,
                messages=[{"role": "user", "content": "ping"}],
            )
            content = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        else:
            model = get_chat_model(overrides=overrides)
            resp = await asyncio.to_thread(model.invoke, "ping")
            content = getattr(resp, "content", "") or ""
        return {"ok": True, "content": str(content)[:100], "protocol": req.protocol}
    except Exception as exc:
        logger.warning("llm ping 失败 protocol=%s: %s", req.protocol, exc)
        # error 恒非空: 前端兜底显示真实原因而非"未知错误"
        return {"ok": False, "error": str(exc) or exc.__class__.__name__, "protocol": req.protocol}
