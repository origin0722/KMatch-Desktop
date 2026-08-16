"""幻觉定向再生 (quality_regen) 单测 — mock _generate_one, 免真实 LLM/Neo4j。

覆盖:
  - 只替换 flagged(hallucinated) 资源, 其余原样保留 (顺序不变)
  - 裁判 reason 作为 correction_hint 透传给 _generate_one
  - adaptation_profile 反映射 theory_level (beginner→2/intermediate→3/advanced→5)
  - 节点缺失 → 保留原资源, 计入 failures
  - 无幻觉 / 空 verdicts → no-op
  - LLM 失败 (safe_llm_call 捕获) → 保留原资源
"""

import pytest

from app.agents import quality_regen


def _resource(idx, node_id="PY-001", ctype="lecture", profile="beginner"):
    return {
        "content_type": ctype,
        "target_node_id": node_id,
        "adaptation_profile": profile,
        "source_nodes": [f"{node_id}.summary"],
        "content": f"原始内容 {idx}",
    }


def _halluc_result(verdicts):
    counts = {"grounded": 0, "hallucinated": 0, "unverifiable": 0}
    for v in verdicts:
        counts[v["verdict"]] += 1
    return {
        "rate": round(counts["hallucinated"] / len(verdicts), 3) if verdicts else 0.0,
        "total": len(verdicts),
        **counts,
        "verdicts": verdicts,
    }


class _FakeKG:
    def __init__(self, nodes):
        self._nodes = nodes  # {node_id: node dict}

    def get_node(self, node_id):
        return self._nodes.get(node_id)


def _node(node_id="PY-001"):
    return {"node_id": node_id, "name": "变量", "difficulty": 1,
            "summary": "s", "key_points": ["k1"], "common_mistakes": []}


def test_replaces_only_flagged(monkeypatch):
    captured = []

    def fake_generate(node, level, ctype, correction_hint=""):
        captured.append((node["node_id"], level, ctype, correction_hint))
        return {**_resource(99, node_id=node.get("node_id", "PY-001"), ctype=ctype),
                "content": f"再生内容 node={node['node_id']} hint={correction_hint}"}

    monkeypatch.setattr(quality_regen, "_generate_one", fake_generate)
    resources = [_resource(0), _resource(1), _resource(2)]
    halluc = _halluc_result([
        {"resource_index": 0, "verdict": "grounded", "reason": ""},
        {"resource_index": 1, "verdict": "hallucinated", "reason": "API 行为描述错误",
         "content_type": "lecture", "target_node_id": "PY-001"},
        {"resource_index": 2, "verdict": "unverifiable", "reason": ""},
    ])
    result = quality_regen.regenerate_flagged(resources, halluc, _FakeKG({"PY-001": _node()}))

    assert result["regenerated_count"] == 1
    assert result["regen_indexes"] == [1]
    assert result["resources"][0]["content"] == "原始内容 0"   # 未标记 → 原样
    assert result["resources"][2]["content"] == "原始内容 2"   # unverifiable → 不再生
    assert "再生内容" in result["resources"][1]["content"]
    # reason 透传
    assert captured[0][3] == "API 行为描述错误"


def test_profile_to_level_reverse_map(monkeypatch):
    captured = []

    def fake_generate(node, level, ctype, correction_hint=""):
        captured.append(level)
        return {**_resource(9), "content": "ok"}

    monkeypatch.setattr(quality_regen, "_generate_one", fake_generate)
    resources = [
        {**_resource(0, profile="beginner"), "target_node_id": "PY-001"},
        {**_resource(1, profile="intermediate"), "target_node_id": "PY-002"},
        {**_resource(2, profile="advanced"), "target_node_id": "PY-003"},
    ]
    halluc = _halluc_result([
        {"resource_index": i, "verdict": "hallucinated", "reason": "r",
         "content_type": "lecture", "target_node_id": resources[i]["target_node_id"]}
        for i in range(3)
    ])
    kg = _FakeKG({"PY-001": _node(), "PY-002": _node(), "PY-003": _node()})
    quality_regen.regenerate_flagged(resources, halluc, kg)

    assert captured == [2, 3, 5]


def test_node_missing_keeps_original(monkeypatch):
    def fail_generate(*a, **k):
        raise AssertionError("节点缺失不应调 LLM")

    monkeypatch.setattr(quality_regen, "_generate_one", fail_generate)
    resources = [_resource(0, node_id="PY-404")]
    halluc = _halluc_result([
        {"resource_index": 0, "verdict": "hallucinated", "reason": "r",
         "content_type": "lecture", "target_node_id": "PY-404"},
    ])
    result = quality_regen.regenerate_flagged(resources, halluc, _FakeKG({}))

    assert result["regenerated_count"] == 0
    assert result["failures"] == 1
    assert result["resources"][0]["content"] == "原始内容 0"  # 保留原资源


def test_no_hallucination_noop(monkeypatch):
    called = []
    monkeypatch.setattr(quality_regen, "_generate_one", lambda *a, **k: called.append(1))
    resources = [_resource(0), _resource(1)]
    halluc = _halluc_result([
        {"resource_index": 0, "verdict": "grounded", "reason": ""},
        {"resource_index": 1, "verdict": "unverifiable", "reason": ""},
    ])
    result = quality_regen.regenerate_flagged(resources, halluc, _FakeKG({"PY-001": _node()}))

    assert result["regenerated_count"] == 0
    assert called == []
    assert result["resources"] == resources


def test_llm_failure_keeps_original(monkeypatch):
    def bad_generate(*a, **k):
        raise RuntimeError("LLM 超时")

    monkeypatch.setattr(quality_regen, "_generate_one", bad_generate)
    resources = [_resource(0)]
    halluc = _halluc_result([
        {"resource_index": 0, "verdict": "hallucinated", "reason": "r",
         "content_type": "lecture", "target_node_id": "PY-001"},
    ])
    result = quality_regen.regenerate_flagged(resources, halluc, _FakeKG({"PY-001": _node()}))

    assert result["regenerated_count"] == 0
    assert result["failures"] == 1
    assert result["resources"][0]["content"] == "原始内容 0"


def test_kg_none_all_skipped():
    resources = [_resource(0)]
    halluc = _halluc_result([
        {"resource_index": 0, "verdict": "hallucinated", "reason": "r",
         "content_type": "lecture", "target_node_id": "PY-001"},
    ])
    result = quality_regen.regenerate_flagged(resources, halluc, None)
    assert result["regenerated_count"] == 0
    assert result["failures"] == 1
    assert result["resources"] == resources


def test_empty_resources_and_verdicts():
    assert quality_regen.regenerate_flagged([], _halluc_result([]), _FakeKG({})) == {
        "resources": [], "regenerated_count": 0, "regen_indexes": [], "failures": 0,
    }
    assert quality_regen.regenerate_flagged(None, None, None)["regenerated_count"] == 0


def test_default_hint_when_reason_empty(monkeypatch):
    captured = {}

    def fake_generate(node, level, ctype, correction_hint=""):
        captured["hint"] = correction_hint
        return {**_resource(9), "content": "ok"}

    monkeypatch.setattr(quality_regen, "_generate_one", fake_generate)
    halluc = _halluc_result([
        {"resource_index": 0, "verdict": "hallucinated", "reason": "",
         "content_type": "lecture", "target_node_id": "PY-001"},
    ])
    quality_regen.regenerate_flagged([_resource(0)], halluc, _FakeKG({"PY-001": _node()}))
    assert "严格依据节点事实" in captured["hint"]
