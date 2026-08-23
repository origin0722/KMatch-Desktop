"""LLM 401 认证错误识别与友好化 (issue: 出题失败 401 根因 = 占位符 key)。"""
from app.agents.llm import friendly_llm_error, is_auth_error

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
