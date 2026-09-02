"""节点级再生缓存单测 (v1.3.3 提速) — 打回时只重生成被审核点名的节点。

验证 (_node_body 的 regen_nodes 过滤):
  - 审核点名 PY-002 (issues[].source_node) → 只重生成 PY-002, PY-001 沿用既有资源
  - 此前生成失败的节点 (无既有资源) 即使未被点名也重生成
  - 审核未点名任何节点 (issues 缺 source_node) → 保守全量再生 (行为与旧版一致)
"""

from unittest.mock import MagicMock

from app.agents import content_generator as cg


def _make_node_fn(monkeypatch, calls):
    monkeypatch.setattr(cg, "llm_configured", lambda: True)

    def _fake_generate_one(node, theory_level, ctype, retry_hint, style_extra, **kw):
        calls.append((node["node_id"], ctype))
        return {"content": f"# 新内容 {node['node_id']} {ctype}",
                "content_type": ctype, "target_node_id": node["node_id"]}
    monkeypatch.setattr(cg, "_generate_one", _fake_generate_one)
    return cg.content_generator_node(MagicMock())


def _state(existing_ids, flagged_nodes, hint=True):
    """existing_ids: 已有资源的 node_id 列表; flagged_nodes: 审核点名的 source_node 列表。

    review_results 用 reviewer 真实产出形状: issues 在 dimensions.<dim>.issues (两层深)。
    """
    issues = [{"severity": "high", "problem": "幻觉", "source_node": nid} for nid in flagged_nodes]
    return {
        "user_profile": {"theory_level": 2},
        "knowledge_graph": {"learning_path": [
            {"node_id": "PY-001", "name": "节点1", "difficulty": 2},
            {"node_id": "PY-002", "name": "节点2", "difficulty": 2},
        ]},
        "content_phase_entered": hint,
        "retry_count": 1,
        "review_results": {
            "retry_hint": "修正幻觉" if hint else "",
            "dimensions": {"factual_accuracy": {"score": 0.5, "issues": issues}},
        },
        "generated_content": {
            "resources": [
                {"target_node_id": nid, "content_type": ct, "content": f"# 旧 {nid} {ct}"}
                for nid in existing_ids for ct in cg.CONTENT_TYPES
            ],
            "node_count": 2,
        },
        "orchestration_log": [],
    }


def test_regen_only_flagged_nodes(monkeypatch):
    """点名 PY-002 → PY-002 重生成 3 段, PY-001 沿用 3 段既有资源。"""
    calls = []
    node_fn = _make_node_fn(monkeypatch, calls)
    delta = node_fn(_state(existing_ids=["PY-001", "PY-002"], flagged_nodes=["PY-002"]))

    gen = delta["generated_content"]
    assert {r["target_node_id"] for r in gen["resources"]} == {"PY-001", "PY-002"}
    assert len(gen["resources"]) == 6
    # PY-001 的资源是旧内容 (沿用), PY-002 是新内容 (重生成)
    old = next(r for r in gen["resources"] if r["target_node_id"] == "PY-001")
    assert old["content"].startswith("# 旧")
    # 仅 PY-002 的 3 种类型被重新生成
    assert set(calls) == {("PY-002", ct) for ct in cg.CONTENT_TYPES}
    assert any("沿用" in line for line in delta["orchestration_log"])


def test_regen_failed_node_even_unflagged(monkeypatch):
    """PY-001 此前生成失败 (无资源) → 即使未点名也重生成。"""
    calls = []
    node_fn = _make_node_fn(monkeypatch, calls)
    delta = node_fn(_state(existing_ids=["PY-002"], flagged_nodes=["PY-002"]))

    assert ("PY-001", "lecture") in calls  # 补齐此前失败的节点
    assert len(delta["generated_content"]["resources"]) == 6


def test_no_flagged_nodes_falls_back_to_full_regen(monkeypatch):
    """issues 无 source_node (点名信息缺失) → 保守全量再生 (行为不变)。"""
    calls = []
    node_fn = _make_node_fn(monkeypatch, calls)
    delta = node_fn(_state(existing_ids=["PY-001", "PY-002"], flagged_nodes=[]))

    total = 2 * len(cg.CONTENT_TYPES)
    assert len(calls) == total
    assert len(delta["generated_content"]["resources"]) == total


def test_first_round_full_regen(monkeypatch):
    """首轮 (content_phase_entered=False, 无既有资源) → 全量, 与旧版一致。"""
    calls = []
    node_fn = _make_node_fn(monkeypatch, calls)
    state = _state(existing_ids=[], flagged_nodes=[], hint=False)
    state["generated_content"] = {}
    state["review_results"] = {}
    delta = node_fn(state)

    assert len(calls) == 2 * len(cg.CONTENT_TYPES)
    assert delta["content_phase_entered"] is True


def test_flagged_extraction_supports_legacy_top_level_issues(monkeypatch):
    """兼容顶层 issues 形状 (防御: 与 reviewer 内部单测等旧形状共存)。"""
    calls = []
    node_fn = _make_node_fn(monkeypatch, calls)
    state = _state(existing_ids=["PY-001", "PY-002"], flagged_nodes=["PY-001"])
    # 用顶层 issues 替换 dimensions 形状
    state["review_results"] = {
        "retry_hint": "修正幻觉",
        "issues": [{"severity": "high", "problem": "幻觉", "source_node": "PY-001"}],
    }
    delta = node_fn(state)
    assert ("PY-001", "lecture") in calls and ("PY-002", "lecture") not in calls


def test_flagged_no_intersection_falls_back_to_full_regen(monkeypatch):
    """LLM source_node 自由文本 (与路径节点零交集) → 保守全量再生 (防空转沿用问题内容)。"""
    calls = []
    node_fn = _make_node_fn(monkeypatch, calls)
    state = _state(existing_ids=["PY-001", "PY-002"], flagged_nodes=["resources[2]"])
    delta = node_fn(state)

    total = 2 * len(cg.CONTENT_TYPES)
    assert len(calls) == total  # 全量再生
    assert len(delta["generated_content"]["resources"]) == total
