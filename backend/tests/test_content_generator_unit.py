"""content_generator 单测 — 覆盖纯函数 + 节点逻辑 (fake model/kg，免真实 API)。

覆盖:
  - _adaptation_label: level → 适配标签
  - _extract_source_node_id (在 reviewer 测，此处仅 import 验证)
  - content_generator_node: 路径→生成3种资源/溯源标记/空路径降级/LLM未配置降级/单段失败容错
"""

import json

from app.agents.content_generator import (
    _adaptation_label,
    content_generator_node,
    MAX_NODES_TO_GENERATE,
    CONTENT_TYPES,
)


# ============================================================
# _adaptation_label
# ============================================================

def test_adaptation_label_beginner():
    assert _adaptation_label(1) == "beginner"
    assert _adaptation_label(2) == "beginner"


def test_adaptation_label_intermediate():
    assert _adaptation_label(3) == "intermediate"
    assert _adaptation_label(4) == "intermediate"


def test_adaptation_label_advanced():
    assert _adaptation_label(5) == "advanced"


# ============================================================
# content_generator_node (fake model + fake kg)
# ============================================================

class _FakeModel:
    """假 LLM: 从 system 消息解析要求的 content_type，返回对应类型的内容 JSON。"""

    def __init__(self, node_id="PY-005", invalid=False):
        self._node_id = node_id
        self._invalid = invalid
        self.calls = 0

    def invoke(self, messages):
        self.calls += 1
        if self._invalid:
            class _Bad:
                content = "这不是JSON"
            return _Bad()
        # 从 system 消息提取要求的 content_type
        sys_text = messages[0].content if messages else ""
        ctype = "lecture"
        for t in CONTENT_TYPES:
            if f'"{t}"' in sys_text:
                ctype = t
                break
        payload = {
            "content_type": ctype,
            "target_node_id": self._node_id,
            "difficulty_level": 2,
            "adaptation_profile": "beginner",
            "source_nodes": [f"{self._node_id}.key_points[0]", f"{self._node_id}.summary"],
            "content": f"# {ctype} 内容\n\n针对 {self._node_id} 的讲解...",
        }
        class _Resp:
            content = json.dumps(payload, ensure_ascii=False)
        return _Resp()


class _FakeKG:
    """graph_controller 用，content_generator 不直接用 kg 但闭包需要。"""
    pass


def _patch_model(monkeypatch, node_id="PY-005", invalid=False):
    monkeypatch.setattr(
        "app.agents.content_generator.get_default_chat_model",
        lambda: _FakeModel(node_id=node_id, invalid=invalid),
    )
    monkeypatch.setattr(
        "app.agents.content_generator.llm_configured",
        lambda: True,
    )


def _make_node(node_id="PY-005", name="循环", difficulty=2):
    return {
        "node_id": node_id, "name": name, "difficulty": difficulty,
        "summary": "循环是重复执行的结构", "key_points": ["for 循环", "while 循环"],
        "common_mistakes": ["忘记更新循环变量"],
    }


def test_node_generates_three_resources_per_node(monkeypatch):
    """每个节点生成 3 种资源 (lecture/practice_guide/test)。"""
    _patch_model(monkeypatch)
    node = content_generator_node(_FakeKG())
    state = {
        "user_profile": {"theory_level": 2},
        "knowledge_graph": {"learning_path": [_make_node()]},
    }
    result = node(state)
    gen = result["generated_content"]

    assert gen["node_count"] == 1
    assert len(gen["resources"]) == 3  # 1 节点 × 3 类型
    types = {r["content_type"] for r in gen["resources"]}
    assert types == set(CONTENT_TYPES)


def test_node_caps_node_count(monkeypatch):
    """路径节点超过 MAX_NODES_TO_GENERATE 时只取前 N 个。"""
    _patch_model(monkeypatch)
    path = [_make_node(f"PY-{i:03d}") for i in range(10)]
    node = content_generator_node(_FakeKG())
    result = node({"user_profile": {"theory_level": 2},
                   "knowledge_graph": {"learning_path": path}})
    assert result["generated_content"]["node_count"] == MAX_NODES_TO_GENERATE


def test_node_attaches_source_traceability(monkeypatch):
    """每段资源带 source_nodes 溯源标记。"""
    _patch_model(monkeypatch, "PY-005")
    node = content_generator_node(_FakeKG())
    result = node({"user_profile": {"theory_level": 2},
                   "knowledge_graph": {"learning_path": [_make_node()]}})
    for res in result["generated_content"]["resources"]:
        assert isinstance(res.get("source_nodes"), list)
        assert len(res["source_nodes"]) > 0
        assert res["target_node_id"] == "PY-005"


