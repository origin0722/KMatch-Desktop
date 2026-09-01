"""场景: _build_request_extras — protocol × model × reasoning_mode 映射 (off/default/high/max 四档)。"""
import pytest
from app.api.chat import _build_request_extras


@pytest.mark.parametrize("protocol,model,mode,expect", [
    # DeepSeek-V4 走 extra_body.thinking (off 显式关; default 不传跟随模型默认; high/max 开启)
    ('openai', 'deepseek-v4-pro', 'off', {'extra_body': {'thinking': {'type': 'disabled'}}}),
    ('openai', 'deepseek-v4-pro', 'default', {}),
    ('openai', 'deepseek-v4-pro', 'high', {'extra_body': {'thinking': {'type': 'enabled'}}}),
    ('openai', 'deepseek-v4-pro', 'max', {'extra_body': {'thinking': {'type': 'enabled'}}}),

    # Anthropic claude-fable-5 (default 不附加; high/max 递增 budget)
    ('anthropic', 'claude-fable-5', 'default', {}),
    ('anthropic', 'claude-fable-5', 'high', {'thinking': {'type': 'enabled', 'budget_tokens': 8000}}),
    ('anthropic', 'claude-fable-5', 'max', {'thinking': {'type': 'enabled', 'budget_tokens': 16000}}),
    ('anthropic', 'claude-fable-5', 'off', {'thinking': {'type': 'disabled'}}),

    # OpenAI o1/o3 reasoning_effort (off=minimal, default=medium, high/max=high)
    ('openai', 'o1', 'default', {'reasoning_effort': 'medium'}),
    ('openai', 'o3-mini', 'high', {'reasoning_effort': 'high'}),
    ('openai', 'o1', 'max', {'reasoning_effort': 'high'}),
    ('openai', 'o1', 'off', {'reasoning_effort': 'minimal'}),

    # 其他模型: 不传 extras
    ('openai', 'gpt-4o', 'high', {}),
    ('openai', 'gpt-4o', 'off', {}),
])
def test_build_request_extras(protocol, model, mode, expect):
    assert _build_request_extras(protocol, model, mode) == expect