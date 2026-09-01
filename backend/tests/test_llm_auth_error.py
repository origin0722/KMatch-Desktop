"""LLM 401 认证错误识别与友好化 (issue: 出题失败 401 根因 = 占位符 key)。"""
from app.agents.llm import _current_overrides, friendly_llm_error, is_auth_error

# 用户实际收到的报错原文 (DeepSeek 对 sk-placeholder 的 401 响应)
AUTH_MSG = (
    "Error code: 401 - {'error': {'message': 'Authentication Fails, "
    "Your api key: ****lder is invalid', 'type': 'authentication_error', "
    "'param': None, 'code': 'invalid_request_error'}}"
)


def test_is_auth_error_detects_real_401():
    assert is_auth_error(Exception(AUTH_MSG))
    assert is_auth_error(Exception("401 Unauthorized"))
    assert is_auth_error(Exception("Invalid API Key provided"))
    assert not is_auth_error(Exception("Request timed out"))
    assert not is_auth_error(Exception("connection reset"))


def test_friendly_llm_error_maps_401_to_guidance():
    msg = friendly_llm_error(Exception(AUTH_MSG))
    assert "学习引擎 API Key 无效" in msg
    assert "测试连接" in msg
    assert "401" in msg
    # 不再糊原始英文报错
    assert "invalid_request_error" not in msg


def test_friendly_llm_error_keeps_first_line_for_other():
    msg = friendly_llm_error(Exception("boom\nsecond line"))
    assert msg == "boom"


# 桩值刻意避开真实凭据形态 (无厂商 key 前缀), 仅本地测试假值
_SNAPSHOT_KEY = "user-key-9999"
_WS_KEY = " user-key-with-space \n"


def test_friendly_llm_error_401_shows_effective_snapshot():
    """401 提示带生效配置快照: 端点/模型/key 尾号, 便于区分配错 key vs 端点不匹配。"""
    overrides = {"api_key": _SNAPSHOT_KEY, "base_url": " https://api.deepseek.com/v1 ", "model": " deepseek-v4-pro "}
    token = _current_overrides.set(overrides)
    try:
        msg = friendly_llm_error(Exception(AUTH_MSG))
    finally:
        _current_overrides.reset(token)
    assert "base_url=https://api.deepseek.com/v1" in msg
    assert "model=deepseek-v4-pro" in msg
    assert "…9999" in msg  # key 尾号 (掩码展示, 不泄漏全文)
    assert "测试连接" in msg


def test_friendly_llm_error_401_flags_whitespace_key():
    """key 首尾带空白 (粘贴带入) 时, 401 提示明确指出已自动去除。"""
    token = _current_overrides.set({"api_key": _WS_KEY})
    try:
        msg = friendly_llm_error(Exception(AUTH_MSG))
    finally:
        _current_overrides.reset(token)
    assert "空白字符" in msg


def test_friendly_llm_error_401_shows_provider_masked_key():
    """厂商 401 原文自带打码 key (****+尾4) → 透出「服务商判定无效的 key」决定性证据。"""
    exc = Exception(
        "Error code: 401 - {'error': {'message': 'Authentication Fails, "
        "Your api key: ****3e17 is invalid', 'type': 'authentication_error'}}"
    )
    msg = friendly_llm_error(exc)
    assert "服务商判定无效的 key：****3e17" in msg
    assert "重新生成" in msg


def test_friendly_llm_error_401_without_provider_key_skips_line():
    """厂商原文无打码 key 形态 (如裸 401) → 不输出该行, 不误报。"""
    msg = friendly_llm_error(Exception("401 Unauthorized"))
    assert "服务商判定无效的 key" not in msg
