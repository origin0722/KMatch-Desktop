"""
LLM JSON 响应解析工具

从 LLM 响应中稳健提取 JSON，处理 markdown 代码块、多对象拼接、
尾部多余文本等常见格式问题。所有 Agent 节点共用。
"""

import json


def parse_llm_json(text: str):
    """从 LLM 响应中稳健提取首个完整 JSON 对象或数组。

    处理场景：
      - markdown 代码块包裹 (```json ... ```)
      - 多对象拼接 ({"a":1}{"b":2})
      - 尾部多余文本
      - 嵌套花括号/方括号（raw_decode 自动匹配括号层级）
      - 完全非法文本 — 返回 {}，不抛异常

    Returns:
        dict | list | 解析失败时返回 {}
    """
    text = text.strip()

    # 处理 markdown 代码块
    if text.startswith("```"):
        parts = text.split("```", 2)
        if len(parts) >= 2:
            text = parts[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

    # 从最早出现的 { 或 [ 开始解析（确保从最外层 JSON 值开始）
    # raw_decode 按括号层级匹配，不会在嵌套结构中间截断
    candidates = []  # [(position, start_char), ...]
    for ch in ("{", "["):
        idx = text.find(ch)
        if idx != -1:
            candidates.append((idx, ch))

    decoder = json.JSONDecoder()
    for idx, _ch in sorted(candidates):  # 按位置升序，最外层优先
        try:
            obj, _end = decoder.raw_decode(text[idx:])
            return obj
        except json.JSONDecodeError:
            continue  # 尝试下一个位置

    # 兜底：直接解析全文（加保护，失败返回 {}）
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}
