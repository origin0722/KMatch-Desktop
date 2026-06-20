"""
可视化报告数据构建器 (Report Builder)

赛题(3)①要求"可视化个人学情与资源匹配度报告"，含三类可视化:
  ①知识盲区定位 ②资源难度匹配曲线 ③学习路径规划图。

本模块从工作流已有产出 (user_profile / knowledge_graph / generated_content /
review_results) 派生预计算好的报告数据契约 `learning_report`，供 B 端
(Dashboard/Learning 页) 直接渲染。纯函数，不调 LLM；REQUIRES 前置依赖边
尽力而为 (kg 可选，仅 learning_path 子对象取前置时用)。

被两处复用:
  - demo 模式: api/diagnostics.py assess 内联计算后嵌入 AssessResponse.learning_report
  - interactive 模式: api/learning.py /report 补跑后返回 LearningReportResponse.learning_report
"""

from datetime import datetime
from typing import Optional

from app.utils.logging import get_logger

logger = get_logger(__name__)

# mastery 三段制 (对齐 02_diagnostics_agent prompt + BUG-039)
# ≥0.8 已掌握(mastered) / 0.5-0.8 学习中(learning) / <0.5 困难(weak)
def _mastery_status(mastery: float) -> str:
    """mastery → 盲区状态标签。"""
    if mastery >= 0.8:
        return "mastered"
    if mastery >= 0.5:
        return "learning"
    return "weak"


# 资源难度匹配: |gap|<=1 匹配 / gap>1 偏难 / gap<-1 偏易 (确定性阈值，可单测)
def _match_status(gap: int) -> str:
    """resource_difficulty - node_difficulty 的 gap → 匹配状态。"""
    if gap > 1:
        return "too_hard"
    if gap < -1:
        return "too_easy"
    return "matched"


def _node_lookup(learning_path: list[dict]) -> dict[str, dict]:
    """learning_path → {node_id: node}，供按 node_id 富化 name/difficulty/estimated_minutes。"""
    return {
        n["node_id"]: n
        for n in learning_path
        if isinstance(n, dict) and n.get("node_id")
    }


def _path_index(learning_path: list[dict]) -> dict[str, int]:
    """learning_path → {node_id: 位置下标}，供 difficulty_match.path_position。"""
    return {
        n["node_id"]: i
        for i, n in enumerate(learning_path)
        if isinstance(n, dict) and n.get("node_id")
    }


def _build_blind_spots(profile: dict, learning_path: list[dict]) -> dict:
    """①知识盲区定位 — 仅被测评节点 (known+weak)，按 mastery 升序。

    name/difficulty 从 learning_path 富化 (弱项节点在路径组装时已优先纳入)；
    不在路径则 name 取 node_id、difficulty 缺省 0。
    """
    lookup = _node_lookup(learning_path)
    nodes = []
    # 合并 known + weak (weak 带 error_patterns)
    weak_ids = set()
    for t in profile.get("weak_topics", []):
        if not isinstance(t, dict):
            continue
        nid = t.get("node_id")
        if not nid:
            continue
        weak_ids.add(nid)
        n = lookup.get(nid, {})
        nodes.append({
            "node_id": nid,
            "name": n.get("name", nid),
            "difficulty": n.get("difficulty", 0),
            "mastery": t.get("mastery", 0),
            "status": _mastery_status(t.get("mastery", 0)),
            "error_patterns": t.get("error_patterns", []),
        })
    for t in profile.get("known_topics", []):
        if not isinstance(t, dict):
            continue
        nid = t.get("node_id")
        if not nid or nid in weak_ids:
            continue  # weak 优先，去重
        n = lookup.get(nid, {})
        nodes.append({
            "node_id": nid,
            "name": n.get("name", nid),
            "difficulty": n.get("difficulty", 0),
            "mastery": t.get("mastery", 0),
            "status": _mastery_status(t.get("mastery", 0)),
            "error_patterns": [],
        })

    # 按 mastery 升序 (盲区最严重的在前)
    nodes.sort(key=lambda x: x.get("mastery", 0))

    counts = {"mastered": 0, "learning": 0, "weak": 0}
    mastery_sum = 0.0
    for n in nodes:
        counts[n["status"]] = counts.get(n["status"], 0) + 1
        mastery_sum += n.get("mastery", 0)
    total = len(nodes)
    overall_mastery = round(mastery_sum / total, 3) if total else 0.0

    return {
        "nodes": nodes,
        "summary": {
            "total": total,
            "mastered": counts["mastered"],
            "learning": counts["learning"],
            "weak": counts["weak"],
            "overall_mastery": overall_mastery,
        },
    }


