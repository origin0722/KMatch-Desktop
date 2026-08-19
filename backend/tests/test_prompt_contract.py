"""提示词-代码 契约漂移测试 (Q2-A)

目的: 把散落在 data/prompts 与代码两处的关键协约**钉死**, 防止其一被改而另一处
悄悄漂移。断言为子串/常量级(稳), 不依赖提示词措辞细节。

钉死的契约:
  1. orchestrator: 打回最多 3 轮 & LLM 超时重试 2 次 & 反馈规则分档 (>=0.8/0.5) —— 与 decide_feedback 一致
  2. 内容/代码审核阈值 0.85 —— 与 settings.REVIEW_PASS_THRESHOLD 一致
  3. code_safety 高危清单 (eval/exec/os.system/pickle) —— 与 07 prompt 一票否决一致
  4. 04 幻觉治理条款存在 (高保真/先锚定后展开/unverified_claims/心算自检)
  5. 动态建域: 10 节点 / 不纳入 M5 —— 与 08 prompt 一致
  6. 结构化事件 Agent 词汇与 log_events.AGENT_KEYS 一致
"""

from pathlib import Path

from app.agents import log_events
from app.config import settings

PROMPTS = Path(__file__).resolve().parents[2] / "data" / "prompts"


def _read(name: str) -> str:
    p = PROMPTS / name
    assert p.is_file(), f"缺提示词文件: {p}"
    return p.read_text(encoding="utf-8")


def test_orchestrator_retry_and_feedback_rules():
    t = _read("01_orchestrator_agent.txt")
    assert "最大重试: 3轮" in t or "最大重试: 3 轮" in t
    assert "最多重试 2 次" in t
    assert "80%" in t and "50%" in t
    # 与 decide_feedback 执行侧一致 (分档语义)
    from app.agents.diagnostics import decide_feedback
    assert decide_feedback(9, 10)["strategy"] == "advance"    # 0.9 ≥0.8
    assert decide_feedback(6, 10)["strategy"] == "remediate"  # 0.6
    assert decide_feedback(2, 10)["strategy"] == "scaffold"   # 0.2


def test_review_threshold_085_locked():
    assert settings.REVIEW_PASS_THRESHOLD == 0.85
    assert "0.85" in _read("05_content_reviewer_agent.txt")
    assert "0.85" in _read("07_code_reviewer_agent.txt")


def test_code_safety_hard_rules_lock_sync():
    from app.agents.code_safety import hard_check_code_safety
    for code in ["x = eval('1')", "exec('1')", "import os\nos.system('ls')", "import pickle\npickle.loads(b'x')"]:
        issues = hard_check_code_safety(code)
        assert issues, f"高危清单漏检: {code!r}"
        assert any(i.get("dimension") == "security" for i in issues)
    t = _read("07_code_reviewer_agent.txt")
    assert "eval" in t and "os.system" in t and "pickle" in t
    assert "一票否决" in t


def test_hallucination_governance_terms_present():
    t = _read("04_content_generator_agent.txt")
    assert "严禁" in t and "高保真" in t
    assert "先锚定" in t or "锚定" in t
    assert "unverified_claims" in t
    assert "心算" in t


def test_domain_bootstrap_contract():
    t = _read("08_domain_bootstrap_agent.txt")
    assert "10 节点" in t or "恰好 10 节点" in t
    assert "不纳入 M5" in t


def test_event_vocabulary_matches_log_events():
    assert set(log_events.AGENT_KEYS) == {
        "orchestrator", "diagnostics", "reviewer", "graph_controller", "content_generator",
    }


def test_shared_contracts_page_pinned():
    """00_shared_contracts.md 共享契约页必须存在且与代码常量一致。"""
    t = _read("00_shared_contracts.md")
    assert "0.85" in t
    assert "REVIEW_PASS_THRESHOLD" in t
    assert settings.REVIEW_PASS_THRESHOLD == 0.85
    assert "max_retries" in t                    # 打回最大轮数
    assert "agent-start" in t and "agent-end" in t and "degraded" in t  # 事件词汇
    assert "advance" in t and "remediate" in t and "scaffold" in t      # 反馈分档


def test_agent_prompts_reference_shared_contracts():
    """01-08 主链提示词头部都引用共享契约页 (单一来源防漂移)。"""
    for name in ("01_orchestrator_agent.txt", "02_diagnostics_agent.txt", "03_graph_controller_agent.txt",
                 "04_content_generator_agent.txt", "05_content_reviewer_agent.txt", "06_code_tester_agent.txt",
                 "07_code_reviewer_agent.txt", "08_domain_bootstrap_agent.txt"):
        assert "00_shared_contracts" in _read(name), f"{name} 缺共享契约页引用"


def test_graph_controller_embedding_degradation_clause():
    """⑦: 03 提示词须显式声明无 embedding 时语义检索降级为仅图遍历。"""
    t = _read("03_graph_controller_agent.txt")
    assert "降级" in t
    assert "semantic_search" in t and "hybrid_retrieve" in t
    assert "图遍历" in t
