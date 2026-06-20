"""
AI 助手聊天 API — SSE 流式对话 (阶段3)

POST /api/chat/completions
  请求: { messages, stream?, max_tokens?, model?, api_key?, base_url? }
  响应: SSE text/event-stream 或 JSON

POST /api/chat/models
  请求: { base_url, api_key }
  响应: { models: [...] }  — 从厂商 /models 端点拉取
"""

import json
from functools import lru_cache

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from openai import OpenAI
from pydantic import BaseModel, Field

from app.config import settings

router = APIRouter()


class ChatRequest(BaseModel):
    messages: list[dict] = Field(
        ...,
        description="对话消息数组",
        min_length=1,
    )
    stream: bool = Field(True, description="是否 SSE 流式返回")
    max_tokens: int = Field(4096, ge=1, le=32768, description="最大生成 token 数")
    model: str | None = Field(None, description="模型名称, 不传则使用默认")
    api_key: str | None = Field(None, description="用户 API Key, 不传则用服务端默认")
    base_url: str | None = Field(None, description="API Base URL, 不传则用服务端默认")


class ModelsRequest(BaseModel):
    base_url: str = Field(..., description="API Base URL (如 https://api.deepseek.com/v1)")
    api_key: str = Field(..., description="API Key")


# ----------------------------------------------------------------
# OpenAI client 缓存 (按 base_url + api_key)
# ----------------------------------------------------------------
@lru_cache(maxsize=16)
def _get_client(base_url: str, api_key: str) -> OpenAI:
    """缓存 OpenAI client, 相同 (base_url, api_key) 复用"""
    return OpenAI(base_url=base_url, api_key=api_key)


def _resolve_client(req: ChatRequest) -> OpenAI | None:
    """优先用请求中的 api_key/base_url, 否则回退到服务端默认"""
    if req.api_key:
        base = req.base_url or settings.LLM_BASE_URL
        return _get_client(base, req.api_key)
    # fallback 到 lifespan 创建的单例
    return None  # caller 自行处理


# ----------------------------------------------------------------
# 流式生成器 — SSE 格式
# ----------------------------------------------------------------
async def _stream_chat(client: OpenAI, messages: list[dict], max_tokens: int, model: str):
    """逐 token 推送 SSE 事件"""
    try:
        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
            max_tokens=max_tokens,
            temperature=0.7,
        )

        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta:
                data = {}
                if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                    data['reasoning'] = delta.reasoning_content
                if delta.content:
                    data['delta'] = delta.content
                if data:
                    yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

        yield "data: [DONE]\n\n"

    except Exception as exc:
        err_msg = str(exc)
        yield f"data: {json.dumps({'error': err_msg}, ensure_ascii=False)}\n\n"


# ----------------------------------------------------------------
# 路由
# ----------------------------------------------------------------
@router.post("/completions")
async def chat_completions(req: ChatRequest, request: Request):
    """AI 助手对话 (SSE 流式, OpenAI 兼容)"""
    model = req.model or settings.LLM_MODEL

    # 优先用户提供的 client, 否则用服务端默认
    dynamic_client = _resolve_client(req)
    client = dynamic_client or getattr(request.app.state, "openai_client", None)

    if client is None:
        detail = "LLM 未配置（请设置 API Key）"
        if req.stream:
            return StreamingResponse(
                iter([f"data: {json.dumps({'error': detail}, ensure_ascii=False)}\n\n"]),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache"},
            )
        return {"error": detail}

    if req.stream:
        return StreamingResponse(
            _stream_chat(client, req.messages, req.max_tokens, model),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # 非流式 fallback
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=req.messages,
            stream=False,
            max_tokens=req.max_tokens,
            temperature=0.7,
        )
        content = completion.choices[0].message.content if completion.choices else ""
        return {"content": content}
    except Exception as exc:
        return {"error": str(exc)}


@router.post("/models")
async def list_models(req: ModelsRequest):
    """拉取厂商模型列表 (OpenAI 兼容 /models 端点)"""
    try:
        client = _get_client(req.base_url, req.api_key)
        resp = client.models.list()
        ids = [m.id for m in resp.data] if hasattr(resp, 'data') else []
        return {"models": ids}
    except Exception as exc:
        return {"error": str(exc)}
