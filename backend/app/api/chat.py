"""
AI 助手聊天 API — SSE 流式对话 (S4: AsyncOpenAI + async for, 不阻塞事件循环)

POST /api/chat/completions
  请求: { messages, stream?, max_tokens?, model?, api_key?, base_url? }
  响应: SSE text/event-stream 或 JSON

POST /api/chat/models
  请求: { base_url, api_key }
  响应: { models: [...] }  — 从厂商 /models 端点拉取

注意: 本模块用 AsyncOpenAI (自给自足), 不依赖 lifespan 的同步 openai_client
(后者供 diagnostics 等同步路径用)。避免 async def 路由内迭代同步阻塞迭代器
导致事件循环冻结 (S4 修复)。
"""

import json
import re
from functools import lru_cache
from typing import Literal

from anthropic import AsyncAnthropic
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from app.config import settings

router = APIRouter()

# Anthropic 无 /models 端点, 硬编码列表 (按需更新)
ANTHROPIC_MODELS = [
    'claude-fable-5', 'claude-opus-4-8', 'claude-sonnet-4-6',
    'claude-haiku-4-5', 'claude-opus-4-7', 'claude-sonnet-4',
]


class ChatRequest(BaseModel):
    messages: list[dict] = Field(..., min_length=1, description="对话消息数组")
    stream: bool = Field(True, description="是否 SSE 流式返回")
    max_tokens: int = Field(4096, ge=1, le=32768)
    model: str | None = Field(None)
    api_key: str | None = Field(None)
    base_url: str | None = Field(None)
    protocol: Literal['openai', 'anthropic'] = Field('openai', description="协议分支")
    reasoning_mode: Literal['auto', 'fast', 'deep'] = Field(
        'auto',
        description="思考模式: auto=模型默认 / fast=关思考秒回 / deep=充分思考",
    )


class ModelsRequest(BaseModel):
    base_url: str = Field(..., description="API Base URL (如 https://api.deepseek.com/v1)")
    api_key: str = Field(..., description="API Key")
    protocol: str = Field('openai', description="协议: openai | anthropic")


class SafetyCheckRequest(BaseModel):
    code: str = Field(..., description="待检查的代码内容")
    filename: str | None = Field(
        None, description="文件名 (用于判断语言; 非 .py 直接判 safe, 跳过 AST)"
    )


# ----------------------------------------------------------------
# AsyncOpenAI client 缓存 (按 base_url + api_key)
# ----------------------------------------------------------------
@lru_cache(maxsize=16)
def _get_async_client(base_url: str, api_key: str) -> AsyncOpenAI:
    """缓存 AsyncOpenAI client, 相同 (base_url, api_key) 复用"""
    return AsyncOpenAI(base_url=base_url, api_key=api_key)


@lru_cache(maxsize=16)
def _get_anthropic_client(api_key: str) -> AsyncAnthropic:
    """缓存 AsyncAnthropic client (key 唯一索引)"""
    return AsyncAnthropic(api_key=api_key)


def _split_system(messages: list[dict]) -> tuple[str, list[dict]]:
    """把 system 消息抽出来拼成字符串 (Anthropic 的 system 是顶层 param);
    其余按原顺序返回。多个 system 消息以两个换行连接。"""
    sys_parts = [
        m["content"] for m in messages
        if m.get("role") == "system" and isinstance(m.get("content"), str)
    ]
    ua = [m for m in messages if m.get("role") != "system"]
    return ("\n\n".join(sys_parts), ua)


def _openai_msg_to_anthropic(msg: dict) -> dict:
    """OpenAI 风格 message → Anthropic 风格。

    - content 是 string: 原样回
    - content 是 OpenAI 多模态数组:
        - text 段: {type: 'text', text: ...}
        - image_url 段:
            url 以 data: 开头 → {type: image, source: {type: base64, media_type, data}}
            否则 → {type: image, source: {type: url, url}}
    """
    content = msg.get("content")
    if isinstance(content, str):
        return {"role": msg["role"], "content": content}
    parts = []
    for p in content or []:
        ptype = p.get("type")
        if ptype == "text":
            parts.append({"type": "text", "text": p.get("text", "")})
        elif ptype == "image_url":
            url = (p.get("image_url") or {}).get("url", "")
            if url.startswith("data:"):
                header, b64 = url.split(",", 1)
                media_type = header.split(";")[0].split(":")[1]
                parts.append({"type": "image",
                              "source": {"type": "base64",
                                         "media_type": media_type, "data": b64}})
            else:
                parts.append({"type": "image",
                              "source": {"type": "url", "url": url}})
    return {"role": msg["role"], "content": parts}


def _is_thinking_extra_body_model(model: str) -> bool:
    """走 extra_body.thinking 的模型 — DeepSeek-V4 / 后续 thinking 系列。"""
    m = (model or "").lower()
    return m.startswith("deepseek-v4") or m == "deepseek-reasoner-pro"


def _is_anthropic_reasoning_model(model: str) -> bool:
    """Anthropic Claude 4+ 支持 thinking param。"""
    m = (model or "").lower()
    return bool(re.match(r'^claude-(opus|sonnet|haiku|fable|mythos)-(4|5)', m))


