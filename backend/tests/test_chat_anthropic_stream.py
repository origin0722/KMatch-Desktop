"""场景: _stream_anthropic 把 Anthropic SDK 事件翻译成统一 SSE 帧。"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.api.chat import _stream_anthropic


class FakeDelta:
    def __init__(self, dtype, **kw):
        self.type = dtype
        for k, v in kw.items():
            setattr(self, k, v)


class FakeEvent:
    def __init__(self, etype, delta=None):
        self.type = etype
        self.delta = delta


class FakeStreamCtx:
    """模拟 client.messages.stream(...) 返回的 async context manager。"""
    def __init__(self, events):
        self._events = events

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def __aiter__(self):
        events = self._events
        async def gen():
            for e in events:
                yield e
        return gen()


@pytest.mark.asyncio
async def test_anthropic_stream_emits_reasoning_then_delta_then_done():
    events = [
        FakeEvent('content_block_delta', delta=FakeDelta('thinking_delta', thinking='思考中…')),
        FakeEvent('content_block_delta', delta=FakeDelta('text_delta', text='答案是 42')),
    ]
    fake_client = MagicMock()
    fake_client.messages.stream = MagicMock(return_value=FakeStreamCtx(events))

    frames = []
    messages = [{"role": "user", "content": "Q"}]
    async for chunk in _stream_anthropic(fake_client, messages, 'claude-fable-5', 1024, {}):
        frames.append(chunk)

    payloads = [json.loads(c.split('data: ', 1)[1].strip())
                for c in frames if 'data:' in c and '[DONE]' not in c]
    assert payloads[0] == {'reasoning': '思考中…'}
    assert payloads[1] == {'delta': '答案是 42'}
    assert frames[-1].strip() == 'data: [DONE]'


@pytest.mark.asyncio
async def test_anthropic_stream_emits_error_on_exception():
    fake_client = MagicMock()
    fake_client.messages.stream = MagicMock(side_effect=RuntimeError('boom'))
    frames = []
    async for chunk in _stream_anthropic(fake_client, [{"role": "user", "content": "Q"}],
                                          'claude-fable-5', 1024, {}):
        frames.append(chunk)
    assert any('"error"' in f and 'boom' in f for f in frames)
