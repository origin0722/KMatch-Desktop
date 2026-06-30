"""
学情检测 Agent (Diagnostics Agent)

对齐 data/prompts/02_diagnostics_agent.txt。

职责: 三维能力测评（理论 + 实操 + 学习风格）→ 输出用户能力画像 v3。
本节点聚焦理论测评（实操/风格问卷第4-5周补），流程:
  1. 取题源: 从知识图谱按目标方向/已知节点抽取候选知识点 (engine)
  2. 生成题: LLM 基于节点 key_points 生成理论题（选择+判断，≤10题）
  3. 作答:   demo 模式 LLM 扮演该水平学习者自动作答；interactive 模式待前端提交
  4. 评估:   LLM 逐题判分 → 计算 mastery
  5. 画像:   汇总为画像 v3 JSON

零基础边界(BUG-006): known_topics 为空时从 difficulty 1-2 入口节点出题，
engine.assemble_learning_path / get_by_difficulty 已内置处理。
"""

import json
import random
import uuid
from datetime import datetime

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.llm import _current_overrides, get_default_chat_model, llm_configured
from app.graph.engine import KnowledgeGraph
from app.utils.json_utils import parse_llm_json
from app.utils.logging import get_logger

logger = get_logger(__name__)

# 测评参数（对齐 diagnostics prompt: 理论≤10题）
MAX_THEORY_QUESTIONS = 10
QUESTIONS_PER_NODE = 2
# 题库驱动出题: 从 :Question 节点抽取的题型 (code 题无法可靠 LLM 判分, 留给 content_generator/code_tester)
BANK_TYPES = ("choice", "fill")


def _fetch_candidate_nodes(kg: KnowledgeGraph, known_topics: list, target_direction: str) -> list[dict]:
    """从图谱抽取出题候选节点。

    - 有已知节点: assemble_learning_path 取后继路径节点
    - 零基础:     get_by_difficulty(1,2) 取基础入口节点
    """
    known_ids = [t["node_id"] for t in known_topics if isinstance(t, dict) and t.get("node_id")]

    if known_ids:
        nodes = kg.assemble_learning_path(known_ids=known_ids, level=2, max_nodes=8)
        if nodes:
            return nodes

    # 零基础 or 路径为空 → 基础入口节点
    return kg.get_by_difficulty(1, 2)[:8]


def _node_facts_text(nodes: list[dict]) -> str:
    """构造节点事实文本 (公共函数): 供出题/补题 prompt 共用。"""
    lines = []
    for n in nodes:
        kps = n.get("key_points", [])
        nid = n.get("node_id") or n.get("id", "?")
        lines.append(
            f"- 节点 {nid}《{n.get('name','')}》(难度{n.get('difficulty',1)}): "
            f"{'；'.join(kps[:4])}"
        )
    return "\n".join(lines)


def _demo_answer(questions: list[dict], target_direction: str) -> list:
    """demo 模式: LLM 扮演一个初学该方向的学习者作答，按难度控制错题率以体现弱项。"""
    model = get_default_chat_model()
    qdesc = []
    for i, q in enumerate(questions):
        diff = q.get("difficulty", 1)
        # options 仅 choice 题展示; fill 题无 options (题库 fill 题不带 options)
        opts = q.get("options")
        if q.get("type") == "choice" and opts:
            opt_text = f" 选项:{opts}"
        elif q.get("type") == "fill":
            opt_text = " (填空题)"
        else:
            opt_text = f" 选项:{opts or '对/错'}"
        qdesc.append(
            f"{i+1}. [难度{diff}] [{q.get('type')}] {q.get('question')}{opt_text}"
        )
    system = SystemMessage(content=(
        "你是一个正在学习 Python 的初学者，理论水平约 1-2 级。"
        "请按以下正确率作答：难度1~2的题约 70% 正确、难度3的题约 50% 正确、难度4~5的题约 30% 正确。"
        "答错的题应选择看似合理但实际错误的选项（模拟典型初学者的误解）。"
        "严格输出 JSON 数组，元素为作答字符串(选择题给选项内容如'A'或'B',判断题给'对'或'错')。"
        "不要输出 JSON 以外文字。"
    ))
    user = HumanMessage(content=(
        f"你的学习目标: {target_direction}\n题目:\n" + "\n".join(qdesc) + "\n\n请逐题作答。"
    ))
    resp = model.invoke([system, user])
    answers = parse_llm_json(resp.content)
    if not isinstance(answers, list):
        answers = []
    if len(answers) != len(questions):
        logger.warning(
            "LLM 作答数量(%d)与出题数量(%d)不一致，已自动对齐",
            len(answers), len(questions),
        )
    # 对齐题目数量
    return (answers + [""] * len(questions))[: len(questions)]