def _build_request_extras(protocol: str, model: str, reasoning_mode: str) -> dict:
    """
    构造厂商特定的额外 kwargs (不含 messages/model/stream/max_tokens).
    reasoning_mode: 'auto' | 'fast' | 'deep'
    返回 kwargs 字典 — 调用方直接 kwargs.update(extras)。
    """
    # DeepSeek-V4 系列 + xiaomi MiMo 等: extra_body.thinking
    if protocol == 'openai' and _is_thinking_extra_body_model(model):
        thinking = 'disabled' if reasoning_mode == 'fast' else 'enabled'
        return {'extra_body': {'thinking': {'type': thinking}}}

    # Anthropic Claude 4+: thinking param
    if protocol == 'anthropic' and _is_anthropic_reasoning_model(model):
        if reasoning_mode == 'deep':
            return {'thinking': {'type': 'enabled', 'budget_tokens': 8000}}
        if reasoning_mode == 'fast':
            return {'thinking': {'type': 'disabled'}}
        return {}

    # OpenAI o1/o3: reasoning_effort
    if protocol == 'openai' and re.match(r'^o[13]', (model or '').lower()):
        if reasoning_mode == 'deep':
            return {'reasoning_effort': 'high'}
        if reasoning_mode == 'fast':
            return {'reasoning_effort': 'low'}
        return {'reasoning_effort': 'medium'}

    return {}


def _resolve_openai_client(req: ChatRequest) -> AsyncOpenAI | None:
    """优先用请求中的 api_key/base_url 建 AsyncOpenAI; 否则用服务端默认 (非 placeholder)。"""
    if req.api_key:
        base = req.base_url or settings.LLM_BASE_URL
        return _get_async_client(base, req.api_key)
    if settings.LLM_API_KEY and settings.LLM_API_KEY != "sk-placeholder":
        return _get_async_client(settings.LLM_BASE_URL, settings.LLM_API_KEY)
    return None


def _resolve_anthropic_client(req: ChatRequest) -> AsyncAnthropic | None:
    """Anthropic 仅认请求 api_key — 服务端默认 key 是 OpenAI 兼容, 不复用。"""
    if req.api_key:
        return _get_anthropic_client(req.api_key)
    return None


def _resolve_client(req: ChatRequest) -> AsyncOpenAI | None:
    """[兼容旧调用] 返回 OpenAI client。Task 12 会切换到 _resolve_client_dispatch。"""
    return _resolve_openai_client(req)


def _resolve_client_dispatch(req: ChatRequest):
    """根据 protocol 分派 client; 返回 (client, protocol)。None 表示未配置。"""
    if req.protocol == 'anthropic':
        return _resolve_anthropic_client(req), 'anthropic'
    return _resolve_openai_client(req), 'openai'


# ----------------------------------------------------------------
# 流式生成器 — SSE 格式 (async for, 不阻塞事件循环)
# ----------------------------------------------------------------
async def _stream_chat(client: AsyncOpenAI, messages: list[dict], max_tokens: int, model: str, extras: dict | None = None):
    """逐 token 推送 SSE 事件 (async for, 释放事件循环)"""
    try:
        kwargs = dict(
            model=model,
            messages=messages,
            stream=True,
            max_tokens=max_tokens,
            temperature=0.7,
        )
        if extras:
            kwargs.update(extras)
        stream = await client.chat.completions.create(**kwargs)

        async for chunk in stream:
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
    """AI 助手对话 (SSE 流式, OpenAI 兼容, async 不阻塞)"""
    model = req.model or settings.LLM_MODEL

    client = _resolve_client(req)

    if client is None:
        detail = "LLM 未配置（请设置 API Key）"
        if req.stream:
            return StreamingResponse(
                iter([f"data: {json.dumps({'error': detail}, ensure_ascii=False)}\n\n"]),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache"},
            )
        return {"error": detail}

    extras = _build_request_extras(req.protocol, model, req.reasoning_mode)

    if req.stream:
        return StreamingResponse(
            _stream_chat(client, req.messages, req.max_tokens, model, extras),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # 非流式 fallback (await, 不阻塞)
    try:
        kwargs = dict(
            model=model,
            messages=req.messages,
            stream=False,
            max_tokens=req.max_tokens,
            temperature=0.7,
        )
        if extras:
            kwargs.update(extras)
        completion = await client.chat.completions.create(**kwargs)
        content = completion.choices[0].message.content if completion.choices else ""
        return {"content": content}
    except Exception as exc:
        return {"error": str(exc)}


@router.post("/models")
async def list_models(req: ModelsRequest):
    """拉取厂商模型列表 (OpenAI 兼容 /models 端点 / Anthropic 硬编码)。"""
    if req.protocol == 'anthropic':
        return {"models": list(ANTHROPIC_MODELS)}
    try:
        client = _get_async_client(req.base_url, req.api_key)
        resp = await client.models.list()
        ids = [m.id for m in resp.data] if hasattr(resp, 'data') else []
        return {"models": ids}
    except Exception as exc:
        return {"error": str(exc)}


@router.post("/safety-check")
async def safety_check(req: SafetyCheckRequest):
    """write_file 审批门: 复用 hard_check_code_safety 做 AST 安全预检 (阶段3)。

    纯 AST 静态分析, 不执行代码。仅对 .py 文件检查; 非_python直接返回 safe。
    safe = 无 high severity 问题 (medium 如无限循环仅提示, 不阻断)。
    """
    from app.agents.code_safety import hard_check_code_safety

    if req.filename and not req.filename.lower().endswith(".py"):
        return {"language": "non-python", "issues": [], "safe": True, "checked": False}

    issues = hard_check_code_safety(req.code or "")
    safe = not any(i.get("severity") == "high" for i in issues)
    return {"language": "python", "issues": issues, "safe": safe, "checked": True}
