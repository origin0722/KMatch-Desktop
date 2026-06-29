"""LLM 工厂单测 — 验证配置注入，不实际调用 API。"""

from app.agents import llm as llm_module
from app.agents.llm import (
    get_chat_model,
    get_default_chat_model,
    llm_configured,
    use_llm_overrides,
    _current_overrides,
)
from app.config import settings


def test_get_chat_model_injects_config():
    """工厂应把 settings 的 LLM 配置注入 ChatOpenAI。"""
    # 清除单例缓存，确保读到当前配置
    llm_module.get_default_chat_model.cache_clear()

    model = get_chat_model()
    assert model.model_name == settings.LLM_MODEL
    # ChatOpenAI 内部用 api_key/base_url，校验非空注入
    assert model.openai_api_key.get_secret_value() == settings.LLM_API_KEY
    assert model.openai_api_base == settings.LLM_BASE_URL


def test_get_chat_model_custom_temperature():
    """自定义温度应覆盖 settings 默认值。"""
    model = get_chat_model(temperature=0.7)
    assert model.temperature == 0.7


def test_get_chat_model_default_temperature():
    """无自定义温度时用 settings.LLM_TEMPERATURE。"""
    model = get_chat_model()
    assert model.temperature == settings.LLM_TEMPERATURE


def test_llm_configured_with_real_key():
    """已配置真实 key 时 llm_configured 返回 True。"""
    # .env 已配真实 DeepSeek key（非 sk-placeholder）
    assert llm_configured() is True


def test_default_chat_model_is_singleton():
    """get_default_chat_model 应缓存为单例。"""
    llm_module.get_default_chat_model.cache_clear()
    m1 = llm_module.get_default_chat_model()
    m2 = llm_module.get_default_chat_model()
    assert m1 is m2


def test_get_chat_model_with_overrides():
    """overrides 应覆盖 settings 默认配置。"""
    overrides = {
        "api_key": "sk-override",
        "base_url": "https://override.example.com/v1",
        "model": "override-model",
    }
    model = get_chat_model(overrides=overrides)
    assert model.model_name == "override-model"
    assert model.openai_api_key.get_secret_value() == "sk-override"
    assert model.openai_api_base == "https://override.example.com/v1"


def test_get_default_chat_model_reads_contextvar():
    """ContextVar 设置后，get_default_chat_model 用 overrides 构造（不走 lru_cache 默认实例）。"""
    overrides = {"api_key": "sk-ctx", "base_url": "https://ctx.example.com/v1", "model": "ctx-model"}
    with use_llm_overrides(overrides):
        model = get_default_chat_model()
        assert model.model_name == "ctx-model"
        assert model.openai_api_key.get_secret_value() == "sk-ctx"
    # 退出上下文后回到 settings 默认
    llm_module.get_default_chat_model.cache_clear()
    assert get_default_chat_model().model_name == settings.LLM_MODEL


def test_use_llm_overrides_none_is_noop():
    """use_llm_overrides(None) 不设 ContextVar，get_default_chat_model 走默认。"""
    llm_module.get_default_chat_model.cache_clear()
    with use_llm_overrides(None):
        assert _current_overrides.get() is None
        assert get_default_chat_model().model_name == settings.LLM_MODEL


def test_get_chat_model_partial_overrides_merge_settings():
    """部分字段 overrides 时，缺省字段回退 settings（不整体替换）。"""
    overrides = {"model": "partial-model"}  # 无 api_key/base_url
    model = get_chat_model(overrides=overrides)
    assert model.model_name == "partial-model"
    assert model.openai_api_key.get_secret_value() == settings.LLM_API_KEY
    assert model.openai_api_base == settings.LLM_BASE_URL


def test_llm_configured_with_overrides_api_key():
    """ContextVar 设了含 api_key 的 overrides 时，llm_configured 返回 True（即便 .env 是占位符）。"""
    overrides = {"api_key": "sk-user-override", "base_url": "https://x.example.com/v1", "model": "m"}
    with use_llm_overrides(overrides):
        assert llm_configured() is True


def test_llm_configured_overrides_without_api_key_falls_through():
    """overrides 缺 api_key 时，llm_configured 回退到 settings 判断（不因有 overrides 就 True）。"""
    expected = settings.LLM_API_KEY not in ("", "sk-placeholder")
    with use_llm_overrides({"model": "only-model"}):
        assert llm_configured() is expected
