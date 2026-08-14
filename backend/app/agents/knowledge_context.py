"""
领域知识上下文构建 -- Agent 共享工具

code_reviewer / code_tester 均需将知识图谱节点 (key_points/common_mistakes)
组织成 LLM 上下文字符串，统一在此避免重复。
"""

import json


def build_knowledge_context(
    knowledge_nodes: list[dict],
    *,
    include_key_points: bool = True,
    empty_hint: str = "(未检索到相关领域知识点)",
) -> str:
    """把领域知识点组织成 LLM 上下文。

    Args:
        knowledge_nodes: 图谱节点列表 (含 node_id/name/key_points/common_mistakes)
        include_key_points: 是否输出 key_points (code_reviewer 需要, code_tester 不需要)
        empty_hint: 节点为空时的提示文本
    """
    if not knowledge_nodes:
        return empty_hint
    lines = []
    for n in knowledge_nodes:
        nid = n.get("node_id") or n.get("id", "")
        name = n.get("name", "")
        lines.append(f"- [{nid}] {name}")
        if include_key_points:
            kps = n.get("key_points", [])
            if kps:
                lines.append(f"  key_points: {json.dumps(kps, ensure_ascii=False)}")
        mistakes = n.get("common_mistakes", [])
        if mistakes:
            lines.append(f"  common_mistakes: {json.dumps(mistakes, ensure_ascii=False)}")
    return "\n".join(lines)