def _build_difficulty_match(
    generated_content: dict, learning_path: list[dict], profile: dict
) -> dict:
    """②资源难度匹配曲线 — per-resource 粒度 (1节点3段资源，每段难度可能不同)。

    gap = resource_difficulty - node_difficulty (带符号，直接做曲线 y 轴)；
    target_node_id 不在 learning_path 时点保留 (node_difficulty/path_position 缺省 0)，不丢点。
    mastery 取该节点 profile mastery (无则 0)。
    """
    lookup = _node_lookup(learning_path)
    pidx = _path_index(learning_path)
    # node_id → mastery (known/weak 合并)
    mastery_by_node = {}
    for section in ("known_topics", "weak_topics"):
        for t in profile.get(section, []):
            if isinstance(t, dict) and t.get("node_id"):
                mastery_by_node[t["node_id"]] = t.get("mastery", 0)

    resources = generated_content.get("resources", []) if isinstance(generated_content, dict) else []
    points = []
    for res in resources:
        if not isinstance(res, dict):
            continue
        nid = res.get("target_node_id", "")
        node = lookup.get(nid, {})
        node_diff = node.get("difficulty", 0) if node else 0
        res_diff = res.get("difficulty_level", 0)
        if not isinstance(res_diff, (int, float)):
            res_diff = 0
        gap = int(res_diff) - int(node_diff)
        points.append({
            "node_id": nid,
            "name": node.get("name", nid) if node else nid,
            "content_type": res.get("content_type", ""),
            "node_difficulty": node_diff,
            "resource_difficulty": res_diff,
            "mastery": mastery_by_node.get(nid, 0),
            "gap": gap,
            "match_status": _match_status(gap),
            "path_position": pidx.get(nid, -1),
        })

    status_counts = {"matched": 0, "too_hard": 0, "too_easy": 0}
    gap_sum = 0
    for p in points:
        status_counts[p["match_status"]] = status_counts.get(p["match_status"], 0) + 1
        gap_sum += p["gap"]
    total = len(points)
    avg_gap = round(gap_sum / total, 2) if total else 0.0

    return {
        "points": points,
        "summary": {
            "total_resources": total,
            "matched": status_counts["matched"],
            "too_hard": status_counts["too_hard"],
            "too_easy": status_counts["too_easy"],
            "avg_gap": avg_gap,
        },
    }