def test_node_empty_path_skips(monkeypatch):
    """学习路径为空 → 跳过生成，空资源。"""
    _patch_model(monkeypatch)
    node = content_generator_node(_FakeKG())
    result = node({"user_profile": {"theory_level": 2}, "knowledge_graph": {"learning_path": []}})
    assert result["generated_content"]["resources"] == []
    assert result["generated_content"]["node_count"] == 0


def test_node_llm_not_configured_degrades(monkeypatch):
    """LLM 未配置 → 降级空资源，不调 LLM。"""
    monkeypatch.setattr("app.agents.content_generator.llm_configured", lambda: False)
    node = content_generator_node(_FakeKG())
    result = node({"user_profile": {"theory_level": 2},
                   "knowledge_graph": {"learning_path": [_make_node()]}})
    assert result["generated_content"]["resources"] == []


def test_node_invalid_json_degrades_gracefully(monkeypatch):
    """LLM 返回非法 JSON 时 (parse_llm_json 返回 {}) → _generate_one 用 setdefault
    补全字段产出降级资源，不抛异常中断工作流。"""
    _patch_model(monkeypatch, invalid=True)
    node = content_generator_node(_FakeKG())
    result = node({"user_profile": {"theory_level": 2},
                   "knowledge_graph": {"learning_path": [_make_node()]}})
    # parse_llm_json 对非法文本返回 {} → _generate_one 补全后仍产出 3 段降级资源 (content 空)
    resources = result["generated_content"]["resources"]
    assert len(resources) == 3  # 不中断
    assert all(r.get("target_node_id") == "PY-005" for r in resources)
    assert all(r.get("content") == "" for r in resources)


def test_node_real_exception_tolerated(monkeypatch):
    """_generate_one 内部抛异常 (如 model.invoke 报错) → 该段跳过，其余正常，不中断。"""
    class _CrashingModel:
        def invoke(self, messages):
            raise RuntimeError("API timeout")
    monkeypatch.setattr(
        "app.agents.content_generator.get_default_chat_model",
        lambda: _CrashingModel(),
    )
    monkeypatch.setattr("app.agents.content_generator.llm_configured", lambda: True)
    node = content_generator_node(_FakeKG())
    result = node({"user_profile": {"theory_level": 2},
                   "knowledge_graph": {"learning_path": [_make_node()]}})
    # 3 段全抛异常 → resources 空，但不中断工作流
    assert result["generated_content"]["resources"] == []
    assert "失败" in result["orchestration_log"][-1]


# ============================================================
# 定向再生: correction_hint 注入 + retry_hint 状态流
# ============================================================

def test_build_prompt_injects_correction_hint():
    """correction_hint 非空 → system 消息含"上轮判定修正要求"块; 为空则不含。"""
    from app.agents.content_generator import _build_generation_prompt

    messages = _build_generation_prompt(_make_node(), 2, "lecture",
                                        correction_hint="find() 返回值描述错误")
    sys_text = messages[0].content
    assert "上轮判定修正要求" in sys_text
    assert "find() 返回值描述错误" in sys_text

    plain = _build_generation_prompt(_make_node(), 2, "lecture")
    assert "上轮判定修正要求" not in plain[0].content


def test_build_prompt_asks_unverified_claims():
    """prompt 要求 LLM 自声明 unverified_claims (认识状态标记, 阶段二)。"""
    from app.agents.content_generator import _build_generation_prompt

    sys_text = _build_generation_prompt(_make_node(), 2, "lecture")[0].content
    assert "unverified_claims" in sys_text
    assert "认识状态自声明" in sys_text


def test_build_prompt_contains_bridge_before_conclusion_rule():
    """先锚定后展开规则 (阶段三): 防结论先行合理化, 首节须复述节点事实。"""
    from app.agents.content_generator import _build_generation_prompt

    for ctype in CONTENT_TYPES:
        sys_text = _build_generation_prompt(_make_node(), 2, ctype)[0].content
        assert "先锚定后展开" in sys_text
        assert "结论不得先于其图谱依据出现" in sys_text


def test_prompt_spec_file_contains_bridge_and_claims_sections():
    """设计稿 data/prompts/04 与运行时 prompt 同步 (阶段二/三小节齐备)。"""
    from app.config import settings
    from pathlib import Path

    spec = (Path(settings.DATA_DIR).parent / "data" / "prompts"
            / "04_content_generator_agent.txt").read_text(encoding="utf-8")
    assert "先锚定后展开" in spec
    assert "认识状态自声明" in spec
    assert "定向再生" in spec


