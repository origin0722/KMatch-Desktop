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
from functools import lru_cache

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
    reasoning: bool | None = Field(
        None,
        description="思考模式开关 (auto/None=模型默认, True=开启思考, False=关闭思考)。"
        "DeepSeek-V4 系列 (deepseek-v4-pro/v4) 需经 extra_body thinking 控制。",
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


def _is_deepseek_thinking_model(model: str) -> bool:
    """DeepSeek-V4 系列是 thinking 模型, 需经 extra_body thinking 控制开/关。
    借鉴 Apix llm_adapter: reasoning=False -> thinking disabled; True -> enabled。
    deepseek-reasoner 走原生 reasoning_content, 不在此列。"""
    m = (model or "").lower()
    return m.startswith("deepseek-v4") or m == "deepseek-reasoner-pro"


def _build_extra_body(model: str, reasoning: bool | None) -> dict:
    """构建厂商特定的 extra_body。
    - DeepSeek-V4 系列: thinking {enabled|disabled} (None 时默认 enabled, 保留模型能力)
    - 其他模型: 不传 extra_body
    """
    if not _is_deepseek_thinking_model(model):
        return {}
    # reasoning=None (auto): 保持 thinking enabled, 体现 reasoner 能力
    # reasoning=False: 关闭思考, 直接出 content (日常对话推荐)
    thinking_type = "disabled" if reasoning is False else "enabled"
    return {"thinking": {"type": thinking_type}}


def _resolve_client(req: ChatRequest) -> AsyncOpenAI | None:
    """
    优先用请求中的 api_key/base_url 建 AsyncOpenAI;
    否则用服务端默认 LLM_API_KEY/LLM_BASE_URL (需非 placeholder)。
    """
    if req.api_key:
        base = req.base_url or settings.LLM_BASE_URL
        return _get_async_client(base, req.api_key)
    # fallback: 服务端默认 key (非 placeholder 才可用)
    if settings.LLM_API_KEY and settings.LLM_API_KEY != "sk-placeholder":
        return _get_async_client(settings.LLM_BASE_URL, settings.LLM_API_KEY)
    return None


# ----------------------------------------------------------------
# 流式生成器 — SSE 格式 (async for, 不阻塞事件循环)
# ----------------------------------------------------------------
async def _stream_chat(client: AsyncOpenAI, messages: list[dict], max_tokens: int, model: str, extra_body: dict | None = None):
    """逐 token 推送 SSE 事件 (async for, 释放事件循环)"""
    try:
        kwargs = dict(
            model=model,
            messages=messages,
            stream=True,
            max_tokens=max_tokens,
            temperature=0.7,
        )
        # DeepSeek-V4 等需要 extra_body.thinking 控制 (借鉴 Apix llm_adapter)
        if extra_body:
            kwargs["extra_body"] = extra_body
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

    extra_body = _build_extra_body(model, req.reasoning)

    if req.stream:
        return StreamingResponse(
            _stream_chat(client, req.messages, req.max_tokens, model, extra_body),
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
        if extra_body:
            kwargs["extra_body"] = extra_body
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
