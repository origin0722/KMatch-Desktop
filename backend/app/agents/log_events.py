"""编排日志结构化事件 (Phase 0) — 借鉴 dsh_workflow 的工作流事件契约思想。

把各 Agent 产出的 emoji 文本日志行 (orchestration_log) 规范化为结构化事件:

    {
      "type":    "agent-start" | "agent-end" | "error" | "run-end" | "info",
      "agent":   "orchestrator" | "diagnostics" | "reviewer"
                 | "graph_controller" | "content_generator" | null,
      "status":  "running" | "done" | "failed" | "degraded" | "idle",
      "message": 清洗后的可读文本 (去时间戳/emoji),
      "log":     原始日志行 (供日志流原样渲染)
    }

用途:
  - demo SSE progress 的 log_events (实时)
  - /assess demo 与 /submit 响应的 orchestration_events (终态)
  - 前端 useAgentStatus 改以事件做确定性状态推导 (正则降级兜底)

纯函数、无 IO，便于单测；事件语义与前端 AGENT_DEFS 保持一致。
"""

from __future__ import annotations

import re
from typing import Optional

__all__ = ["to_log_event", "AGENT_KEYS"]

AGENT_KEYS = (
    "orchestrator",
    "diagnostics",
    "reviewer",
    "graph_controller",
    "content_generator",
)

# 关键词 → agent (顺序即优先级判定)。
# 注意 reviewer 优先于 diagnostics：reviewer 的「审核学情检测产出的用户画像」行
# 同时含两个关键词，必须归 reviewer。
_AGENT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("orchestrator", ("流程结束", "主控调度")),
    ("reviewer", ("审核", "画像模式", "画像为空")),
    ("diagnostics", ("学情检测", "判分")),
    ("graph_controller", ("图谱", "路径组装")),
    ("content_generator", ("领域知识生成", "内容生成")),
)


def resolve_agent(line: str) -> Optional[str]:
    """从日志行解析所属 Agent；无法识别返回 None。"""
    for key, keywords in _AGENT_RULES:
        for kw in keywords:
            if kw in line:
                return key
    return None


def _strip_prefix(line: str) -> str:
    """去 [timestamp] 前缀与行首符号/emoji，保留可读中文/字母文本。"""
    rest = re.sub(r"^\[[^\]]*\]\s*", "", line)
    return re.sub(r"^[^\u4e00-\u9fffA-Za-z]+", "", rest).strip()


def to_log_event(line: str) -> dict:
    """把一条编排日志行转换为结构化事件字典（不解析匹配时返回 info）。"""
    line = line or ""
    agent = resolve_agent(line)
    message = _strip_prefix(line)

    # 终态: 流程结束 (降级/正常)
    if "流程结束" in line:
        return {
            "type": "run-end",
            "agent": "orchestrator",
            "status": "degraded" if "⚠️" in line else "done",
            "message": message or "流程结束",
            "log": line,
        }

    # 终态: 显式失败
    if "❌" in line:
        return {
            "type": "error",
            "agent": agent or "orchestrator",
            "status": "failed",
            "message": message or line,
            "log": line,
        }

    # 终态: 通过/完成
    if "✅" in line:
        return {
            "type": "agent-end",
            "agent": agent or "orchestrator",
            "status": "done",
            "message": message or line,
            "log": line,
        }

    # 进行中: 开始/组装/判分等 emoji 起点行
    if any(k in line for k in ("开始", "组装", "判分", "生成")):
        return {
            "type": "agent-start",
            "agent": agent,
            "status": "running",
            "message": message or line,
            "log": line,
        }

    # 其余: 告警/信息 (⚠️ 降级提示保留语义)
    return {
        "type": "info",
        "agent": agent,
        "status": "degraded" if "⚠️" in line else "idle",
        "message": message or line,
        "log": line,
    }