def test_generate_one_unverified_claims_fallback():
    """unverified_claims: LLM 未输出 → 空 list; 输出 list → 保留; 非 list → 强转空。"""
    from app.agents.content_generator import _generate_one

    class _Model:
        def __init__(self, payload):
            self._payload = payload

        def invoke(self, messages):
            class _Resp:
                content = json.dumps(self._payload, ensure_ascii=False)
            return _Resp()

    import app.agents.content_generator as cg
    original = cg.get_default_chat_model
    try:
        # 未输出 → []
        cg.get_default_chat_model = lambda: _Model({
            "content_type": "lecture", "target_node_id": "PY-005", "content": "x"})
        r1 = _generate_one(_make_node(), 2, "lecture")
        assert r1["unverified_claims"] == []

        # 正常输出 → 保留
        cg.get_default_chat_model = lambda: _Model({
            "content_type": "lecture", "target_node_id": "PY-005", "content": "x",
            "unverified_claims": ["用了生活化类比: 变量像盒子"]})
        r2 = _generate_one(_make_node(), 2, "lecture")
        assert r2["unverified_claims"] == ["用了生活化类比: 变量像盒子"]

        # 非 list (字符串) → 强转空
        cg.get_default_chat_model = lambda: _Model({
            "content_type": "lecture", "target_node_id": "PY-005", "content": "x",
            "unverified_claims": "一段话不是数组"})
        r3 = _generate_one(_make_node(), 2, "lecture")
        assert r3["unverified_claims"] == []
    finally:
        cg.get_default_chat_model = original


def test_node_retry_hint_injected_on_content_phase_rerun(monkeypatch):
    """内容阶段被 reviewer 打回 (content_phase_entered=True + retry_hint)
    → _generate_one 收到 retry_hint (定向再生, 取代盲重跑)。"""
    captured = []

    class _CaptureModel:
        def invoke(self, messages):
            captured.append(messages[0].content)  # 记录 system 消息
            class _Resp:
                content = json.dumps({
                    "content_type": "lecture", "target_node_id": "PY-005",
                    "adaptation_profile": "beginner",
                    "source_nodes": ["PY-005.summary"], "content": "x",
                }, ensure_ascii=False)
            return _Resp()

    monkeypatch.setattr("app.agents.content_generator.get_default_chat_model", lambda: _CaptureModel())
    monkeypatch.setattr("app.agents.content_generator.llm_configured", lambda: True)

    node = content_generator_node(_FakeKG())
    state = {
        "user_profile": {"theory_level": 2},
        "knowledge_graph": {"learning_path": [_make_node()]},
        "content_phase_entered": True,  # 内容阶段重跑
        "review_results": {"passed": False, "retry_hint": "测试题答案与实际运行结果不符"},
    }
    result = node(state)
    assert any("测试题答案与实际运行结果不符" in s for s in captured)
    assert any("定向再生" in line for line in result["orchestration_log"])


def test_node_first_run_no_retry_hint(monkeypatch):
    """首轮 (无 content_phase_entered) → 即使有 review_results (画像阶段结论) 也不注入。"""
    captured = []

    class _CaptureModel:
        def invoke(self, messages):
            captured.append(messages[0].content)
            class _Resp:
                content = json.dumps({
                    "content_type": "lecture", "target_node_id": "PY-005",
                    "adaptation_profile": "beginner",
                    "source_nodes": ["PY-005.summary"], "content": "x",
                }, ensure_ascii=False)
            return _Resp()

    monkeypatch.setattr("app.agents.content_generator.get_default_chat_model", lambda: _CaptureModel())
    monkeypatch.setattr("app.agents.content_generator.llm_configured", lambda: True)

    node = content_generator_node(_FakeKG())
    state = {
        "user_profile": {"theory_level": 2},
        "knowledge_graph": {"learning_path": [_make_node()]},
        # 首轮: 无 content_phase_entered, review_results 是画像阶段结论
        "review_results": {"passed": True, "retry_hint": "画像阶段的不相关 hint"},
    }
    node(state)
    assert all("画像阶段的不相关 hint" not in s for s in captured)


