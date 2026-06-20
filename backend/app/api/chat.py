"""
AI 助手聊天 API — SSE 流式对话 (阶段2)

POST /api/chat/completions
  请求: { messages: [{role, content}, ...], stream: bool }
  响应: SSE 流 text/event-stream (stream=true) 或 JSON (stream=false)

技术选型:
  - 复用 lifespan 创建的 app.state.openai_client 单例 (DeepSeek, OpenAI 兼容)
  - SSE 格式与前端 fetch + ReadableStream 对接
  - 模型配置: settings.LLM_MODEL (默认 deepseek-v4-pro)
"""

import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.config import settings

router = APIRouter()


class ChatRequest(BaseModel):
    messages: list[dict] = Field(
        ...,
        description="对话消息数组, 每项 {role: 'user'|'assistant'|'system', content: str}",
        min_length=1,
    )
    stream: bool = Field(True, description="是否 SSE 流式返回")
    max_tokens: int = Field(4096, ge=1, le=32768, description="最大生成 token 数")


# ----------------------------------------------------------------
# 流式生成器 — SSE 格式
# ----------------------------------------------------------------
async def _stream_chat(openai_client, messages: list[dict], max_tokens: int):
    """逐 token 推送 SSE 事件: data: {"delta": "..."} ... data: [DONE]"""
    try:
        stream = openai_client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=messages,
            stream=True,
            max_tokens=max_tokens,
            temperature=0.7,  # 对话场景比 Agent 任务稍高
        )

        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield f"data: {json.dumps({'delta': delta.content}, ensure_ascii=False)}\n\n"

        yield "data: [DONE]\n\n"

    except Exception as exc:
        err_msg = str(exc)
        yield f"data: {json.dumps({'error': err_msg}, ensure_ascii=False)}\n\n"


# ----------------------------------------------------------------
# 路由
# ----------------------------------------------------------------
@router.post("/completions")
async def chat_completions(req: ChatRequest, request: Request):
    """AI 助手对话 (SSE 流式, OpenAI 兼容格式)

    请求体:
      {
        "messages": [
          {"role": "system", "content": "你是一个编程助手..."},
          {"role": "user", "content": "解释这段代码..."}
        ],
        "stream": true,
        "max_tokens": 4096
      }

    响应 (stream=true):
      Content-Type: text/event-stream
      data: {"delta": "你好"}
      data: {"delta": "！"}
      data: [DONE]

    响应 (stream=false):
      Content-Type: application/json
      { "content": "完整回复文本" }
    """
    openai_client = getattr(request.app.state, "openai_client", None)

    if openai_client is None:
        detail = "LLM 未配置（请设置 LLM_API_KEY）"
        if req.stream:
            return StreamingResponse(
                iter([f"data: {json.dumps({'error': detail}, ensure_ascii=False)}\n\n"]),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache"},
            )
        return {"error": detail}

    if req.stream:
        return StreamingResponse(
            _stream_chat(openai_client, req.messages, req.max_tokens),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # 禁用 nginx 缓冲 (如有反向代理)
            },
        )

    # 非流式 fallback
    try:
        completion = openai_client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=req.messages,
            stream=False,
            max_tokens=req.max_tokens,
            temperature=0.7,
        )
        content = completion.choices[0].message.content if completion.choices else ""
        return {"content": content}
    except Exception as exc:
        return {"error": str(exc)}