def _grade(questions: list[dict], answers: list) -> dict:
    """LLM 逐题判分，返回逐题得分与汇总。"""
    model = get_default_chat_model()
    pairs = []
    for q, a in zip(questions, answers):
        pairs.append({
            "node_id": q.get("node_id"),
            "question": q.get("question"),
            "correct_answer": q.get("answer"),
            "user_answer": a,
        })
    system = SystemMessage(content=(
        "你是阅卷 Agent。逐题判断用户作答是否正确。"
        "严格输出 JSON 数组，元素顺序需与输入题目顺序一一对应，每个元素: "
        '{"question_index": <题目在原 questions 数组中的下标，从 0 开始>, '
        '"node_id": "PY-xxx", "correct": true|false}。'
        "不要输出 JSON 以外文字。"
    ))
    user = HumanMessage(content="题目与作答:\n" + json.dumps(pairs, ensure_ascii=False))
    resp = model.invoke([system, user])
    grades = parse_llm_json(resp.content)
    if not isinstance(grades, list):
        grades = []

    correct_by_node: dict[str, list[dict]] = {}
    correct_count = 0
    seen_q_idx: set[int] = set()  # BUG-005x: 按 question_index 去重，防 LLM 多返虚增 correct_count
    for idx, g in enumerate(grades):
        if not isinstance(g, dict):
            continue
        # 优先用 LLM 显式回写的 question_index（根除顺序依赖，BUG-022 治本）；
        # LLM 漏题/乱序时回退到 grades 数组下标兜底。
        q_idx = g.get("question_index", idx)
        if not isinstance(q_idx, int) or q_idx < 0 or q_idx >= len(questions):
            q_idx = idx
        if q_idx in seen_q_idx:  # 同一题重复判分 → 跳过 (BUG-5)
            continue
        seen_q_idx.add(q_idx)
        # node_id 优先用题目真实值反查 (F5: 比 grade 二次回传可靠，
        # 避免 LLM 漏写/错写 node_id 导致逐节点掌握度全丢)；
        # 仅在反查失败时才信任 grade 回传的 node_id。
        nid = questions[q_idx].get("node_id") if q_idx < len(questions) else None
        if not nid:
            nid = g.get("node_id")
        # BUG-2: 防 LLM 把 correct 字符串化 ("false"/"False") 被 bool() 误判为 True
        raw_correct = g.get("correct")
        if isinstance(raw_correct, bool):
            ok = raw_correct
        elif isinstance(raw_correct, str):
            ok = raw_correct.strip().lower() == "true"
        else:
            ok = bool(raw_correct)
        correct_by_node.setdefault(nid, []).append({
            "question_index": q_idx,
            "correct": ok,
        })
        if ok:
            correct_count += 1

    return {
        "per_node": correct_by_node,
        "correct_count": correct_count,
        "total_count": len(questions),
    }