def test_generate_one_list_response_takes_first_dict(monkeypatch):
    """BUG-041: LLM 偶发返回数组而非对象 → _generate_one 取首个 dict，不抛异常。"""
    from app.agents.content_generator import _generate_one

    class _ListModel:
        def invoke(self, messages):
            payload = [{"content_type": "lecture", "content": "首元素", "target_node_id": "PY-005"}]
            class _Resp:
                content = json.dumps(payload, ensure_ascii=False)
            return _Resp()
    monkeypatch.setattr("app.agents.content_generator.get_default_chat_model", lambda: _ListModel())
    node = _make_node()
    result = _generate_one(node, 2, "lecture")
    # 取首个 dict 元素，不抛异常
    assert isinstance(result, dict)
    assert result["content"] == "首元素"
    assert result["target_node_id"] == "PY-005"


def test_generate_one_list_no_dict_degrades_gracefully(monkeypatch):
    """BUG-041: LLM 返回数组但无 dict 元素 → 降级空资源 dict，不抛异常。"""
    from app.agents.content_generator import _generate_one

    class _ListNoDictModel:
        def invoke(self, messages):
            class _Resp:
                content = json.dumps(["str", 123], ensure_ascii=False)
            return _Resp()
    monkeypatch.setattr("app.agents.content_generator.get_default_chat_model", lambda: _ListNoDictModel())
    result = _generate_one(_make_node(), 2, "lecture")
    assert isinstance(result, dict)  # 降级空资源，不抛
    assert result["content_type"] == "lecture"  # setdefault 补全


def test_node_empty_path_contract_complete(monkeypatch):
    """空路径降级时 generated_content 含完整字段 (content_types/generated_at 不缺失)。"""
    _patch_model(monkeypatch)
    node = content_generator_node(_FakeKG())
    result = node({"user_profile": {"theory_level": 2},
                   "knowledge_graph": {"learning_path": []}})
    gen = result["generated_content"]
    # 对接契约: 降级也含全部 key
    assert gen["resources"] == []
    assert gen["node_count"] == 0
    assert gen["content_types"] == ["lecture", "practice_guide", "test"]
    assert "generated_at" in gen


# ============================================================
# W5 动态反馈: select_feedback_nodes 纯函数
# ============================================================

from app.agents.content_generator import select_feedback_nodes

_PATH = [
    {"node_id": "PY-005", "name": "循环", "difficulty": 2},
    {"node_id": "PY-008", "name": "函数", "difficulty": 3},
    {"node_id": "PY-012", "name": "类", "difficulty": 4},
]
_WEAK = [{"node_id": "PY-005", "mastery": 0.2}]


def test_select_remediate_returns_weak_node():
    """remediate → 弱项节点本身。"""
    nodes = select_feedback_nodes("remediate", _WEAK, _PATH)
    assert [n["node_id"] for n in nodes] == ["PY-005"]


def test_select_advance_returns_next_node():
    """advance → 弱项之后的下一节点。"""
    nodes = select_feedback_nodes("advance", _WEAK, _PATH)
    assert [n["node_id"] for n in nodes] == ["PY-008"]


def test_select_scaffold_no_kg_returns_empty():
    """scaffold 无 kg → 空 (无法查前置)。"""
    assert select_feedback_nodes("scaffold", _WEAK, _PATH, kg=None) == []


def test_select_scaffold_with_kg():
    """scaffold 有 kg → 弱项前置节点 (去重, 最多2)。"""
    class _FakeKG:
        def get_prerequisites(self, wid):
            return [{"node_id": "PY-001", "name": "变量"}, {"node_id": "PY-003", "name": "条件"}]
    nodes = select_feedback_nodes("scaffold", _WEAK, _PATH, kg=_FakeKG())
    assert len(nodes) == 1
    assert nodes[0]["node_id"] == "PY-001"


def test_select_remediate_weak_not_in_path_returns_empty():
    """弱项不在 path 中 → remediate 返回空。"""
    weak = [{"node_id": "PY-999", "mastery": 0.1}]
    assert select_feedback_nodes("remediate", weak, _PATH) == []


def test_select_advance_weak_at_path_end_returns_empty():
    """弱项是路径最后一个 → advance 无下一节点 → 空。"""
    weak = [{"node_id": "PY-012", "mastery": 0.1}]
    assert select_feedback_nodes("advance", weak, _PATH) == []


def test_select_unknown_strategy_returns_empty():
    assert select_feedback_nodes("unknown", _WEAK, _PATH) == []


# ============================================================
# M5 适配率修复: _generate_one 强制 difficulty_level = 节点难度
# (LLM 自填难度会覆盖节点难度导致 gap 错位; 难度是图谱事实非 LLM 臆造)
# ============================================================

