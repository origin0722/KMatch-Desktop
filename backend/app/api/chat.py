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

import hashlib
import json
import os
import re
import tempfile
from urllib.parse import urlparse
from pathlib import Path
from typing import Literal

from anthropic import AsyncAnthropic
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from app.config import settings

router = APIRouter()

# Anthropic 无 /models 端点, 硬编码列表 (issue-86: 与前端 PROVIDERS 兜底对齐)
ANTHROPIC_MODELS = [
    'claude-opus-5', 'claude-sonnet-5',
    'claude-opus-4-8', 'claude-sonnet-4-6', 'claude-haiku-4-5',
]

# 76x100 PNG 写有 'test vision' 文字, 用于 vision 能力探测
# (Pillow 生成: 白底黑字, 两行 'test' / 'vision')
TEST_IMG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAEwAAABkCAIAAACjCkEnAAADFklEQVR4nOXZv0tyfRgG8MtrKBos"
    "l6IEp6BVkwgcOlb042BDRVs/KHAT+gsaGlqkoUWo3aBJaIkCN4kg2iMXhwLDTQ0hC/R+eRGkx/eB"
    "t+l5tOuzndv7iDf393Dg0mNm+OkIAYQAQgAhgBBACCAEEAIIAYQAQgAhgBBACCAEEAIIAYQAQgAh"
    "gBBACCAEEAIIAYQAQgAhgBBACCAEh0wmk9+57ZttXcLT8Sesz+erVCr/e9s327pxk4eHh7VabWlp"
    "qVwub29vLywsOI7z8PAAIJVKTU5OhsPhbDbbbkOvsF8NDQ2ZWTwev7+/N7Pn5+dgMGhmw8PDb29v"
    "T09POzs77bZe4fntcQ0EAuPj461KsVjM5/PxeLxarSYSicXFxZ47rugYurWi0dHR9/d3M2s0Grlc"
    "rvVRLpdbX1/f29vruU2i49rr9TYajY2NjYuLCzO7urpyXbdSqTiO8/n5WavVRkZG2m3Wo0PGYrGV"
    "lZWXlxfXdR3HmZ+fLxQKZnZ8fBwOh0OhUCqVardZjz6TPxIhgBBACCAEEAIIAYQAQgAhgBBACCAE"
    "EAIIAYQAQnzIx8fHs7Oz7xS7nEcuGQiFQsViEcDHx8fExESz2fT5fB3JciuPBFAqlWKxmOM4sVis"
    "VCq16gcHB9FoNBgMXl5eonvYF0dHR6enp2Z2c3Ozv7/fjh5/myxvbm6m02kzS6fTW1tbZjYwMHBy"
    "cmJmhUIhEAhY18DXi3w+v7y8bGaJROL29rY9z+7u7traWjabbbW1in6/v16vm1m9Xvf7/WbW399f"
    "LpdbPYODg9a1keTU1FS1Wo1EIs1m82uI/N9keWxsrGNIr9fb/p6uSp/ZcXpXV1eTyeT09LTH42lV"
    "qtVqNBqNRCLn5+fX19ftzrm5uUwmAyCTyczOzv77fLNbX0j2q3w+39fXd3d393UhHclyq1gsFl3X"
    "nZmZcV339fW1Y3tdtUmP3CvkpyIEEAIIAYQAQgAhgBBACCAEEAIIAYQAQgAhgBBACCAEEAIIAYQA"
    "QgAhgBBACCAEEAIIAYQAQgAhgBBACODf/gF/wj8a1dy1cMBPvwAAAABJRU5ErkJggg=="
)


