"""AI 对话流 usage 透传单测 (issue: 前端统计栏需要真实 token/缓存命中)。"""
import asyncio

from app.api import chat as chat_api


class _FakeDelta:
    content = 'hi'
    reasoning_content = None


class _FakeChoices:
    def __init__(self, delta):
        self.delta = delta


class _FakeChunk:
    def __init__(self, delta=None, usage=None):
        self.choices = [_FakeChoices(delta)] if delta is not None else []
        self.usage = usage


class _FakeUsage:
    def model_dump(self):
        return {"prompt_tokens": 10, "completion_tokens": 2, "prompt_cache_hit_tokens": 8}


class _FakeCompletions:
    def __init__(self):
        self.seen = None

    async def create(self, **kwargs):
        self.seen = kwargs

        async def gen():
            yield _FakeChunk(_FakeDelta())
            yield _FakeChunk(None, _FakeUsage())

        return gen()


class _FakeClient:
    def __init__(self):
        self.completions = _FakeCompletions()
        self.chat = type('_Chat', (), {'completions': self.completions})()


def test_stream_openai_forwards_usage_and_requests_include_usage():
    client = _FakeClient()

    async def collect():
        return [b async for b in chat_api._stream_openai(client, [], 100, 'deepseek-v4-pro')]

    blocks = asyncio.run(collect())
    text = ''.join(blocks)
    assert 'stream_options' in client.completions.seen
    assert client.completions.seen['stream_options'] == {'include_usage': True}
    # delta 帧 + usage 帧 + [DONE]
    assert '"delta"' in text
    assert '"usage"' in text
    assert '"prompt_tokens": 10' in text
    assert '[DONE]' in text