def test_generate_one_forces_difficulty_to_node_difficulty(monkeypatch):
    """LLM 返回的 difficulty_level 必须被节点难度强制覆盖 (gap=0 → 适配率达标)。"""
    from app.agents.content_generator import _generate_one

    class _Model:
        def invoke(self, messages):
            # LLM 自填 difficulty_level=5 (与节点难度 2 错位)
            payload = {
                "content_type": "lecture", "target_node_id": "PY-005",
                "difficulty_level": 5, "adaptation_profile": "beginner",
                "source_nodes": ["PY-005.summary"], "content": "# 讲义",
            }
            class _Resp:
                content = json.dumps(payload, ensure_ascii=False)
            return _Resp()
    monkeypatch.setattr("app.agents.content_generator.get_default_chat_model", lambda: _Model())
    node = _make_node(difficulty=2)  # 节点难度 2
    result = _generate_one(node, 2, "lecture")
    assert result["difficulty_level"] == 2, "难度须被节点难度强制覆盖, 非 LLM 自填的 5"


def test_generate_one_difficulty_defaults_when_node_missing(monkeypatch):
    """节点无 difficulty 字段 → 兜底 1。"""
    from app.agents.content_generator import _generate_one

    class _Model:
        def invoke(self, messages):
            payload = {"content_type": "lecture", "target_node_id": "PY-005", "content": "# x"}
            class _Resp:
                content = json.dumps(payload, ensure_ascii=False)
            return _Resp()
    monkeypatch.setattr("app.agents.content_generator.get_default_chat_model", lambda: _Model())
    node = {"node_id": "PY-005", "name": "x"}  # 无 difficulty
    result = _generate_one(node, 2, "lecture")
    assert result["difficulty_level"] == 1


# ============================================================
# BUG-043 一致性: 反馈再生路径 _generate_feedback_one 也强制难度=节点难度
# (主生成路径已修, 反馈路径同源 bug, 不得漂移)
# ============================================================

def test_generate_feedback_one_forces_difficulty_to_node(monkeypatch):
    """反馈再生: LLM 自填 difficulty_level 必须被节点难度强制覆盖。"""
    from app.agents.content_generator import _generate_feedback_one

    class _Model:
        def invoke(self, messages):
            payload = {
                "content_type": "lecture", "target_node_id": "PY-005",
                "difficulty_level": 5, "adaptation_profile": "beginner",
                "source_nodes": ["PY-005.summary"], "content": "# 降维讲义",
            }
            class _Resp:
                content = json.dumps(payload, ensure_ascii=False)
            return _Resp()
    monkeypatch.setattr("app.agents.content_generator.get_default_chat_model", lambda: _Model())
    node = _make_node(difficulty=2)
    result = _generate_feedback_one(node, 2, "lecture", "换角度重讲")
    assert result["difficulty_level"] == 2, "反馈路径难度须被节点难度强制覆盖, 非 LLM 自填的 5"


# ============================================================
# regenerate_for_feedback: 并行再生 + Spec B ContextVar 跨线程透传 + 单节点失败容错
# (串行->并行改造: target_nodes 并发再生, wall-clock ≈ 单次而非 N×;
#  worker 线程不继承 ContextVar, 须在 worker 内 re-set overrides -- 与主生成路径同模式)
# ============================================================

def _fake_model_recording(seen):
    """假 LLM 工厂: invoke 时从 user 消息解析 node_id, 记录调用的 node_id 与 worker 内 override 快照。"""
    from app.agents.llm import _current_overrides

    class _Model:
        def invoke(self, messages):
            uid = ""
            for m in messages:
                txt = getattr(m, "content", "")
                if "node_id:" in txt:
                    uid = txt.split("node_id:")[1].split("\n")[0].strip()
                    break
            seen["node_ids"].append(uid)
            seen["worker_overrides"].append(_current_overrides.get())
            payload = {
                "content_type": "lecture", "target_node_id": uid or "PY-005",
                "adaptation_profile": "beginner",
                "source_nodes": [f"{uid or 'PY-005'}.summary"], "content": f"# {uid} 讲义",
            }

            class _Resp:
                content = json.dumps(payload, ensure_ascii=False)
            return _Resp()
    return _Model()


