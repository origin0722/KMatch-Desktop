"""
知识图谱管控 Agent (Graph Controller Agent)

对齐 data/prompts/03_graph_controller_agent.txt。

职责: 根据已审核通过的用户画像，从领域元知识层组装个性化学习路径图谱，
并将节点掌握状态同步写回 Neo4j。本节点是工作流中"画像→可学习路径"的桥梁，
产出的 knowledge_graph 字段供第4周内容生成 Agent 溯源引用。

第3周实现范围 (无项目场景 — 学习路径组装):
  1. 从 user_profile 提取 known_ids / weak_ids / level / time_per_week
  2. 调用 engine.assemble_learning_path 组装渐进式路径 (依赖拓扑排序 + 难度升序)
  3. 估算总学时 (Σ estimated_minutes / 60)
  4. 派生节点状态更新: 弱项→difficult, 路径首节点→in_progress, 已掌握→mastered
  5. 写回 Neo4j 节点状态 + 写入 state.knowledge_graph

有项目场景 (项目图谱生成 / AST 解析) 第3周后续迭代补，本节点先不接入。
"""

from datetime import datetime
from typing import Optional

from app.graph.engine import KnowledgeGraph
from app.utils.logging import get_logger

logger = get_logger(__name__)

# 学习路径节点数上限 (对齐 prompt: 上限 20 个节点，约 40 小时学习量)
MAX_PATH_NODES = 20
# 每周学习量映射: 每周约 2 个节点 (每节点约 30 分钟*2 = 1h，time_per_week 小时)
NODES_PER_WEEK = 2


def _derive_max_nodes(time_per_week: Optional[int]) -> int:
    """根据每周可投入时间派生路径节点数上限。

    prompt 规则: 截取长度 = time_per_week * 2，上限 20，下限保 4 (避免路径过短无意义)。
    """
    tpw = time_per_week if isinstance(time_per_week, int) and time_per_week > 0 else 6
    return min(MAX_PATH_NODES, max(4, tpw * NODES_PER_WEEK))


def _compute_estimated_hours(path: list[dict]) -> float:
    """估算路径总学时 (小时): Σ node.estimated_minutes / 60，保留 1 位小数。

    纯函数 — 节点缺失 estimated_minutes 时按 0 计。
    """
    total_minutes = sum(
        n.get("estimated_minutes", 0) or 0 for n in path if isinstance(n, dict)
    )
    return round(total_minutes / 60, 1)


def _derive_status_updates(profile: dict, path: list[dict]) -> dict[str, str]:
    """从画像与路径派生节点状态更新映射 {node_id: status}。

    纯函数 — 不写库，仅计算应更新的状态:
      - known_topics (mastery≥0.8)  → mastered
      - weak_topics                 → difficult
      - 路径首节点 (非弱项)          → in_progress
    同一节点若同时命中多条规则，弱项 difficult 优先 (需重点学习)。
    """
    updates: dict[str, str] = {}

    for t in profile.get("known_topics", []):
        # BUG-039: 对齐画像 mastery 阈值 (known = mastery≥0.8)。
        # 画像 known_topics 已是 mastery≥0.8 子集,此处阈值仅作防御性校验。
        if isinstance(t, dict) and t.get("mastery", 0) >= 0.8:
            nid = t.get("node_id")
            if nid:
                updates[nid] = "mastered"

    for t in profile.get("weak_topics", []):
        if isinstance(t, dict):
            nid = t.get("node_id")
            if nid:
                updates[nid] = "difficult"  # 弱项优先级最高，覆盖 mastered

    # 路径首节点标记为进行中 (若该节点不是弱项)
    path_ids = [n.get("node_id") for n in path if isinstance(n, dict) and n.get("node_id")]
    if path_ids:
        first = path_ids[0]
        if first not in updates or updates[first] != "difficult":
            updates[first] = "in_progress"

    return updates


def _strip_node(node: dict) -> dict:
    """剥离内部检索字段 (_source/_score/_similarity)，返回干净节点 dict。"""
    return {k: v for k, v in node.items() if not k.startswith("_")}


def graph_controller_node(kg: KnowledgeGraph):
    """返回 LangGraph 节点函数。闭包注入 KnowledgeGraph 实例。"""

    def _node(state) -> dict:
        profile = state.get("user_profile", {})
        log = [f"[{datetime.utcnow().isoformat()}] 🗺️ 知识图谱管控: 开始组装学习路径"]

        # 画像为空 (审核未通过/降级) → 跳过组装，写空图谱 (字段与正常分支对齐，F7)
        if not profile:
            log.append("⚠️ 画像为空，跳过路径组装")
            return {
                "knowledge_graph": {
                    "learning_path": [],
                    "path_node_ids": [],
                    "estimated_total_hours": 0.0,
                    "node_status_updates": {},
                    "assembled_at": datetime.utcnow().isoformat() + "Z",
                },
                "orchestration_log": log,
            }

        known_ids = [t["node_id"] for t in profile.get("known_topics", []) if isinstance(t, dict) and t.get("node_id")]
        weak_ids = [t["node_id"] for t in profile.get("weak_topics", []) if isinstance(t, dict) and t.get("node_id")]
        level = profile.get("theory_level", 2) or 2
        max_nodes = _derive_max_nodes(profile.get("time_per_week"))

        log.append(
            f"📥 画像输入: known={len(known_ids)} weak={len(weak_ids)} "
            f"level={level} max_nodes={max_nodes}"
        )

        try:
            path = kg.assemble_learning_path(
                known_ids=known_ids,
                weak_ids=weak_ids,
                level=level,
                max_nodes=max_nodes,
            )
        except Exception:
            logger.error("学习路径组装失败", exc_info=True)
            log.append("❌ 学习路径组装异常，写空路径")
            return {
                "knowledge_graph": {
                    "learning_path": [],
                    "path_node_ids": [],
                    "estimated_total_hours": 0.0,
                    "node_status_updates": {},
                    "assembled_at": datetime.utcnow().isoformat() + "Z",
                },
                "orchestration_log": log,
            }

        clean_path = [_strip_node(n) for n in path]
        path_ids = [n["node_id"] for n in clean_path if n.get("node_id")]
        hours = _compute_estimated_hours(clean_path)
        status_updates = _derive_status_updates(profile, clean_path)

        # 写回 Neo4j 节点状态 (弱项 difficult / 路径首节点 in_progress / 已掌握 mastered)
        written = 0
        for nid, status in status_updates.items():
            try:
                kg.update_node_status(nid, status)
                written += 1
            except Exception:
                logger.warning("节点状态写回失败: %s=%s", nid, status, exc_info=True)

        log.append(
            f"✅ 路径组装完成: {len(path_ids)} 个节点，预估 {hours}h，"
            f"状态更新 {written}/{len(status_updates)}"
        )
        logger.info("学习路径组装: nodes=%d hours=%s status_updates=%d",
                    len(path_ids), hours, written)

        return {
            "knowledge_graph": {
                "learning_path": clean_path,
                "path_node_ids": path_ids,
                "estimated_total_hours": hours,
                "node_status_updates": status_updates,
                "assembled_at": datetime.utcnow().isoformat() + "Z",
            },
            "orchestration_log": log,
        }

    return _node
