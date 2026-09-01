"""交互日志脱敏组件 (赛题(5) 数据合规与伦理 — §数据合规与隐私保护说明 配套)。

本地单机 + 全合成测试数据场景默认关闭 (should_redact()=False)：run 落盘/日志按原样写，
保证复盘与联调可读、且**不改变任何既有默认行为**。将来接入真实培训数据时，置环境变量
`PRIVACY_REDACT_INTERACTION_LOGS=1`，则在 run.json/events.jsonl 落盘前对 request 内的
敏感字段 (答题原文 answers / 实操证据 practical_evidence / 学习者标识 learner_key /
API key / 邮箱 / 手机 / 姓名等) 做打码。

本模块为纯 stdlib (os/typing 仅此)，不依赖 FastAPI/LLM/配置，供 run_store 及后续任何
需要落盘交互数据的组件复用。
"""

from __future__ import annotations

import os
from typing import Any

# 脱敏开关环境变量名 (默认关闭)
REDACT_ENV = "PRIVACY_REDACT_INTERACTION_LOGS"

# 默认敏感键名 (键名匹配为「大小写不敏感子串」，故 api_key/APIKey/apiKey 均命中)。
#   answer / explanation        —— 答题原文与解析 (判分/反馈落盘的敏感内容)
#   practical_evidence          —— 实操能力证据 (代码测试通过率等)
#   api_key                     —— LLM/Tavily/本地密钥
#   learner_key                 —— 学习者稳定标识 (跨次画像档案) 的键
#   email / phone / name        —— 直接或间接标识符
DEFAULT_SENSITIVE_KEYS: list[str] = [
    "answer",
    "explanation",
    "practical_evidence",
    "api_key",
    "learner_key",
    "email",
    "phone",
    "name",
]


def mask_secret(value: Any) -> Any:
    """对单个值打码：保留首 4 尾 4、中间以 ``*`` 替换，长度保持不变。

    - ``None`` -> ``None``（原样返回，便于 JSON 序列化）
    - 空串 -> 空串
    - 长度 <= 4 -> 全量打码（无法暴露任何可辨识片段）
    - 4 < 长度 <= 8 -> 保留首 2 尾 2、中间打码（短串若保留首尾各 4 会相互重叠，退化为各 2）
    - 长度 > 8 -> 保留首 4 尾 4、中间打码
    """
    if value is None:
        return None
    s = str(value)
    n = len(s)
    if n == 0:
        return ""
    if n <= 4:
        return "*" * n
    if n <= 8:
        return s[:2] + "*" * (n - 4) + s[-2:]
    return s[:4] + "*" * (n - 8) + s[-4:]


def _is_sensitive(key: Any, sensitive: list[str]) -> bool:
    """键名是否命中敏感清单（大小写不敏感子串匹配）。"""
    k = str(key).lower()
    return any(pat in k for pat in sensitive)


def redact_keys(obj: Any, sensitive: list[str] | None = None) -> Any:
    """递归脱敏 dict / list 中「键名命中敏感清单」的值。

    - 命中键名 -> 用 :func:`mask_secret` 对**值**打码（无论值是标量、dict 还是 list）。
    - 未命中键名 -> 递归进其 dict / list 结构继续扫描。
    - 返回**新结构**（不修改入参），便于调用方按需替换。

    `sensitive` 缺省用 :data:`DEFAULT_SENSITIVE_KEYS`；传入则覆盖默认清单。
    """
    sens = [s.lower() for s in (sensitive if sensitive is not None else DEFAULT_SENSITIVE_KEYS)]
    return _redact_value(obj, sens)


def _redact_value(obj: Any, sensitive: list[str]) -> Any:
    if isinstance(obj, dict):
        return {
            key: (mask_secret(val) if _is_sensitive(key, sensitive) else _redact_value(val, sensitive))
            for key, val in obj.items()
        }
    if isinstance(obj, list):
        return [_redact_value(val, sensitive) for val in obj]
    return obj


def should_redact() -> bool:
    """读取脱敏开关环境变量 :data:`REDACT_ENV`，默认 ``"0"``（关闭）。

    默认关闭的理由：本地优先 + 全合成测试数据（无真实个人信息），脱敏无收益且会
    降低复盘/联调可读性。接入真实培训数据前必须置该变量为 ``1``（同时建议最小化采集）。

    兼容取值：``1/true/yes/on``（大小写不敏感、允许首尾空白）视为开启；其余视为关闭。
    """
    val = os.environ.get(REDACT_ENV, "0")
    return val.strip().lower() in ("1", "true", "yes", "on")
