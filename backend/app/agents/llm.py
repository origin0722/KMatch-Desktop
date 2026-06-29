"""
LLM 调用封装

统一通过 get_chat_model() 获取 Chat 模型实例，
所有 Agent 节点共用，便于单测 mock 与配置集中管理。

复用 app.config.settings 的 LLM_* 配置（DeepSeek，OpenAI 兼容接口）。
对齐 01_orchestrator_agent.txt 注意事项：LLM 超时最多重试 2 次。

Spec B: per-request LLM overrides 通过 ContextVar 承载。
- 路由层从请求体 llm_overrides 字段提取，用 use_llm_overrides(overrides) 上下文管理器 set。
- 工作流路径：节点入口从 state["llm_overrides"] set/reset。
- content_generator 的 ThreadPoolExecutor 工作线程不继承 ContextVar，需在 _safe_generate 内重新 set。
- 无 override 时 get_default_chat_model() 走 lru_cache 默认实例（行为不变，单测兼容）。
"""

import contextvars
from functools import lru_cache
from typing import Optional, TypedDict

from langchain_openai import ChatOpenAI

from app.config import settings


class LlmOverrides(TypedDict, total=False):
    """Per-request LLM 覆写（来自请求体 llm_overrides 字段）。"""
    api_key: str
    base_url: str
    model: str
    protocol: str  # 本期仅 'openai'，预留


# ContextVar: 当前请求的 overrides；None 时走 settings 默认。
_current_overrides: contextvars.ContextVar[Optional[dict]] = contextvars.ContextVar(
    "kmatch_llm_overrides", default=None
)


class use_llm_overrides:
    """上下文管理器：在 with 块内设置当前 overrides，退出时 reset。

    overrides=None 时为 no-op（不设 ContextVar）。
    用于路由层直调路径（submit/feedback/learning report/project review/test）。
    """

    def __init__(self, overrides: Optional[dict]):
        self.overrides = overrides
        self.token = None

    def __enter__(self):
        if self.overrides is not None:
            self.token = _current_overrides.set(self.overrides)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.token is not None:
            _current_overrides.reset(self.token)
        return False


def get_chat_model(
    temperature: float = None,
    overrides: Optional[dict] = None,
) -> ChatOpenAI:
    """创建 Chat 模型实例。

    Args:
        temperature: 生成温度，None 时用 settings.LLM_TEMPERATURE (0.3)
        overrides: 显式覆写（优先于 ContextVar）；None 时读 _current_overrides。
                   字段缺省时回退 settings 默认（部分覆写，不整体替换）。

    Returns:
        ChatOpenAI 实例（OpenAI 兼容）

    Note:
        max_retries=2 对齐 orchestrator prompt「LLM 超时重试 2 次」要求。
        本函数始终返回新实例（override 路径不缓存）；无 override 时由
        get_default_chat_model 的 lru_cache 复用单例。
    """
    ovr = overrides if overrides is not None else _current_overrides.get()
    if ovr:
        api_key = ovr.get("api_key") or settings.LLM_API_KEY
        base_url = ovr.get("base_url") or settings.LLM_BASE_URL
        model = ovr.get("model") or settings.LLM_MODEL
    else:
        api_key = settings.LLM_API_KEY
        base_url = settings.LLM_BASE_URL
        model = settings.LLM_MODEL

    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature if temperature is not None else settings.LLM_TEMPERATURE,
        max_retries=2,
        timeout=settings.LLM_TIMEOUT,
    )


@lru_cache(maxsize=1)
def _get_default_chat_model_cached() -> ChatOpenAI:
    """无 override 时的单例实例（lru_cache 缓存，单测通过 cache_clear 清除）。"""
    return get_chat_model()


def get_default_chat_model() -> ChatOpenAI:
    """单例：全流程共享的默认 Chat 模型实例。

    Spec B: 若 ContextVar 已设 overrides，绕过缓存直接构造（按需实例）——
    必须在查 lru_cache 之前判断，否则已缓存的默认实例会被直接返回
    （lru_cache 命中时不执行函数体，函数内的 ContextVar 判断无法生效）。
    无 override 时返回缓存的默认实例（单测 monkeypatch 兼容）。
    """
    if _current_overrides.get() is not None:
        # 绕过 lru_cache（缓存键无参，无法区分 overrides；直接构造，不污染缓存）
        return get_chat_model()
    return _get_default_chat_model_cached()


# 单测通过 get_default_chat_model.cache_clear() 清缓存 —— 代理到内部 lru_cache。
get_default_chat_model.cache_clear = _get_default_chat_model_cached.cache_clear


def llm_configured() -> bool:
    """是否配置了真实 LLM API Key（非占位符）。

    Spec B: ContextVar 设了 overrides 且含 api_key 时，视为已配置
    （用户用独立 key 跑 Agent，即便后端 .env 是占位符）。
    """
    ovr = _current_overrides.get()
    if ovr and ovr.get("api_key"):
        return True
    return settings.LLM_API_KEY not in ("", "sk-placeholder")
