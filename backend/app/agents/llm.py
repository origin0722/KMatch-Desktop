"""
LLM 调用封装

统一通过 get_chat_model() 获取 DeepSeek Chat 模型实例，
所有 Agent 节点共用，便于单测 mock 与配置集中管理。

复用 app.config.settings 的 LLM_* 配置（DeepSeek，OpenAI 兼容接口）。
对齐 01_orchestrator_agent.txt 注意事项：LLM 超时最多重试 2 次。
"""

from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.config import settings


def get_chat_model(temperature: float = None) -> ChatOpenAI:
    """创建 DeepSeek Chat 模型实例。

    Args:
        temperature: 生成温度，None 时用 settings.LLM_TEMPERATURE (0.3)

    Returns:
        ChatOpenAI 实例（OpenAI 兼容，指向 DeepSeek endpoint）

    Note:
        max_retries=2 对齐 orchestrator prompt「LLM 超时重试 2 次」要求。
        未配置真实 key（sk-placeholder）时仍返回实例，调用时由上层降级处理。
    """
    return ChatOpenAI(
        model=settings.LLM_MODEL,
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        temperature=temperature if temperature is not None else settings.LLM_TEMPERATURE,
        max_retries=2,
        timeout=settings.LLM_TIMEOUT,
    )


@lru_cache(maxsize=1)
def get_default_chat_model() -> ChatOpenAI:
    """单例：全流程共享的默认 Chat 模型实例。

    Agent 节点默认用此实例避免重复构造。单测可通过 lru_cache 的 cache_clear
    或直接调用 get_chat_model() 注入 mock。
    """
    return get_chat_model()


def llm_configured() -> bool:
    """是否配置了真实 LLM API Key（非占位符）。"""
    return settings.LLM_API_KEY not in ("", "sk-placeholder")