def _build_profile(target_direction, nodes, grading, questions: list = None) -> dict:
    """根据判分结果组装画像 v3。

    questions (BUG-036 深化): 题目列表，含 question 文本 + question_index 对齐 per_node，
    用于让 error_pattern 引用实际错题题目而非猜测知识点 (reviewer 批评旧实现 fabricated)。
    """
    per_node = grading["per_node"]
    total = grading["total_count"] or 1
    questions = questions or []

    # 构建 node_id → [错题 dict] 映射 (per_node 记 question_index，反查 questions 题目文本)
    wrong_by_node: dict[str, list[dict]] = {}
    for nid, results in per_node.items():
        for g in (results or []):
            if isinstance(g, dict) and not g.get("correct"):
                qidx = g.get("question_index")
                if isinstance(qidx, int) and 0 <= qidx < len(questions):
                    wrong_by_node.setdefault(nid, []).append(questions[qidx])

    known_topics, weak_topics = [], []
    for n in nodes:
        nid = n["node_id"]
        results = per_node.get(nid, [])
        if not results:
            continue
        # per_node 新结构: [{question_index, correct}, ...]
        corrects = [g["correct"] for g in results if isinstance(g, dict)]
        mastery = sum(corrects) / len(corrects) if corrects else 0
        entry = {"node_id": nid, "mastery": round(mastery, 2)}
        # BUG-039: 对齐 diagnostics prompt 三段制 — mastery≥0.8 已掌握(known),
        # 0.5-0.8 学习中、<0.5 困难均属"未达已掌握"→ weak (需学习)。
        # 旧 >=0.5 把"一半题错"(0.5)误归 known,致 weak 空、与错题矛盾 → reviewer 打回循环。
        if mastery >= 0.8:
            known_topics.append({**entry, "last_test_score": round(mastery * 10, 1)})
        else:
            weak_topics.append({**entry, "error_patterns": _build_error_patterns(n, wrong_by_node.get(nid, []))})

    overall = grading["correct_count"] / total
    # BUG-035: level 1-5 分段映射，对齐级数↔正确率语义
    theory_level = _derive_theory_level(overall)

    # weakness_areas 直接复用 weak_topics (BUG-039配套: 阈值须与 weak_topics 一致 <0.8,
    # 旧用 <0.5 重算致 mastery=0.5 节点进 weak_topics 却不进 weakness_areas → 矛盾被reviewer打回)
    node_by_id = {n["node_id"]: n for n in nodes if n.get("node_id")}
    weakness_areas = []
    for t in weak_topics:
        nid = t.get("node_id") if isinstance(t, dict) else None
        n = node_by_id.get(nid) if nid else None
        name = (n or {}).get("name", nid or "该知识点")
        mastery = t.get("mastery", 0) if isinstance(t, dict) else 0
        if mastery < 0.5:
            weakness_areas.append(f"对《{name}》掌握不足（mastery={mastery}）")
        else:
            weakness_areas.append(f"对《{name}》尚需巩固（mastery={mastery}，学习中）")

    # 推荐起始节点: 弱项优先 → 第一个未掌握候选 → 默认 PY-001
    # BUG-038: 全掌握时不应回退到已掌握的 nodes[0]/PY-001，否则 current_node=已掌握+weeks=4 矛盾
    known_ids = [t["node_id"] for t in known_topics if isinstance(t, dict) and t.get("node_id")]
    known_set = set(known_ids)
    weak_ids = [t["node_id"] for t in weak_topics if isinstance(t, dict) and t.get("node_id")]
    unmastered_nodes = [n for n in nodes if n.get("node_id") not in known_set]

    if weak_topics:
        recommended_start = weak_topics[0]["node_id"]
    elif unmastered_nodes:
        # 有未掌握候选 → 从第一个未掌握节点开始 (非已掌握的 nodes[0])
        recommended_start = unmastered_nodes[0]["node_id"]
    elif nodes:
        # 所有候选已掌握 → 巩固复习，起点取最后掌握的节点 (进阶方向)
        recommended_start = nodes[-1]["node_id"]
    else:
        recommended_start = "PY-001"

    # 推荐路径 (对齐 profile_schema.json recommended_path: object)。
    # next_nodes 从候选 nodes 顺序中取 current_node 之后的 3-5 个；
    # 候选 nodes 已由 engine.assemble_learning_path 按"距离+难度"排序，
    # 故后续节点即为合理的进阶序列。
    # BUG-034: 排除已掌握节点，避免推荐 mastery=1.0 的节点造成逻辑矛盾
    next_nodes = _suggest_next_nodes(nodes, recommended_start, known_ids=known_ids)

    # 预估完成周数: 弱项越多周期越长
    # BUG-038: 无弱项 (全掌握) → 巩固周数 1-2 周，不再固定 4 周 (避免矛盾)
    if weak_topics:
        estimated_weeks = max(2, 2 + len(weak_topics))
    else:
        estimated_weeks = max(1, len(unmastered_nodes))  # 仅未掌握节点数，全掌握→1周巩固

    return {
        "profile_id": f"UP-DIA-{uuid.uuid4().hex[:6]}",
        "name": "测评用户",
        "created_at": datetime.utcnow().isoformat() + "Z",
        "type": "学情检测产出",
        "theory_level": theory_level,
        "practical_level": 1,  # 实操测评第4周补，暂记最低
        "learning_style": "read_write",  # 风格问卷第5周补，暂默认
        "target_direction": target_direction,
        "preferred_pace": "normal",
        "time_per_week": 6,
        "known_topics": known_topics,
        "weak_topics": weak_topics,
        "weakness_areas": weakness_areas or ["暂无明显弱项"],
        "recommended_path": {
            "current_node": recommended_start,
            "next_nodes": next_nodes,
            "estimated_completion_weeks": estimated_weeks,
        },
        "raw_assessment_data": {
            "theory_test": {
                "total_questions": total,
                "correct": grading["correct_count"],
            }
        },
    }


