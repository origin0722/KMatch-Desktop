"""redaction 交互日志脱敏组件单测。

覆盖:
  - mask_secret: 长度保持 / 首尾保留位 / 短串退化 / None / 空串
  - redact_keys: 嵌套 dict/list 命中、大小写不敏感子串、非敏感键原样保留
  - should_redact: 默认关闭、以及开启取值兼容
"""

from app.utils.redaction import (
    DEFAULT_SENSITIVE_KEYS,
    mask_secret,
    redact_keys,
    should_redact,
)


# ---------------------------------------------------------------- mask_secret

def test_mask_secret_long_preserves_ends_and_length():
    s = "sk-abcdefgh1234567"  # 17 字符
    m = mask_secret(s)
    assert len(m) == len(s)
    assert m[:4] == s[:4]
    assert m[-4:] == s[-4:]
    assert m[4:-4] == "*" * (len(s) - 8)


def test_mask_secret_short_fully_masked():
    assert mask_secret("abcd") == "****"
    assert mask_secret("a") == "*"


def test_mask_secret_mid_length_degrades_gracefully():
    # 4 < len <= 8: 首尾各 2 保留 (短串首尾各 4 会相互重叠, 退化为各 2), 中间打码
    m = mask_secret("abcdefg")  # 7 字符
    assert len(m) == 7
    assert m[:2] == "ab"
    assert m[-2:] == "fg"
    assert m[2:-2] == "*" * 3


def test_mask_secret_none_and_empty():
    assert mask_secret(None) is None
    assert mask_secret("") == ""


# ---------------------------------------------------------------- redact_keys

def test_redact_keys_nested_hits():
    obj = {
        "target_direction": "Python 入门",
        "answers": ["A", "B"],
        "practical_evidence": {"tests_passed": 3, "tests_total": 4},
        "learner_key": "learner-abc",
        "api_key": "sk-abc123",
        "nested": {
            "user_email": "a@example.com",
            "safe_field": "ok",
            "list": [{"student_name": "Alice"}, "plain"],
        },
    }
    out = redact_keys(obj)
    # 非敏感键原样保留
    assert out["target_direction"] == "Python 入门"
    assert out["nested"]["safe_field"] == "ok"
    assert out["nested"]["list"][1] == "plain"
    # 命中键名的值被打码 (answers 列表整体被打码成字符串, 不泄露原文)
    assert out["answers"] != ["A", "B"]
    assert out["practical_evidence"] != {"tests_passed": 3, "tests_total": 4}
    assert out["learner_key"] != "learner-abc"
    assert out["api_key"] != "sk-abc123"
    # 嵌套命中
    assert out["nested"]["user_email"] != "a@example.com"
    assert out["nested"]["list"][0]["student_name"] != "Alice"


def test_redact_keys_case_insensitive_substring():
    # 键名匹配为「大小写不敏感子串」: api_key/learner_key/name/phone 均命中
    obj = {"API_KEY": "sk-abc", "Learner_Key": "lk-1", "userName": "Bob", "PHONE": "138", "safe": "ok"}
    out = redact_keys(obj)
    assert out["API_KEY"] != "sk-abc"
    assert out["Learner_Key"] != "lk-1"
    assert out["userName"] != "Bob"
    assert out["PHONE"] != "138"
    assert out["safe"] == "ok"


def test_redact_keys_does_not_mutate_input():
    obj = {"answers": ["secret"], "target_direction": "Python"}
    redact_keys(obj)
    assert obj["answers"] == ["secret"]  # 原对象未被修改


def test_redact_keys_preserves_non_matching_structure():
    obj = {"target_direction": "x", "scene": "no_project", "max_retries": 3}
    assert redact_keys(obj) == obj


def test_redact_keys_scalars_pass_through():
    assert redact_keys("hello") == "hello"
    assert redact_keys(42) == 42
    assert redact_keys(None) is None


def test_default_sensitive_keys_present():
    for k in ("answer", "explanation", "practical_evidence", "api_key", "learner_key", "email", "phone", "name"):
        assert k in DEFAULT_SENSITIVE_KEYS


# ---------------------------------------------------------------- should_redact

def test_should_redact_default_off(monkeypatch):
    monkeypatch.delenv("PRIVACY_REDACT_INTERACTION_LOGS", raising=False)
    assert should_redact() is False


def test_should_redact_on_values(monkeypatch):
    monkeypatch.setenv("PRIVACY_REDACT_INTERACTION_LOGS", "1")
    assert should_redact() is True
    monkeypatch.setenv("PRIVACY_REDACT_INTERACTION_LOGS", "true")
    assert should_redact() is True
    monkeypatch.setenv("PRIVACY_REDACT_INTERACTION_LOGS", "True")
    assert should_redact() is True
    monkeypatch.setenv("PRIVACY_REDACT_INTERACTION_LOGS", " yes ")
    assert should_redact() is True


def test_should_redact_off_values(monkeypatch):
    monkeypatch.setenv("PRIVACY_REDACT_INTERACTION_LOGS", "0")
    assert should_redact() is False
    monkeypatch.setenv("PRIVACY_REDACT_INTERACTION_LOGS", "false")
    assert should_redact() is False
    monkeypatch.setenv("PRIVACY_REDACT_INTERACTION_LOGS", "anything")
    assert should_redact() is False
