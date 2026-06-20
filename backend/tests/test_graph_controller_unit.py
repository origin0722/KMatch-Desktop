"""graph_controller 纯函数单测 — 覆盖路径派生逻辑，免真实 Neo4j。

覆盖:
  - _derive_max_nodes: time_per_week → 节点数上限 (含上下限边界)
  - _compute_estimated_hours: Σ estimated_minutes / 60
  - _derive_status_updates: known→mastered / weak→difficult / 路径首节点→in_progress
  - graph_controller_node: 画像→路径组装 + 状态写回 (fake kg)
"""

from app.agents.graph_controller import (
    _derive_max_nodes,
    _compute_estimated_hours,
    _derive_status_updates,
    graph_controller_node,
)


# ============================================================
# _derive_max_nodes
# ============================================================

def test_max_nodes_from_time_per_week():
    """time_per_week=6 → 6*2=12 个节点。"""
    assert _derive_max_nodes(6) == 12


def test_max_nodes_capped_at_20():
    """time_per_week=15 → 30，但上限 20。"""
    assert _derive_max_nodes(15) == 20


def test_max_nodes_floor_at_4():
    """time_per_week=1 → 2，但下限 4。"""
    assert _derive_max_nodes(1) == 4


def test_max_nodes_invalid_time_falls_back():
    """非法 time_per_week (None/0/负) → 默认 6h → 12。"""
    assert _derive_max_nodes(None) == 12
    assert _derive_max_nodes(0) == 12
    assert _derive_max_nodes(-3) == 12


# ============================================================
# _compute_estimated_hours
# ============================================================

def test_estimated_hours_sum():
    """三节点 60+90+30=180 分钟 → 3.0 小时。"""
    path = [
        {"node_id": "PY-001", "estimated_minutes": 60},
        {"node_id": "PY-002", "estimated_minutes": 90},
        {"node_id": "PY-003", "estimated_minutes": 30},
    ]
    assert _compute_estimated_hours(path) == 3.0


def test_estimated_hours_missing_field():
    """节点缺 estimated_minutes → 按 0 计，不报错。"""
    path = [{"node_id": "PY-001"}, {"node_id": "PY-002", "estimated_minutes": 45}]
    assert _compute_estimated_hours(path) == 0.8  # 45/60 = 0.75 → round 0.8


def test_estimated_hours_empty_path():
    assert _compute_estimated_hours([]) == 0.0


# ============================================================
# _derive_status_updates
# ============================================================

def test_status_updates_known_mastered():
    """BUG-039: mastery≥0.8 的 known → mastered。"""
    profile = {
        "known_topics": [{"node_id": "PY-001", "mastery": 0.9}],
        "weak_topics": [],
    }
    updates = _derive_status_updates(profile, [])
    assert updates.get("PY-001") == "mastered"


def test_status_updates_weak_difficult_overrides_mastered():
    """弱项 difficult 优先级最高，覆盖 mastered。"""
    profile = {
        "known_topics": [{"node_id": "PY-001", "mastery": 0.9}],
        "weak_topics": [{"node_id": "PY-001", "mastery": 0.2}],
    }
    updates = _derive_status_updates(profile, [])
    # PY-001 同时在 known 和 weak → difficult 胜出
    assert updates["PY-001"] == "difficult"


def test_status_updates_known_below_threshold_not_mastered():
    """BUG-039: known_topics 中 mastery<0.8 (防御性) 不标 mastered, 与画像阈值一致。"""
    profile = {
        "known_topics": [{"node_id": "PY-001", "mastery": 0.5}],  # 低于0.8阈值
        "weak_topics": [],
    }
    updates = _derive_status_updates(profile, [])
    assert "PY-001" not in updates  # 未达0.8不标mastered


def test_status_updates_first_path_node_in_progress():
    """路径首节点 (非弱项) → in_progress。"""
    profile = {"known_topics": [], "weak_topics": []}
    path = [{"node_id": "PY-005"}, {"node_id": "PY-006"}]
    updates = _derive_status_updates(profile, path)
    assert updates["PY-005"] == "in_progress"
    assert "PY-006" not in updates