def _derive_theory_level(overall: float) -> int:
    """正确率 → 理论等级 (1-5)，分段映射对齐级数↔正确率语义。

    BUG-035: 旧 `int(overall*5)+1` 把 0.7 正确率误判为 4 级，但 4 级语义应≥0.8
    (reviewer prompt "4级通常对应85%以上")，reviewer 据此判 factual_accuracy
    不自洽打回。改为保守分段映射，使级数与正确率自洽：
      <0.6→1, <0.7→2, <0.8→3, <0.9→4, ≥0.9→5
    （0.7→3，0.85→4，避免低正确率误判高等级）
    """
    if overall < 0.6:
        return 1
    if overall < 0.7:
        return 2
    if overall < 0.8:
        return 3
    if overall < 0.9:
        return 4
    return 5


def _build_error_patterns(node: dict, wrong_questions: list[dict] = None) -> list[str]:
    """生成具体 error_pattern，对齐实际错题 (BUG-036 深化)。

    reviewer 批评旧实现（按 key_points[0] 猜知识点）"与实际错题不符/fabricated"。
    正确做法: 直接引用该节点的错题题目本身，确保 error_pattern 与错题 100% 对齐。
    无错题文本时回退到 common_mistakes/key_points。
    """
    wrong_questions = wrong_questions or []
    if wrong_questions:
        # 引用错题题目 (截断超长)，最多 2 条
        patterns = []
        for q in wrong_questions[:2]:
            qtext = q.get("question") or q.get("q") or ""
            if qtext:
                qtext = qtext if len(qtext) <= 60 else qtext[:60] + "..."
                patterns.append(f"错题: {qtext}")
        if patterns:
            return patterns
    # 回退: 无错题文本 → common_mistakes / key_points
    mistakes = node.get("common_mistakes") or []
    if mistakes:
        first = mistakes[0]
        return [first if isinstance(first, str) else str(first)]
    kps = node.get("key_points") or []
    name = node.get("name", "该知识点")
    if kps:
        first_kp = kps[0] if isinstance(kps[0], str) else str(kps[0])
        return [f"对《{name}》中「{first_kp}」理解有误"]
    return [f"对《{name}》掌握不足"]


def _suggest_next_nodes(nodes: list[dict], current_node: str, known_ids: list = None, limit: int = 5) -> list[str]:
    """从候选 nodes 顺序中取 current_node 之后的进阶节点 id（最多 limit 个）。

    候选 nodes 已由 engine.assemble_learning_path 按"距离升序、层内难度升序"排序，
    故 current_node 之后的节点即为合理的下一步学习序列。current_node 自身排除。

    BUG-034: 排除 known_topics 中已掌握节点，避免推荐已 mastery=1.0 的节点造成逻辑矛盾。
    """
    known_set = set(known_ids or [])
    ids = [n["node_id"] for n in nodes if n.get("node_id")]
    try:
        start_idx = ids.index(current_node)
    except ValueError:
        # current_node 不在候选列表（如默认 PY-001）→ 从头取候选
        candidates = ids
    else:
        candidates = ids[start_idx + 1:]
    # 排除已掌握节点 (BUG-034)
    return [nid for nid in candidates if nid not in known_set][:limit]


def _select_from_bank(
    kg: KnowledgeGraph,
    nodes: list[dict],
    target_count: int = MAX_THEORY_QUESTIONS,
    seed: int | None = None,
) -> list[dict]:
    """从候选节点的 :Question 题库抽 choice/fill 题,注入 node_id。

    - 调 kg.get_questions_for_nodes 取每节点最多 QUESTIONS_PER_NODE 道 (type 限定 BANK_TYPES)
    - 题库题已带 source_node_id (import 时存), _question_from_record 注入 node_id 别名
    - random.shuffle 保证不每次抽同样题 (seed=None 每次不同; 单测传 seed 固定)
    - 返回题数 <= target_count; 不足部分由调用方 LLM 补
    """
    node_ids = [n.get("node_id") or n.get("id") for n in nodes
                if isinstance(n, dict) and (n.get("node_id") or n.get("id"))]
    if not node_ids:
        return []
    banked = kg.get_questions_for_nodes(node_ids, types=list(BANK_TYPES), max_per_node=QUESTIONS_PER_NODE)
    # 仅保留 BANK_TYPES (防御: 引擎 type 筛选已做, 此处再兜底)
    banked = [q for q in banked if q.get("type") in BANK_TYPES]
    rng = random.Random(seed) if seed is not None else random
    rng.shuffle(banked)
    return banked[:target_count]