def _build_learning_path_graph(
    knowledge_graph: dict, profile: dict, kg=None
) -> dict:
    """③学习路径规划图 — G6 友好的 nodes/edges 结构。

    nodes 按路径顺序；status 来自 node_status_updates (mastered/in_progress/difficult)，
    未在更新映射中且非已掌握 → unlearned；is_current = recommended_path.current_node。
    edges: PATH_SEQUENCE (相邻节点恒有 N-1 条) + REQUIRES (kg 可用时取路径节点间前置，尽力而为)。
    """
    kg_state = knowledge_graph if isinstance(knowledge_graph, dict) else {}
    learning_path = kg_state.get("learning_path", [])
    status_updates = kg_state.get("node_status_updates", {})
    rec_path = profile.get("recommended_path", {}) if isinstance(profile, dict) else {}
    current_node = rec_path.get("current_node", "")
    next_nodes = rec_path.get("next_nodes", [])
    weeks = rec_path.get("estimated_completion_weeks", 0)

    # node_id → mastery
    mastery_by_node = {}
    for section in ("known_topics", "weak_topics"):
        for t in profile.get(section, []):
            if isinstance(t, dict) and t.get("node_id"):
                mastery_by_node[t["node_id"]] = t.get("mastery", 0)

    nodes = []
    for i, n in enumerate(learning_path):
        if not isinstance(n, dict) or not n.get("node_id"):
            continue
        nid = n["node_id"]
        # 路径图状态: node_status_updates 优先，否则按 mastery 推
        if nid in status_updates:
            status = status_updates[nid]
        else:
            # BUG B13: 旧 `if m` 把 mastery=0 (已测全错, 属 weak) 当 falsy 误判 unlearned。
            # 改按"是否在 mastery_by_node"判已测: 在表内 → 用 _mastery_status (0→weak);
            # 不在表 → 未测 unlearned。
            if nid in mastery_by_node:
                status = _mastery_status(mastery_by_node[nid])  # 0→weak, 非 unlearned
            else:
                status = "unlearned"
        nodes.append({
            "node_id": nid,
            "name": n.get("name", nid),
            "difficulty": n.get("difficulty", 0),
            "estimated_minutes": n.get("estimated_minutes", 0),
            "mastery": mastery_by_node.get(nid, 0),
            "status": status,
            "is_current": nid == current_node,
            "position": i,
        })

    # PATH_SEQUENCE 边: 相邻节点
    edges = []
    ids = [n["node_id"] for n in nodes]
    for i in range(len(ids) - 1):
        edges.append({"source": ids[i], "target": ids[i + 1], "type": "PATH_SEQUENCE"})

    # REQUIRES 边: kg 可用时，对路径节点取前置依赖 (尽力而为，仅取路径内前置)。
    # 去重仅针对 REQUIRES 自身 (与 PATH_SEQUENCE 同 (source,target) 但不同类型，可共存)。
    if kg is not None:
        path_id_set = set(ids)
        seen_requires = set()
        for nid in ids:
            try:
                prereqs = kg.get_prerequisites(nid)
            except Exception:
                logger.debug("取前置失败 node=%s", nid, exc_info=True)
                continue
            if not prereqs:
                continue
            for pr in prereqs:
                pid = pr.get("node_id") if isinstance(pr, dict) else None
                if not pid or pid not in path_id_set:
                    continue
                key = (pid, nid)
                if key in seen_requires:
                    continue
                seen_requires.add(key)
                edges.append({"source": pid, "target": nid, "type": "REQUIRES"})

    return {
        "nodes": nodes,
        "edges": edges,
        "estimated_total_hours": kg_state.get("estimated_total_hours", 0.0),
        "path_length": len(ids),
        "current_node": current_node,
        "next_nodes": next_nodes,
        "estimated_completion_weeks": weeks,
    }


def build_learning_report(
    profile: dict,
    knowledge_graph: dict,
    generated_content: dict,
    review_results: dict,
    kg=None,
) -> dict:
    """组装可视化报告数据契约 (三类可视化预计算)。纯函数，不调 LLM。

    Args:
        profile: 用户画像 (含 known_topics/weak_topics/recommended_path)
        knowledge_graph: {learning_path, path_node_ids, estimated_total_hours, node_status_updates}
        generated_content: {resources[], ...}; resources 含 target_node_id/difficulty_level/content_type
        review_results: {passed, overall_score, threshold}
        kg: 可选 KnowledgeGraph，仅 learning_path 子对象取 REQUIRES 前置边用

    Returns:
        learning_report dict (blind_spots/difficulty_match/learning_path/
        review_status/quality_metrics/generated_at)
    """
    profile = profile or {}
    knowledge_graph = knowledge_graph or {}
    generated_content = generated_content or {}
    review_results = review_results or {}
    learning_path = knowledge_graph.get("learning_path", [])

    blind_spots = _build_blind_spots(profile, learning_path)
    difficulty_match = _build_difficulty_match(generated_content, learning_path, profile)
    learning_path_graph = _build_learning_path_graph(knowledge_graph, profile, kg)

    review_status = {
        "passed": bool(review_results.get("passed", False)),
        "overall_score": review_results.get("overall_score", 0.0),
        "threshold": review_results.get("threshold", 0.85),
    }

    # 赛题 M5 质量检测指标 (幻觉率/适配率/覆盖率) — 纯函数派生,复用已算好的
    # difficulty_match 避免重算。per-session 实时展示供评委,批量聚合见 run_quality_test.py。
    from app.agents.quality_metrics import compute_quality_metrics
    quality_metrics = compute_quality_metrics(
        profile, knowledge_graph, generated_content, review_results,
        learning_report={"difficulty_match": difficulty_match},
    )

    return {
        "blind_spots": blind_spots,
        "difficulty_match": difficulty_match,
        "learning_path": learning_path_graph,
        "review_status": review_status,
        "quality_metrics": quality_metrics,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
