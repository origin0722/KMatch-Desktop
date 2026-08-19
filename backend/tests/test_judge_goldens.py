"""裁判 golden 回归集 (⑥) — 离线可跑、不依赖真实 LLM。

两层保障:
  1) 数据集合法性 + 用"假裁判"驱动 judge_hallucination/judge_adaptation 全量案例,
     验证 harness(事实拼装/JSON 解析/coverage 归一/计数/非法值兜底) 对每类错误族输出正确;
  2) 钉裁判提示词的**判定条款** (如 图谱没写≠幻觉 / 与图谱相悖→hallucinated / unverifiable 语义),
     防"改了提示词就偷偷改判"→ wording 漂移被捕获。

真裁判 live 全量回归: python backend/scripts/run_judge_golden.py (配置 key 时)。
"""

import json
from pathlib import Path

import pytest

from app.agents.quality_judge import (
    _build_difficulty_prompt,
    _build_hallucination_prompt,
    judge_adaptation,
    judge_hallucination,
)

FIXTURE = Path(__file__).parent / "fixtures" / "judge_goldens.json"
GOLD = json.loads(FIXTURE.read_text(encoding="utf-8"))


class FakeKG:
    """dict 化图谱: get_node(node_id) → {summary, key_points} 或 None。"""

    def __init__(self, nodes: dict):
        self.nodes = nodes

    def get_node(self, node_id):
        return self.nodes.get(node_id)


class FakeJudge:
    """假裁判: invoke 返回 Golden 期望的 JSON 字符串 (模拟真实 LLM 回包)。"""

    def __init__(self, payload: dict):
        self.payload = payload

    def invoke(self, prompt):
        return type("R", (), {"content": json.dumps(self.payload, ensure_ascii=False)})()


def _fake_judge_for(case: dict, kind: str):
    if kind == "hallucination":
        return FakeJudge({
            "verdict": case["expected_verdict"],
            "evidence_node_ids": [case.get("facts", {}).keys().__iter__().__next__()
                                  if case.get("facts") else "RA-001"],
            "coverage": case["expected_coverage"],
            "reason": "golden",
        })
    return FakeJudge({
        "difficulty": case["expected_difficulty"],
        "reason": "golden",
    })


def test_golden_dataset_valid():
    for case in GOLD["hallucination"]:
        assert case.get("id") and case.get("content")
        assert case["expected_verdict"] in {"grounded", "hallucinated", "unverifiable"}
        assert case["expected_coverage"] in {"full", "partial", "none"}
    for case in GOLD["difficulty"]:
        assert case.get("id") and case.get("content")
        assert 1 <= int(case["theory_level"]) <= 5
        assert isinstance(case["expected_difficulty"], int) or case["expected_difficulty"] == "oops"


@pytest.mark.parametrize("case", GOLD["hallucination"], ids=lambda c: c["id"])
def test_hallucination_golden(case):
    kg = FakeKG(case["facts"])
    resource = {
        "content": case["content"],
        "target_node_id": next(iter(case["facts"]), ""),
        "source_nodes": list(case["facts"]),
        "content_type": "lecture",
    }
    out = judge_hallucination([resource], kg, _fake_judge_for(case, "hallucination"))
    assert out["total"] == 1
    v = out["verdicts"][0]
    assert v["verdict"] == case["expected_verdict"], case["id"]
    assert v["coverage"] == case["expected_coverage"], case["id"]
    # rate: 只有 hallucinated 计幻觉
    expect_rate = 1.0 if case["expected_verdict"] == "hallucinated" else 0.0
    assert out["rate"] == expect_rate


def test_hallucination_aggregate_counts():
    """一次调用多资源 → 计数/rate 正确 (与 run_quality_test 同口径)。"""
    class FakeJudgeSeq:
        def __init__(self, payloads):
            self.payloads = list(payloads)
            self.i = 0
        def invoke(self, _prompt):
            p = self.payloads[self.i % len(self.payloads)]
            self.i += 1
            return type("R", (), {"content": json.dumps(p, ensure_ascii=False)})()

    resources = [
        {"content": "a", "target_node_id": "X", "source_nodes": ["X"]},
        {"content": "b", "target_node_id": "Y", "source_nodes": ["Y"]},
        {"content": "c", "target_node_id": "Z", "source_nodes": ["Z"]},
    ]
    out = judge_hallucination(resources, kg=None, judge_llm=FakeJudgeSeq([
        {"verdict": "grounded", "coverage": "full", "reason": "g"},
        {"verdict": "hallucinated", "coverage": "none", "reason": "h"},
        {"verdict": "unverifiable", "coverage": "none", "reason": "u"},
    ]))
    assert (out["grounded"], out["hallucinated"], out["unverifiable"]) == (1, 1, 1)
    assert out["total"] == 3
    assert out["rate"] == round(1 / 3, 3)


def test_difficulty_golden():
    for case in GOLD["difficulty"]:
        resource = {"content": case["content"], "content_type": "lecture"}
        out = judge_adaptation([resource], {"theory_level": case["theory_level"]},
                               _fake_judge_for(case, "difficulty"))
        j = out["judged"][0]
        assert j["matched"] == case["expected_matched"], case["id"]
        if case["expected_difficulty"] == "oops":
            assert j["difficulty"] is None  # 非法值 → 判定失败 (非崩溃)
        else:
            assert j["difficulty"] == case["expected_difficulty"]


def test_judge_prompt_discriminating_clauses_pinned():
    """钉提示词判定条款: 改动判据措辞 → 本测试红 (wording 漂移防护)。"""
    hp = _build_hallucination_prompt("内容", "图谱事实", unverified=["待验"])
    for phrase in ("grounded", "hallucinated", "unverifiable", "不等于幻觉", "与图谱事实相悖", "编造"):
        assert phrase in hp, f"幻觉判据缺少关键短语: {phrase}"
    dp = _build_difficulty_prompt("内容")
    assert "1" in dp and "5" in dp  # 难度标尺锚点