def _build_supplement_prompt(
    nodes: list[dict],
    target_direction: str,
    shortfall: int,
    covered_node_ids: set,
) -> list:
    """构造补题 prompt: 仅补 shortfall 道 choice/fill (避开已抽节点)。"""
    # 优先用未覆盖的节点事实, 不够再混入已覆盖
    uncovered = [n for n in nodes if (n.get("node_id") or n.get("id")) not in covered_node_ids]
    fact_nodes = uncovered if len(uncovered) >= 2 else nodes
    system = SystemMessage(content=(
        "你是 KMatch 学情检测 Agent。基于知识图谱节点事实补充 Python 理论测评题。"
        f"题型限定选择题(choice)和填空题(fill),共 {shortfall} 道。"
        "严格输出 JSON 数组,每个元素: "
        '{"type":"choice|fill","node_id":"PY-xxx","question":"题干",'
        '"options":["A.."](仅choice),"answer":"答案(choice给字母,fill给文本)","difficulty":1-5}。'
        "不要输出 JSON 以外文字。"
    ))
    user = HumanMessage(content=(
        f"学习者目标方向: {target_direction}\n\n"
        f"可用知识节点:\n" + _node_facts_text(fact_nodes) + "\n\n"
        f"请补充 {shortfall} 道 choice/fill 题 (每题必填 node_id)。"
    ))
    return [system, user]


def _generate_supplement(
    nodes: list[dict], target_direction: str, shortfall: int, covered_node_ids: set
) -> list[dict]:
    """LLM 补题,返回 <= shortfall 道。失败/不足 → 返回空 (降级为题库题数)。"""
    model = get_default_chat_model()
    resp = model.invoke(_build_supplement_prompt(nodes, target_direction, shortfall, covered_node_ids))
    data = parse_llm_json(resp.content)
    if not isinstance(data, list):
        return []
    # 过滤: 仅 BANK_TYPES, 必须有 node_id (补注入: 缺则用首个候选节点兜底)
    fallback_nid = (nodes[0].get("node_id") or nodes[0].get("id")) if nodes else None
    valid = []
    for q in data:
        if not isinstance(q, dict) or q.get("type") not in BANK_TYPES:
            continue
        if not q.get("node_id") and fallback_nid:
            q["node_id"] = fallback_nid
        if not q.get("node_id"):
            continue
        valid.append(q)
    return valid[:shortfall]


def prepare_questions(
    kg: KnowledgeGraph, target_direction: str, known_topics: list,
    seed: int | None = None, nodes: list[dict] | None = None,
) -> tuple[list[dict], list[dict]]:
    """出题：返回 (questions, nodes)。demo 与 interactive 模式共用 (题库驱动, 赛题层次1减幻觉)。

    题库驱动: 优先从 :Question 题库抽 choice/fill 题 (Cypher 查, 快, 不调 LLM 造题), 不足 LLM 补。
    - interactive: assess 路由直接调用 (不走 LangGraph), nodes 供 submit 复用
    - demo: diagnostics_node 调用 (传已取的 nodes 避免重查), 题进工作流自动作答判分
    nodes 入参可选: 调用方已取候选节点则传入复用, 否则内部 _fetch_candidate_nodes。
    """
    if nodes is None:
        nodes = _fetch_candidate_nodes(kg, known_topics, target_direction)
    banked = _select_from_bank(kg, nodes, MAX_THEORY_QUESTIONS, seed=seed)
    shortfall = MAX_THEORY_QUESTIONS - len(banked)
    if shortfall > 0:
        if not llm_configured():
            # 题库不足且 LLM 未配置: 若题库完全空则报错, 否则用题库题数
            if not banked:
                raise ValueError("LLM 未配置且题库为空,无法出题")
        else:
            covered = {q.get("node_id") for q in banked if q.get("node_id")}
            supp = _generate_supplement(nodes, target_direction, shortfall, covered)
            banked.extend(supp)
    return banked[:MAX_THEORY_QUESTIONS], nodes