def test_regenerate_for_feedback_parallel_generates_all_nodes(monkeypatch):
    """并行再生: 每个目标节点生成全部三种类型 (lecture/practice_guide/test), 不随策略单类型。"""
    from app.agents.content_generator import regenerate_for_feedback

    seen = {"node_ids": [], "worker_overrides": []}
    monkeypatch.setattr(
        "app.agents.content_generator.get_default_chat_model",
        lambda: _fake_model_recording(seen),
    )
    monkeypatch.setattr("app.agents.content_generator.llm_configured", lambda: True)

    nodes = [_make_node("DA-001", "数据分析流程", 1), _make_node("DA-003", "数据清洗", 2)]
    profile = {"theory_level": 2, "weak_topics": [
        {"node_id": "DA-001", "mastery": 0.0, "error_patterns": []},
        {"node_id": "DA-003", "mastery": 0.0, "error_patterns": []},
    ]}
    result = regenerate_for_feedback("remediate", profile, nodes, kg=None)
    assert result["strategy"] == "remediate"
    assert result["node_count"] == 1          # 目标节点数 (remediate 选 1)
    assert len(result["resources"]) == 3      # 每节点 lecture/practice_guide/test 三种
    types = {r["content_type"] for r in result["resources"]}
    assert types == {"lecture", "practice_guide", "test"}
    assert all(r["target_node_id"] == "DA-001" for r in result["resources"])
    assert seen["node_ids"] == ["DA-001", "DA-001", "DA-001"]


def test_regenerate_for_feedback_overrides_propagate_to_workers(monkeypatch):
    """Spec B: 主线程 use_llm_overrides 设的 ContextVar 须透传到 worker 线程
    (并行改造关键: worker 内 _current_overrides.set(overrides) 后 invoke 才能读到)。"""
    from app.agents.content_generator import regenerate_for_feedback
    from app.agents.llm import use_llm_overrides

    seen = {"node_ids": [], "worker_overrides": []}
    monkeypatch.setattr(
        "app.agents.content_generator.get_default_chat_model",
        lambda: _fake_model_recording(seen),
    )
    monkeypatch.setattr("app.agents.content_generator.llm_configured", lambda: True)

    overrides = {"api_key": "sk-agent-independent", "model": "agent-llm"}
    nodes = [_make_node("PY-005", "循环", 2), _make_node("PY-006", "函数", 2)]
    profile = {"theory_level": 2, "weak_topics": [
        {"node_id": "PY-005", "mastery": 0.0, "error_patterns": []},
        {"node_id": "PY-006", "mastery": 0.0, "error_patterns": []},
    ]}
    with use_llm_overrides(overrides):
        result = regenerate_for_feedback("remediate", profile, nodes, kg=None)
    assert len(result["resources"]) == 3   # 1 节点 × 3 类型
    assert all(o == overrides for o in seen["worker_overrides"]), \
        f"worker 线程未读到主线程 overrides: {seen['worker_overrides']}"


def test_regenerate_for_feedback_partial_failure_tolerated(monkeypatch):
    """单节点 LLM 失败不阻断其他节点 (per-node try/except, 失败计入 failures 不外抛)。"""
    from app.agents.content_generator import regenerate_for_feedback

    class _Model:
        def invoke(self, messages):
            uid = ""
            for m in messages:
                txt = getattr(m, "content", "")
                if "node_id:" in txt:
                    uid = txt.split("node_id:")[1].split("\n")[0].strip()
                    break
            if uid == "PY-005":
                raise RuntimeError("模拟 PY-005 LLM 失败")
            payload = {
                "content_type": "lecture", "target_node_id": uid,
                "adaptation_profile": "beginner",
                "source_nodes": [f"{uid}.summary"], "content": f"# {uid} 讲义",
            }

            class _Resp:
                content = json.dumps(payload, ensure_ascii=False)
            return _Resp()
    monkeypatch.setattr(
        "app.agents.content_generator.get_default_chat_model", lambda: _Model(),
    )
    monkeypatch.setattr("app.agents.content_generator.llm_configured", lambda: True)

    nodes = [_make_node("PY-005", "循环", 2), _make_node("PY-006", "函数", 2)]
    profile = {"theory_level": 2, "weak_topics": [
        {"node_id": "PY-005", "mastery": 0.0, "error_patterns": []},
        {"node_id": "PY-006", "mastery": 0.0, "error_patterns": []},
    ]}
    result = regenerate_for_feedback("remediate", profile, nodes, kg=None)
    assert result["node_count"] == 1
    # remediate 选出 1 节点 (PY-005), 其 3 种类型全失败被跳过 → 0 资源, 失败不外抛
    assert len(result["resources"]) == 0
