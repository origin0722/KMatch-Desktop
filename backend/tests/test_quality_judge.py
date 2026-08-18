"""独立裁判 (quality_judge) 单测 — LLM-as-Judge 幻觉/难度判定。

用假 judge LLM (invoke 返回固定 JSON), 免真实 API。覆盖:
  - judge_hallucination: 判定计数/幻觉率/降级/unverifiable 处理/kg 事实收集
  - judge_adaptation: 难度比对 (|gap|<=1)/判定失败不计匹配
  - get_judge_llm: JUDGE_LLM_* 独立源 vs 同源降级
"""

import json
from types import SimpleNamespace

from app.agents import quality_judge as qj


class _FakeJudge:
    """假裁判 LLM: 按调用顺序返回预设 JSON (content 字符串)。"""

    def __init__(self, results):
        self._results = list(results)
        self.calls = []

    def invoke(self, prompt):
        self.calls.append(prompt)
        return SimpleNamespace(content=self._results[len(self.calls) - 1])


def _res(content="内容", node="PY-001", ctype="讲义", sources=None):
    return {"content": content, "target_node_id": node, "content_type": ctype, "source_nodes": sources or []}


# ============================================================
# judge_hallucination
# ============================================================

def test_hallucination_all_grounded_rate_zero():
    """全部 grounded → 幻觉率 0。"""
    judge = _FakeJudge([
        json.dumps({"verdict": "grounded", "reason": "与节点一致"}, ensure_ascii=False),
        json.dumps({"verdict": "grounded", "reason": "与节点一致"}, ensure_ascii=False),
    ])
    result = qj.judge_hallucination([_res("a"), _res("b")], judge_llm=judge)
    assert result["rate"] == 0.0
    assert result["grounded"] == 2
    assert result["hallucinated"] == 0
    assert result["same_source"] is False  # 显式传入 judge_llm → 非同源

def test_hallucination_detects_halucinated():
    """检出 1 条幻觉 → rate = 1/3。"""
    judge = _FakeJudge([
        json.dumps({"verdict": "grounded", "reason": "ok"}, ensure_ascii=False),
        json.dumps({"verdict": "hallucinated", "reason": "编造了图谱外事实"}, ensure_ascii=False),
        json.dumps({"verdict": "grounded", "reason": "ok"}, ensure_ascii=False),
    ])
    result = qj.judge_hallucination([_res("a"), _res("b"), _res("c")], judge_llm=judge)
    assert result["rate"] == round(1 / 3, 3)
    assert result["hallucinated"] == 1
    assert result["verdicts"][1]["verdict"] == "hallucinated"
    assert "编造" in result["verdicts"][1]["reason"]

def test_hallucination_unverifiable_not_counted_in_rate():
    """unverifiable 不计入幻觉率, 单独报告。"""
    judge = _FakeJudge([
        json.dumps({"verdict": "unverifiable", "reason": "事实不足"}, ensure_ascii=False),
        json.dumps({"verdict": "grounded", "reason": "ok"}, ensure_ascii=False),
    ])
    result = qj.judge_hallucination([_res("a"), _res("b")], judge_llm=judge)
    assert result["rate"] == 0.0
    assert result["unverifiable"] == 1
    assert result["hallucinated"] == 0

def test_hallucination_llm_error_falls_to_unverifiable():
    """LLM 抛异常 → 该条计 unverifiable, 批量不中断。"""
    class _Boom:
        def invoke(self, prompt):
            raise RuntimeError("judge down")

    result = qj.judge_hallucination([_res("a"), _res("b")], judge_llm=_Boom())
    assert result["total"] == 2
    assert result["unverifiable"] == 2
    assert result["rate"] == 0.0

def test_hallucination_front_empty_content_keeps_original_index():
    """issue-04: 前位 content="" 资源被跳过但不下标左移。

    旧实现先过滤再 enumerate → resource_index 是过滤后下标, 与 quality_regen 的原始列表
    out 索引不一致 (定向再生改错资源)。修复后仅跳过空内容资源, 下标保持原始列表坐标。
    """
    judge = _FakeJudge([
        json.dumps({"verdict": "hallucinated", "reason": "编造了图谱外事实"}, ensure_ascii=False),
        json.dumps({"verdict": "grounded", "reason": "ok"}, ensure_ascii=False),
    ])
    resources = [
        {"content": "", "target_node_id": "PY-001", "content_type": "讲义"},  # 空内容 → 跳过, 不产出 verdict
        _res("b", node="PY-002"),
        _res("c", node="PY-003"),
    ]
    result = qj.judge_hallucination(resources, judge_llm=judge)
    assert result["total"] == 2
    assert result["hallucinated"] == 1
    assert [v["resource_index"] for v in result["verdicts"]] == [1, 2]  # 原始坐标
    assert result["verdicts"][0]["verdict"] == "hallucinated"

def test_hallucination_invalid_verdict_falls_to_unverifiable():
    """裁判输出非法 verdict → 保守计 unverifiable。"""
    judge = _FakeJudge(['{"verdict": "maybe", "reason": "x"}'])
    result = qj.judge_hallucination([_res("a")], judge_llm=judge)
    assert result["unverifiable"] == 1

def test_hallucination_prompt_includes_node_facts():
    """有 kg 时 prompt 含节点 summary/key_points 事实。"""
    class _FakeKg:
        def get_node(self, node_id):
            return {"summary": "变量", "key_points": ["kp1", "kp2"]}

    judge = _FakeJudge([json.dumps({"verdict": "grounded", "reason": "ok"}, ensure_ascii=False)])
    qj.judge_hallucination([_res("a")], kg=_FakeKg(), judge_llm=judge)
    prompt = judge.calls[0]
    assert "[PY-001.summary] 变量" in prompt
    assert "[PY-001.key_points[0]] kp1" in prompt