def decide_feedback(correct_count: int, total_count: int) -> dict:
    """根据答题正确率决定动态反馈策略 (对齐 orchestrator prompt 规则2)。

    纯函数:
      - 正确率 ≥ 0.8 → "advance" (进阶挑战/下一节点)
      - 0.5 ≤ 正确率 < 0.8 → "remediate" (降维解释，换角度重讲)
      - 正确率 < 0.5 → "scaffold" (补前置基础知识)
    返回 {strategy, accuracy, description}
    """
    total = total_count or 1
    accuracy = round(correct_count / total, 3)
    if accuracy >= 0.8:
        strategy = "advance"
        desc = "掌握良好，进入下一知识节点或生成进阶挑战内容"
    elif accuracy >= 0.5:
        strategy = "remediate"
        desc = "部分掌握，触发降维解释——换一个角度重新讲解同一知识点"
    else:
        strategy = "scaffold"
        desc = "掌握不足，标记当前节点为困难，自动补充前置基础知识节点"
    return {"strategy": strategy, "accuracy": accuracy, "description": desc}


def diagnostics_node(kg: KnowledgeGraph):
    """返回 LangGraph 节点函数。闭包注入 KnowledgeGraph 实例。"""

    def _node(state) -> dict:
        target = state.get("target_direction", "Python 基础入门")
        known = state.get("known_topics", [])
        mode = state.get("mode", "demo")
        log = [f"[{datetime.utcnow().isoformat()}] 🔧 学情检测: 开始 (mode={mode})"]

        # Spec B: 工作流路径从 state.llm_overrides set ContextVar（节点退出 reset）。
        # 深层 LLM helper (_demo_answer/_grade/_generate_supplement) 调 get_default_chat_model()
        # 读 _current_overrides 构造用户独立 key 的实例。
        overrides = state.get("llm_overrides")
        ctx_token = _current_overrides.set(overrides) if overrides else None
        try:
            return _node_body(state, target, known, mode, log)
        finally:
            if ctx_token is not None:
                _current_overrides.reset(ctx_token)

    def _node_body(state, target, known, mode, log) -> dict:
        if not llm_configured():
            log.append("⚠️ LLM 未配置，学情检测降级为空画像")
            logger.warning("LLM 未配置(sk-placeholder)，学情检测降级")
            return {
                "user_profile": {},
                "assessment": {},
                "orchestration_log": log,
            }

        try:
            nodes = _fetch_candidate_nodes(kg, known, target)
            log.append(f"📖 取得候选节点 {len(nodes)} 个")
            # 题库驱动出题 (赛题层次1减幻觉): 优先 :Question 题库 choice/fill, 不足 LLM 补。
            # demo 与 interactive 共用此路径 — 评委看的 demo 全流程亦走题库, 不再纯 LLM 造 judge 题。
            questions, _ = prepare_questions(kg, target, known, nodes=nodes)
            log.append(f"📝 出题 {len(questions)} 道 (题库优先)")

            # interactive 模式: 仅出题，等待前端提交答案 (POST /api/diagnostics/submit)。
            # 不在此判分/产画像，避免全错画像污染工作流。
            if mode == "interactive":
                log.append("📤 interactive 模式: 返回题目，等待前端提交答案")
                logger.info("interactive 出题完成: %d 题", len(questions))
                return {
                    "user_profile": {},
                    "assessment": {
                        "questions": questions,
                        "answers": [],
                        "per_node": {},
                        "correct_count": 0,
                        "total_count": len(questions),
                    },
                    "orchestration_log": log,
                }

            answers = _demo_answer(questions, target)
            grading = _grade(questions, answers)
            profile = _build_profile(target, nodes, grading, questions=questions)

            log.append(
                f"✅ 画像产出: theory_level={profile['theory_level']}, "
                f"known={len(profile['known_topics'])}, weak={len(profile['weak_topics'])}, "
                f"正确率={grading['correct_count']}/{grading['total_count']}"
            )
            logger.info("学情检测完成: level=%s 正确率=%d/%d",
                        profile['theory_level'], grading['correct_count'], grading['total_count'])

            return {
                "user_profile": profile,
                "assessment": {
                    "questions": questions,
                    "answers": answers,
                    "per_node": grading["per_node"],
                    "correct_count": grading["correct_count"],
                    "total_count": grading["total_count"],
                },
                "orchestration_log": log,
            }
        except Exception as e:
            logger.error("学情检测节点异常", exc_info=True)
            log.append(f"❌ 学情检测失败: {e}")
            return {
                "user_profile": {},
                "assessment": {},
                "orchestration_log": log,
            }

    return _node