class ChatRequest(BaseModel):
    messages: list[dict] = Field(..., min_length=1, description="对话消息数组")
    stream: bool = Field(True, description="是否 SSE 流式返回")
    max_tokens: int = Field(4096, ge=1, le=32768)
    model: str | None = Field(None)
    api_key: str | None = Field(None)
    base_url: str | None = Field(None)
    protocol: Literal['openai', 'anthropic'] = Field('openai', description="协议分支")
    reasoning_mode: Literal['default', 'high', 'max', 'off'] = Field(
        'default',
        description="思考程度: off=关闭思考 / default=模型默认 / high=增强思考 / max=最高思考",
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


class ProbeVisionRequest(BaseModel):
    base_url: str
    api_key: str
    model: str
    protocol: Literal['openai', 'anthropic'] = 'openai'


# ----------------------------------------------------------------
# AsyncOpenAI client 缓存 (按 base_url + api_key)
# 安全 (issue-45): 缓存键用 api_key 的 sha256 摘要, 不把原始 key 字符串驻留缓存;
# client 对象内部仍持有真实 key (发请求所需), 但不再额外留在 dict 键里。
# ----------------------------------------------------------------
_ASYNC_OPENAI_CLIENTS: dict[tuple[str, str], AsyncOpenAI] = {}
_ASYNC_ANTHROPIC_CLIENTS: dict[str, AsyncAnthropic] = {}


def _validate_base_url(base_url: str) -> str:
    """SSRF 收敛: 客户端传入的 base_url 只允许 http/https (issue-45)。

    允许任意 http(s) 厂商/内网 (如 Ollama 127.0.0.1), 但拒绝 file:/gopher:/
    dict: 等非 HTTP 协议造成的任意协议访问面。非法 → 400。
    """
    try:
        scheme = urlparse(base_url).scheme.lower()
    except Exception as exc:  # 缺 scheme / 畸形 URL
        raise HTTPException(status_code=400, detail=f"非法 base_url: {base_url}") from exc
    if scheme not in ("http", "https"):
        raise HTTPException(
            status_code=400,
            detail=f"base_url 仅支持 http/https, 收到: {scheme or '(空)'}",
        )
    return base_url.strip()


def _get_async_client(base_url: str, api_key: str) -> AsyncOpenAI:
    """缓存 AsyncOpenAI client, 相同 (base_url, api_key) 复用; 键用 key 哈希。"""
    key = (base_url, hashlib.sha256((api_key or "").encode()).hexdigest())
    if key not in _ASYNC_OPENAI_CLIENTS:
        _ASYNC_OPENAI_CLIENTS[key] = AsyncOpenAI(base_url=base_url, api_key=api_key)
        if len(_ASYNC_OPENAI_CLIENTS) > 32:  # 简单上限 (类 lru, 丢弃最早键), 防无界增长
            _ASYNC_OPENAI_CLIENTS.pop(next(iter(_ASYNC_OPENAI_CLIENTS)))
    return _ASYNC_OPENAI_CLIENTS[key]


def _get_anthropic_client(api_key: str) -> AsyncAnthropic:
    """缓存 AsyncAnthropic client (键用 key 哈希)。"""
    key = hashlib.sha256((api_key or "").encode()).hexdigest()
    if key not in _ASYNC_ANTHROPIC_CLIENTS:
        _ASYNC_ANTHROPIC_CLIENTS[key] = AsyncAnthropic(api_key=api_key)
        if len(_ASYNC_ANTHROPIC_CLIENTS) > 32:
            _ASYNC_ANTHROPIC_CLIENTS.pop(next(iter(_ASYNC_ANTHROPIC_CLIENTS)))
    return _ASYNC_ANTHROPIC_CLIENTS[key]


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
    reasoning_mode: 'off' | 'default' | 'high' | 'max'
    返回 kwargs 字典 — 调用方直接 kwargs.update(extras)。
    """
    # DeepSeek-V4 系列 + xiaomi MiMo 等: extra_body.thinking
    if protocol == 'openai' and _is_thinking_extra_body_model(model):
        thinking = 'disabled' if reasoning_mode == 'off' else 'enabled'
        return {'extra_body': {'thinking': {'type': thinking}}}

    # Anthropic Claude 4+: thinking param
    if protocol == 'anthropic' and _is_anthropic_reasoning_model(model):
        if reasoning_mode == 'off':
            return {'thinking': {'type': 'disabled'}}
        if reasoning_mode == 'high':
            return {'thinking': {'type': 'enabled', 'budget_tokens': 8000}}
        if reasoning_mode == 'max':
            return {'thinking': {'type': 'enabled', 'budget_tokens': 16000}}
        return {}

    # OpenAI o1/o3: reasoning_effort
    if protocol == 'openai' and re.match(r'^o[13]', (model or '').lower()):
        if reasoning_mode == 'off':
            return {'reasoning_effort': 'minimal'}
        if reasoning_mode in ('high', 'max'):
            return {'reasoning_effort': 'high'}
        return {'reasoning_effort': 'medium'}

    return {}


def _resolve_openai_client(req: ChatRequest) -> AsyncOpenAI | None:
    """优先用请求中的 api_key/base_url 建 AsyncOpenAI; 否则用服务端默认 (非 placeholder)。

    issue-45: 客户端传入 base_url 先过 scheme 白名单 (http/https), 防任意协议访问面。
    """
    if req.api_key:
        base = req.base_url or settings.LLM_BASE_URL
        if req.base_url:
            _validate_base_url(req.base_url)
        return _get_async_client(base, req.api_key)
    if settings.LLM_API_KEY and settings.LLM_API_KEY != "sk-placeholder":
        return _get_async_client(settings.LLM_BASE_URL, settings.LLM_API_KEY)
    return None


def _resolve_anthropic_client(req: ChatRequest) -> AsyncAnthropic | None:
    """Anthropic 仅认请求 api_key — 服务端默认 key 是 OpenAI 兼容, 不复用。"""
    if req.api_key:
        return _get_anthropic_client(req.api_key)
    return None


def _resolve_client(req: ChatRequest):
    """根据 protocol 分派 client; 返回 (client, protocol)。client=None 表示未配置。"""
    if req.protocol == 'anthropic':
        return _resolve_anthropic_client(req), 'anthropic'
    return _resolve_openai_client(req), 'openai'


# ----------------------------------------------------------------
# vision 能力探测缓存 (probe-vision) — 持久化到 {DATA_DIR}/vision_cache.json
# key = "{base_url}::{model}", value = bool (是否支持 vision OCR)
# 原子写: .tmp 同目录 + os.replace (跨平台原子 rename)
# ----------------------------------------------------------------
def _vision_cache_path() -> Path:
    p = Path(settings.DATA_DIR)
    p.mkdir(parents=True, exist_ok=True)
    return p / "vision_cache.json"


def _load_vision_cache() -> dict:
    path = _vision_cache_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}


def _save_vision_cache(cache: dict) -> None:
    path = _vision_cache_path()
    # 原子写: .tmp 同目录 + os.replace (跨平台原子 rename)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.vision_cache.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


# ----------------------------------------------------------------
# 流式生成器 — SSE 格式 (async for, 不阻塞事件循环)
# 两个函数发完全相同的 SSE 帧: {delta} / {reasoning} / {error} / [DONE]
# 前端 chat.js 不感知协议差异。
# ----------------------------------------------------------------
async def _stream_openai(client: AsyncOpenAI, messages: list[dict], max_tokens: int, model: str, extras: dict | None = None):
    """逐 token 推送 SSE 事件 (OpenAI 兼容协议, async for 释放事件循环)"""
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


async def _stream_anthropic(client, messages, model, max_tokens, extras=None):
    """逐 token 推送 SSE 事件 (Anthropic 协议) — 与 _stream_openai 帧形状完全一致。

    注意形参顺序与 _stream_openai 不同: 这里 model 在 max_tokens 前
    (与 Anthropic SDK messages.create 的关键字顺序一致, 也匹配测试调用)。
    """
    system_text, ua_msgs = _split_system(messages)
    anthropic_msgs = [_openai_msg_to_anthropic(m) for m in ua_msgs]
    try:
        kwargs = dict(model=model, max_tokens=max_tokens, messages=anthropic_msgs)
        if system_text:
            kwargs['system'] = system_text
        if extras:
            kwargs.update(extras)
        async with client.messages.stream(**kwargs) as stream:
            async for event in stream:
                if getattr(event, 'type', None) != 'content_block_delta':
                    continue
                d = getattr(event, 'delta', None)
                if d is None:
                    continue
                if d.type == 'thinking_delta':
                    yield f"data: {json.dumps({'reasoning': d.thinking}, ensure_ascii=False)}\n\n"
                elif d.type == 'text_delta':
                    yield f"data: {json.dumps({'delta': d.text}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as exc:
        yield f"data: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"


# ----------------------------------------------------------------
# 路由
# ----------------------------------------------------------------
@router.post("/completions")
async def chat_completions(req: ChatRequest, request: Request):
    """AI 助手对话 (SSE 流式, OpenAI / Anthropic 双协议, async 不阻塞)"""
    model = req.model or settings.LLM_MODEL

    # issue-45: _validate_base_url 不合规时抛 HTTPException(400) 由 FastAPI 统一返回; 其余正常
    client, protocol = _resolve_client(req)

    if client is None:
        detail = "LLM 未配置（请设置 API Key）"
        if req.stream:
            return StreamingResponse(
                iter([f"data: {json.dumps({'error': detail}, ensure_ascii=False)}\n\n"]),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache"},
            )
        return {"error": detail}

    extras = _build_request_extras(protocol, model, req.reasoning_mode)

    if req.stream:
        if protocol == 'anthropic':
            gen = _stream_anthropic(client, req.messages, model, req.max_tokens, extras)
        else:
            gen = _stream_openai(client, req.messages, req.max_tokens, model, extras)
        return StreamingResponse(
            gen,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # 非流式 fallback — 本期只走 OpenAI 路径; Anthropic 非流式留 future
    if protocol == 'anthropic':
        return {"error": "Anthropic 非流式 fallback 本期未实现, 请用 stream=true"}
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
    _validate_base_url(req.base_url)  # issue-45: scheme 白名单 → 非法直接 400
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


# ----------------------------------------------------------------
# probe-vision — 探测 model 是否支持 vision (OCR 测试图)
# ----------------------------------------------------------------
_VISION_PROMPT = ("You are given an image.\n"
                  "The image contains only text.\n"
                  "Extract the exact text from the image.\n"
                  "Return only the text. No explanation.")

_AUTH_ERR_TOKENS = ('unauthorized', 'authentication', 'invalid api key',
                    'api key', 'permission denied', '401')


@router.post("/probe-vision")
async def probe_vision(req: ProbeVisionRequest):
    """探测 model 是否支持 vision; 用一张 OCR 测试图发请求, 看回包是否包含 test/vision 两词。"""
    cache = _load_vision_cache()
    key = f"{req.base_url}::{req.model}"
    if key in cache:
        return {"vision": cache[key], "cached": True}

    _validate_base_url(req.base_url)  # issue-45: scheme 白名单 → 非法直接 400 (不写缓存)

    try:
        if req.protocol == 'openai':
            client = _get_async_client(req.base_url, req.api_key)
            resp = await client.chat.completions.create(
                model=req.model,
                messages=[
                    {"role": "system", "content": "You are a precise OCR assistant."},
                    {"role": "user", "content": [
                        {"type": "text", "text": _VISION_PROMPT},
                        {"type": "image_url",
                         "image_url": {"url": f"data:image/png;base64,{TEST_IMG_BASE64}"}},
                    ]},
                ],
                max_tokens=100, stream=False,
            )
            content = (resp.choices[0].message.content or "").strip().lower()
        else:  # anthropic
            client = _get_anthropic_client(req.api_key)
            resp = await client.messages.create(
                model=req.model, max_tokens=100,
                messages=[{"role": "user", "content": [
                    {"type": "text", "text": _VISION_PROMPT},
                    {"type": "image", "source": {
                        "type": "base64", "media_type": "image/png", "data": TEST_IMG_BASE64}},
                ]}],
            )
            content = (resp.content[0].text if resp.content else "").strip().lower()

        is_vision = ("test" in content and "vision" in content)
    except Exception as exc:
        err = str(exc).lower()
        if any(tok in err for tok in _AUTH_ERR_TOKENS):
            return {"vision": False, "cached": False, "error": "auth"}
        is_vision = False   # 非 auth 错: 判 False + 写缓存

    cache[key] = is_vision
    _save_vision_cache(cache)
    return {"vision": is_vision, "cached": False}


@router.delete("/probe-vision/cache")
async def clear_vision_cache():
    _save_vision_cache({})
    return {"ok": True}