def test_hallucination_kg_none_uses_references_only():
    """kg 为 None → prompt 标注图谱事实缺失, 仅引用。"""
    judge = _FakeJudge([json.dumps({"verdict": "unverifiable", "reason": "缺事实"}, ensure_ascii=False)])
    qj.judge_hallucination([_res("a")], kg=None, judge_llm=judge)
    assert "图谱事实缺失" in judge.calls[0]

def test_hallucination_prompt_includes_unverified_claims():
    """资源带 unverified_claims 自声明 → prompt 追加"资源自声明待验证补充"块 (优先核验)。
    无声明 / 非 list → 不追加。"""
    judge = _FakeJudge([
        json.dumps({"verdict": "grounded", "reason": "ok"}, ensure_ascii=False),
        json.dumps({"verdict": "grounded", "reason": "ok"}, ensure_ascii=False),
        json.dumps({"verdict": "grounded", "reason": "ok"}, ensure_ascii=False),
    ])
    with_claims = {**_res("a"), "unverified_claims": ["变量像盒子的类比"]}
    none_claims = _res("b")
    bad_claims = {**_res("c"), "unverified_claims": "不是数组"}

    qj.judge_hallucination([with_claims, none_claims, bad_claims], judge_llm=judge)

    assert "资源自声明待验证补充" in judge.calls[0]
    assert "变量像盒子的类比" in judge.calls[0]
    assert "资源自声明待验证补充" not in judge.calls[1]
    assert "资源自声明待验证补充" not in judge.calls[2]

def test_hallucination_empty_resources():
    """空资源 → total 0, rate 0。"""
    result = qj.judge_hallucination([], judge_llm=_FakeJudge([]))
    assert result["total"] == 0
    assert result["rate"] == 0.0

def test_hallucination_verdict_records_evidence_and_coverage():
    """阶段四: verdict 读入 evidence_node_ids + coverage (验证依据+锚定覆盖双记录)。
    非法 coverage 兜底 none; 缺失 evidence 兜底空列表。"""
    judge = _FakeJudge([
        json.dumps({"verdict": "grounded", "evidence_node_ids": ["PY-001", "PY-002"],
                    "coverage": "full", "reason": "ok"}, ensure_ascii=False),
        json.dumps({"verdict": "grounded", "coverage": "非法值", "reason": "ok"}, ensure_ascii=False),
        json.dumps({"verdict": "grounded", "coverage": "partial", "reason": "ok"}, ensure_ascii=False),
    ])
    result = qj.judge_hallucination([_res("a"), _res("b"), _res("c")], judge_llm=judge)

    assert result["verdicts"][0]["evidence_node_ids"] == ["PY-001", "PY-002"]
    assert result["verdicts"][0]["coverage"] == "full"
    # 非法 coverage → none; 缺失 evidence → []
    assert result["verdicts"][1]["coverage"] == "none"
    assert result["verdicts"][1]["evidence_node_ids"] == []
    assert result["verdicts"][2]["coverage"] == "partial"


# ============================================================
# judge_adaptation
# ============================================================

def test_adaptation_all_matched():
    """裁判难度与画像水平一致 → 适配率 100%。"""
    judge = _FakeJudge([
        json.dumps({"difficulty": 2, "reason": "基础"}, ensure_ascii=False),
        json.dumps({"difficulty": 1, "reason": "入门"}, ensure_ascii=False),
    ])
    result = qj.judge_adaptation([_res("a"), _res("b")], {"theory_level": 2}, judge_llm=judge)
    assert result["rate"] == 1.0
    assert result["matched"] == 2
    assert all(j["matched"] for j in result["judged"])

def test_adaptation_partial_match():
    """理论水平 1, 难度 3 资源 → 不匹配。"""
    judge = _FakeJudge([
        json.dumps({"difficulty": 1, "reason": "入门"}, ensure_ascii=False),
        json.dumps({"difficulty": 3, "reason": "进阶"}, ensure_ascii=False),
    ])
    result = qj.judge_adaptation([_res("a"), _res("b")], {"theory_level": 1}, judge_llm=judge)
    assert result["matched"] == 1
    assert result["rate"] == 0.5

def test_adaptation_judge_failure_not_matched():
    """判定失败 (difficulty 缺失) → 不计匹配, 不中断。"""
    judge = _FakeJudge([
        json.dumps({"reason": "无法评"}, ensure_ascii=False),
        json.dumps({"difficulty": 2, "reason": "ok"}, ensure_ascii=False),
    ])
    result = qj.judge_adaptation([_res("a"), _res("b")], {"theory_level": 2}, judge_llm=judge)
    assert result["judged"][0]["difficulty"] is None
    assert result["matched"] == 1

def test_adaptation_empty_resources():
    """空资源 → rate 0。"""
    result = qj.judge_adaptation([], {"theory_level": 2}, judge_llm=_FakeJudge([]))
    assert result["total"] == 0
    assert result["rate"] == 0.0


# ============================================================
# get_judge_llm
# ============================================================

def test_get_judge_llm_independent_source(monkeypatch):
    """JUDGE_LLM_API_KEY 配置 → 独立源 (same_source=False)。"""
    monkeypatch.setattr(qj.settings, "JUDGE_LLM_API_KEY", "sk-judge")
    judge, same = qj.get_judge_llm()
    assert same is False
    assert judge is not None

def test_get_judge_llm_fallback_same_source(monkeypatch):
    """JUDGE_LLM_* 未配置 → 回退主 LLM (same_source=True)。"""
    monkeypatch.setattr(qj.settings, "JUDGE_LLM_API_KEY", "")
    judge, same = qj.get_judge_llm()
    assert same is True
    assert judge is not None
