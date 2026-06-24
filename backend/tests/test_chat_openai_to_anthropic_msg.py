"""场景: OpenAI 消息形式 → Anthropic messages.create 参数。

输入是前端发的 OpenAI 风格 messages, 含可能的多模态 content 数组、system 消息;
输出是 Anthropic SDK 要的 (system_text, [{role, content: parts}])。
"""
from app.api.chat import _split_system, _openai_msg_to_anthropic


def test_split_system_concatenates_multiple_system_messages():
    msgs = [
        {"role": "system", "content": "S1"},
        {"role": "user", "content": "U1"},
        {"role": "system", "content": "S2"},
        {"role": "assistant", "content": "A1"},
    ]
    system, ua = _split_system(msgs)
    assert system == "S1\n\nS2"
    assert [m["role"] for m in ua] == ["user", "assistant"]


def test_openai_msg_text_only_passthrough():
    out = _openai_msg_to_anthropic({"role": "user", "content": "hello"})
    assert out == {"role": "user", "content": "hello"}


def test_openai_msg_multimodal_data_url_image():
    msg = {"role": "user", "content": [
        {"type": "text", "text": "what is this?"},
        {"type": "image_url",
         "image_url": {"url": "data:image/png;base64,AAAA"}},
    ]}
    out = _openai_msg_to_anthropic(msg)
    assert out["role"] == "user"
    assert out["content"][0] == {"type": "text", "text": "what is this?"}
    assert out["content"][1] == {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": "AAAA"},
    }


def test_openai_msg_multimodal_url_image():
    msg = {"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": "https://example.com/x.png"}},
    ]}
    out = _openai_msg_to_anthropic(msg)
    assert out["content"][0] == {
        "type": "image",
        "source": {"type": "url", "url": "https://example.com/x.png"},
    }
