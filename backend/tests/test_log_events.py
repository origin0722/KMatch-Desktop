"""to_log_event 结构化事件分类单测 (Phase 0)。

覆盖: agent 解析优先级、终态/进行中识别、消息清洗、原始行保留。
"""

from app.agents.log_events import to_log_event


def test_diagnostics_start():
    ev = to_log_event("[2026-06-20T10:00:00] 🔧 学情检测: 开始 (mode=demo)")
    assert ev["type"] == "agent-start"
    assert ev["agent"] == "diagnostics"
    assert ev["status"] == "running"
    assert ev["message"] == "学情检测: 开始 (mode=demo)"
    assert "学情检测: 开始" in ev["log"]


def test_diagnostics_grading():
    ev = to_log_event("[ts] 🔧 学情检测: 判分 7/10")
    assert ev["agent"] == "diagnostics"
    assert ev["status"] == "running"  # 判分视为进行中节点产出
    assert "判分 7/10" in ev["message"]


def test_content_generator_start():
    ev = to_log_event("[ts] 📚 领域知识生成: 开始")
    assert ev["agent"] == "content_generator"
    assert ev["status"] == "running"
    assert ev["type"] == "agent-start"


def test_graph_controller_assembly():
    ev = to_log_event("[ts] 🗺️ 知识图谱管控: 开始组装学习路径")
    assert ev["agent"] == "graph_controller"
    assert ev["type"] == "agent-start"


def test_reviewer_pass():
    ev = to_log_event("[ts] ✅ 内容审核通过: 评分 0.92")
    assert ev["agent"] == "reviewer"
    assert ev["type"] == "agent-end"
    assert ev["status"] == "done"


def test_reviewer_fail():
    ev = to_log_event("[ts] ❌ 内容审核不通过: 溯源不足")
    assert ev["agent"] == "reviewer"
    assert ev["type"] == "error"
    assert ev["status"] == "failed"


def test_reviewer_line_containing_diagnostics_keyword_goes_to_reviewer():
    # 关键歧义用例: reviewer 文案含「学情检测」，必须归 reviewer
    ev = to_log_event("📊 画像模式: 审核学情检测产出的用户画像")
    assert ev["agent"] == "reviewer"


def test_run_end_normal():
    ev = to_log_event("[ts] ✅ 流程结束")
    assert ev["type"] == "run-end"
    assert ev["agent"] == "orchestrator"
    assert ev["status"] == "done"


def test_run_end_degraded():
    ev = to_log_event("[ts] ⚠️ 流程结束 (超过最大重试 3 轮，降级为待人工审核)")
    assert ev["type"] == "run-end"
    assert ev["status"] == "degraded"


def test_warning_info():
    ev = to_log_event("[ts] ⚠️ LLM 未配置，学情检测降级为空画像")
    assert ev["type"] == "info"
    assert ev["status"] == "degraded"
    assert "LLM 未配置" in ev["message"]


def test_unknown_line_falls_back_to_info():
    ev = to_log_event("[ts] 某些无关日志")
    assert ev["type"] == "info"
    assert ev["agent"] is None
    assert ev["status"] == "idle"


def test_empty_line():
    ev = to_log_event("")
    assert ev["type"] == "info"
    assert ev["log"] == ""


def test_message_strips_timestamp_and_emoji_only():
    ev = to_log_event("[2026-06-20T10:00:00.000Z] 🚀 主控调度: 编排开始")
    assert ev["message"] == "主控调度: 编排开始"
    assert "🚀" not in ev["message"]
