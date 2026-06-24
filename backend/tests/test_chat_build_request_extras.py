"""场景: _build_request_extras — protocol × model × reasoning_mode 九宫格。"""
import pytest
from app.api.chat import _build_request_extras


@pytest.mark.parametrize("protocol,model,mode,expect", [
    # DeepSeek-V4 走 extra_body.thinking
    ('openai', 'deepseek-v4-pro', 'auto', {'extra_body': {'thinking': {'type': 'enabled'}}}),
    ('openai', 'deepseek-v4-pro', 'deep', {'extra_body': {'thinking': {'type': 'enabled'}}}),
    ('openai', 'deepseek-v4-pro', 'fast', {'extra_body': {'thinking': {'type': 'disabled'}}}),

    # Anthropic claude-fable-5
    ('anthropic', 'claude-fable-5', 'auto', {}),
    ('anthropic', 'claude-fable-5', 'deep', {'thinking': {'type': 'enabled', 'budget_tokens': 8000}}),
    ('anthropic', 'claude-fable-5', 'fast', {'thinking': {'type': 'disabled'}}),

    # OpenAI o1/o3
    ('openai', 'o1', 'auto', {'reasoning_effort': 'medium'}),
    ('openai', 'o3-mini', 'deep', {'reasoning_effort': 'high'}),
    ('openai', 'o1', 'fast', {'reasoning_effort': 'low'}),

    # 其他模型: 不传 extras
    ('openai', 'gpt-4o', 'deep', {}),
    ('openai', 'gpt-4o', 'fast', {}),
])
def test_build_request_extras(protocol, model, mode, expect):
    assert _build_request_extras(protocol, model, mode) == expect
