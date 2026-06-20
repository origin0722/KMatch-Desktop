"""LLM 工厂单测 — 验证配置注入，不实际调用 API。"""

from app.agents import llm as llm_module
from app.agents.llm import get_chat_model, llm_configured
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