def test_status_updates_first_node_is_weak_stays_difficult():
    """路径首节点恰为弱项 → 保持 difficult，不被 in_progress 覆盖。"""
    profile = {"known_topics": [], "weak_topics": [{"node_id": "PY-005", "mastery": 0.1}]}
    path = [{"node_id": "PY-005"}, {"node_id": "PY-006"}]
    updates = _derive_status_updates(profile, path)
    assert updates["PY-005"] == "difficult"


# ============================================================
# graph_controller_node (集成 fake kg)
# ============================================================

class _FakeKG:
    """假 KnowledgeGraph: 记录调用参数，返回预设路径。"""

    def __init__(self, path=None, fail=False):
        self._path = path if path is not None else [
            {"node_id": "PY-005", "name": "循环", "difficulty": 2, "estimated_minutes": 60},
            {"node_id": "PY-008", "name": "函数", "difficulty": 3, "estimated_minutes": 90},
        ]
        self._fail = fail
        self.status_writes = {}  # 记录 update_node_status 调用

    def assemble_learning_path(self, known_ids, weak_ids, level, max_nodes):
        if self._fail:
            raise RuntimeError("db down")
        self.last_call = dict(known_ids=known_ids, weak_ids=weak_ids, level=level, max_nodes=max_nodes)
        return self._path

    def update_node_status(self, node_id, status):
        self.status_writes[node_id] = status


def _make_profile(known=None, weak=None, level=2, tpw=6):
    return {
        "known_topics": known or [],
        "weak_topics": weak or [],
        "theory_level": level,
        "time_per_week": tpw,
    }


def test_node_assembles_path_and_writes_status():
    """画像通过 → 组装路径 + 写回节点状态。"""
    kg = _FakeKG()
    node = graph_controller_node(kg)
    state = {"user_profile": _make_profile(
        known=[{"node_id": "PY-001", "mastery": 0.9}],
        weak=[{"node_id": "PY-005", "mastery": 0.2}],
    )}

    result = node(state)
    kg_out = result["knowledge_graph"]

    assert kg_out["path_node_ids"] == ["PY-005", "PY-008"]
    assert kg_out["estimated_total_hours"] == 2.5  # (60+90)/60
    # 调用参数透传
    assert kg.last_call["known_ids"] == ["PY-001"]
    assert kg.last_call["weak_ids"] == ["PY-005"]
    assert kg.last_call["level"] == 2
    # 状态写回: PY-001 mastered, PY-005 difficult, 路径首节点 PY-005 已是 difficult
    assert kg.status_writes.get("PY-001") == "mastered"
    assert kg.status_writes.get("PY-005") == "difficult"


def test_node_strips_internal_fields():
    """assemble 返回的 _source/_score 内部字段被剥离。"""
    kg = _FakeKG(path=[{"node_id": "PY-005", "name": "循环", "_source": "graph", "_score": 1.0}])
    node = graph_controller_node(kg)
    result = node({"user_profile": _make_profile()})

    path = result["knowledge_graph"]["learning_path"]
    assert path[0]["node_id"] == "PY-005"
    assert "_source" not in path[0]
    assert "_score" not in path[0]


def test_node_empty_profile_skips():
    """空画像 (降级) → 跳过组装，写空图谱，不调 engine。"""
    kg = _FakeKG()
    node = graph_controller_node(kg)
    result = node({"user_profile": {}})

    assert result["knowledge_graph"]["learning_path"] == []
    assert result["knowledge_graph"]["path_node_ids"] == []
    assert kg.status_writes == {}  # 未写状态


def test_node_assemble_failure_returns_empty():
    """engine 异常 → 写空路径，不抛 (工作流不中断)。"""
    kg = _FakeKG(fail=True)
    node = graph_controller_node(kg)
    result = node({"user_profile": _make_profile()})

    assert result["knowledge_graph"]["path_node_ids"] == []
    assert "❌" in result["orchestration_log"][-1]


def test_node_logs_progress():
    """日志含开始/输入/完成三段。"""
    kg = _FakeKG()
    node = graph_controller_node(kg)
    result = node({"user_profile": _make_profile(tpw=6)})
    log = result["orchestration_log"]
    assert any("🗺️" in line for line in log)
    assert any("📥" in line for line in log)
    assert any("✅" in line for line in log)
