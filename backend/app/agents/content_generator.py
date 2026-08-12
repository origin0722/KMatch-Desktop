"""
领域知识生成 Agent (Content Generator Agent)

对齐 data/prompts/04_content_generator_agent.txt。

职责: 基于 graph_controller 组装的学习路径节点 + 用户画像，为每个节点生成
三种形态的个性化学习资源 (分层讲义 / 阶梯式实操指南 / 分阶测试题)，每段内容
带知识溯源标记 (source_nodes) 供 reviewer 逐条校验与 content 审核对象迁移 (BUG-016)。

第4周实现范围 (无项目场景):
  1. 取 state.knowledge_graph.learning_path 的前 N 个节点 (控量)
  2. 对每个节点调 LLM 生成3种资源，按 level 调整语言风格
  3. 每段内容标注 source_nodes (图谱节点 key_points/summary 引用)
  4. 写入 state.generated_content

阶梯式引导的5级粒度、代码题自动测试用例等 prompt 细节交 LLM，本节点负责结构化编排。
"""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.llm import _current_overrides, get_default_chat_model, llm_configured
from app.graph.engine import KnowledgeGraph
from app.utils.json_utils import parse_llm_json
from app.utils.logging import get_logger

logger = get_logger(__name__)

# 单次生成的节点数上限 (控量: 每节点3次LLM调用，避免全路径生成耗时过长)
MAX_NODES_TO_GENERATE = 3
# 每节点3种资源
CONTENT_TYPES = ("lecture", "practice_guide", "test")


def _empty_generated_content() -> dict:
    """降级时返回的结构 (字段与正常分支对齐，避免 B 端契约缺口)。"""
    return {
        "resources": [],
        "node_count": 0,
        "content_types": list(CONTENT_TYPES),
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }

# level → 适配画像标签 (对齐 prompt 04 语言风格调整)
def _adaptation_label(theory_level: int) -> str:
    if theory_level <= 2:
        return "beginner"
    if theory_level <= 4:
        return "intermediate"
    return "advanced"


def _build_generation_prompt(node: dict, theory_level: int, content_type: str) -> list:
    """构造单节点单资源类型的生成 prompt，要求 LLM 返回带溯源标记的结构化 JSON。"""
    kps = node.get("key_points", [])
    mistakes = node.get("common_mistakes", [])
    label = _adaptation_label(theory_level)

    style_hint = {
        "beginner": "面向初学者: 多用类比和生活化比喻，减少专业术语，每步详尽",
        "intermediate": "面向进阶者: 可引入底层原理和性能考量，适度精简",
        "advanced": "面向高级者: 讨论设计模式选择与工程权衡，重点突出",
    }[label]

    type_spec = {
        "lecture": (
            "生成【分层讲义】: 含标题(带难度标签)、3-5条可检验学习目标、"
            "核心概念讲解(缩进≤3层)、带注释代码示例、常见误区提醒、小节总结。"
        ),
        "practice_guide": (
            "生成【阶梯式实操指南】: 含任务目标、环境准备、步骤1-N(每步含目标/提示/检查点)、"
            "反思问题(引导思考不给答案)、扩展挑战(选做)。"
            "\n脚手架式引导(赛题启发式导学核心——引导思考而非直接给答案): "
            "在内容中给出渐进提示阶梯——第1级只给功能描述与预期输入输出; "
            "第2级补算法思路提示; 第3级给伪代码框架; 第4级给关键代码片段(含空白); "
            "第5级给完整参考代码+详细注释。学习者按需逐级揭示, 首次仅呈现第1级。"
        ),
        "test": (
            "生成【分阶测试题】: 基础题50%(直接考察key_points)+进阶题30%(综合2-3个key_points)+"
            "挑战题20%(跨知识点推理)。题型含选择题(4选项含干扰项来自common_mistakes)/填空题/代码题。"
            "代码题须同时给出测试用例。"
            "\n【答案自检--消除测试题答案幻觉】每道题的答案/预期输出在写入前必须逐步心算执行验证, "
            "重点复核以下高频易错点(历次独立裁判质检发现的真实错误): "
            "①列表方法: pop(i)删除并返回索引i的元素(非删除末尾), remove(v)删首个等于v的元素且返回None, "
            "sort()原地排序返回None(非新列表), sorted()返回新列表不改原对象; "
            "②字符串方法: find()找不到返回-1(非None/非False), join()由分隔符字符串调用(非列表调用), "
            "strip()/replace()/upper()/lower()返回新字符串不改原串(字符串不可变); "
            "③切片: s[a:b]不含索引b(右界不包含), 负索引从末尾计数。"
            "每道输出推断题/填空题答案后标注[已心算验证], 若无法确定则改出题方式避免写不确定的答案。"
        ),
    }[content_type]

    system = SystemMessage(content=(
        "你是 KMatch 领域知识生成 Agent。基于知识图谱节点事实生成个性化学习资源。"
        f"{style_hint}。"
        "\n【高保真约束——消除幻觉，赛题核心要求】"
        "\n你只能依据本节点提供的 summary/key_points/common_mistakes 生成内容。"
        "严禁补充图谱以外的实现细节、内部表示、具体数值/位数/字节宽度、版本号、"
        "性能数据、历史沿革——这些都是你的训练记忆而非图谱事实，属于必须消除的幻觉。"
        "举例只能用本节点已给信息；若某技术点节点未提供，宁可留白也不得自行补全。"
        "\n错误示范(禁):「int 内部用30位/15位数组表示」「CPython 用引用计数，对象头占28字节」"
        "——这些是图谱外实现细节，节点未提供即不得写入。"
        "\n正向要求: 每条技术断言须能在给定的 key_points/summary 中找到依据；"
        "讲解用类比、结构、示例阐释已有事实，而非编造新事实。"
        "\n严格输出 JSON 对象: "
        '{"content_type": "' + content_type + '", "target_node_id": "PY-xxx", '
        '"adaptation_profile": "beginner|intermediate|advanced", '
        '"source_nodes": ["PY-xxx.key_points[0]", "PY-xxx.summary", ...], '
        '"content": "markdown格式正文"}。'
        "\n注意: difficulty_level 由系统按知识点难度统一赋值, 你不要输出该字段。"
        "不要输出 JSON 以外文字。"
    ))
    user = HumanMessage(content=(
        f"知识图谱节点:\n"
        f"- node_id: {node['node_id']}\n"
        f"- 名称: {node.get('name','')}\n"
        f"- 难度: {node.get('difficulty',1)}\n"
        f"- summary: {node.get('summary','')}\n"
        f"- key_points: {json.dumps(kps, ensure_ascii=False)}\n"
        f"- common_mistakes: {json.dumps(mistakes, ensure_ascii=False)}\n\n"
        f"{type_spec}"
    ))
    return [system, user]


def _generate_one(node: dict, theory_level: int, content_type: str) -> dict:
    """调 LLM 为单节点生成单类型资源，返回带溯源标记的内容 dict。"""
    model = get_default_chat_model()
    resp = model.invoke(_build_generation_prompt(node, theory_level, content_type))
    data = parse_llm_json(resp.content)
    # BUG-041: LLM 偶发返回数组而非对象 (把多资源放数组)。
    # 取首个 dict 元素; 无可用 dict → 降级空资源 (不抛异常, 避免 _safe_generate 计失败拖累整体)
    if isinstance(data, list):
        data = next((x for x in data if isinstance(x, dict)), None)
    if not isinstance(data, dict):
        logger.warning("生成响应非对象 node=%s type=%s, 降级空资源",
                       node.get("node_id"), type(data))
        data = {}
    # 兜底: 补全必要字段
    data.setdefault("content_type", content_type)
    data.setdefault("target_node_id", node.get("node_id"))
    # 难度由系统按知识点难度统一赋值 (M5 适配率: 资源难度须对齐节点难度, gap=0)。
    # 强制覆盖 LLM 自填值 — 难度是图谱事实, 非 LLM 臆造 (对齐"组装而非生成"理念)。
    node_diff = node.get("difficulty", 1)
    data["difficulty_level"] = node_diff if isinstance(node_diff, (int, float)) else 1
    data.setdefault("adaptation_profile", _adaptation_label(theory_level))
    if not isinstance(data.get("source_nodes"), list):
        data["source_nodes"] = [f"{node['node_id']}.summary"]
    data.setdefault("content", "")
    data["generated_at"] = datetime.utcnow().isoformat() + "Z"
    return data


def content_generator_node(kg: KnowledgeGraph):
    """返回 LangGraph 节点函数。闭包注入 KnowledgeGraph 实例。"""

    def _node(state) -> dict:
        profile = state.get("user_profile", {})
        kg_state = state.get("knowledge_graph", {}) or {}
        log = [f"[{datetime.utcnow().isoformat()}] 📚 领域知识生成: 开始"]

        # Spec B: 工作流路径 set ContextVar；content_generator 的 ThreadPoolExecutor
        # 工作线程不继承 ContextVar，_safe_generate 内闭包捕获 overrides 重新 set。
        overrides = state.get("llm_overrides")
        ctx_token = _current_overrides.set(overrides) if overrides else None
        try:
            return _node_body(state, profile, kg_state, log, overrides)
        finally:
            if ctx_token is not None:
                _current_overrides.reset(ctx_token)

    def _node_body(state, profile, kg_state, log, overrides) -> dict:
        # 无学习路径 (图谱未组装/降级) → 跳过生成 (字段结构与正常分支对齐)
        # 仍标记 content_phase_entered=True: 防止 reviewer 回退画像模式 (BUG-031)
        learning_path = kg_state.get("learning_path", [])
        if not learning_path:
            log.append("⚠️ 学习路径为空，跳过内容生成")
            return {
                "generated_content": _empty_generated_content(),
                "content_phase_entered": True,
                "orchestration_log": log,
            }

        # LLM 未配置 → 降级: 不生成 (reviewer 会判不通过触发降级)
        if not llm_configured():
            log.append("⚠️ LLM 未配置，内容生成降级为空资源")
            logger.warning("LLM 未配置(sk-placeholder)，内容生成降级")
            return {
                "generated_content": _empty_generated_content(),
                "content_phase_entered": True,
                "orchestration_log": log,
            }

        theory_level = profile.get("theory_level", 2) or 2
        target_nodes = learning_path[:MAX_NODES_TO_GENERATE]
        log.append(f"📖 为 {len(target_nodes)} 个节点生成资源 (每节点3种, level={theory_level})")

        # 并行生成: _generate_one 是无共享状态的纯调用 (LangChain ChatModel 线程安全，
        # 内部 httpx 连接池)，9 次独立 LLM 调用可并发。
        # 按原 (node, ctype) 顺序提交并聚合结果，保持 resources 顺序稳定 (B 端虽不依赖顺序，
        # 但稳定顺序便于调试与回归比对)。
        tasks = [(node, ctype) for node in target_nodes for ctype in CONTENT_TYPES]

        def _safe_generate(node, ctype):
            """单任务包装: 返回 (ok, result_or_None)。异常不外抛，避免 ThreadPool 终止其他任务。

            Spec B: ContextVar 不跨线程传播；工作线程内闭包捕获 overrides 重新 set，
            使 _generate_one → get_default_chat_model() 读到 overrides。
            """
            wtoken = _current_overrides.set(overrides) if overrides else None
            try:
                return True, _generate_one(node, theory_level, ctype)
            except Exception:
                logger.warning("生成失败 node=%s type=%s",
                               node.get("node_id"), ctype, exc_info=True)
                return False, None
            finally:
                if wtoken is not None:
                    _current_overrides.reset(wtoken)

        resources = []
        failures = 0
        # 并发度: 可配 (CONTENT_GEN_CONCURRENCY), 默认 5。
        # 实测 (DeepSeek V4 Pro API, 9 次生成): 并发5 内容生成 137s, 并发3 反而 190s。
        # 降并发未能减少 429 退避 (DeepSeek 对并发5 限流不严重), 却多了轮次 (2轮 vs 3轮) 更慢。
        # 故默认 5; 仅在确认重度限流时调低, 或换更快模型/减资源数 (减 LLM 调用) 才能真降耗时。
        import os
        _concurrency = int(os.environ.get("CONTENT_GEN_CONCURRENCY", "5"))
        max_workers = min(_concurrency, len(tasks)) if tasks else 1
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            results = list(pool.map(lambda args: _safe_generate(*args), tasks))

        for ok, res in results:
            if ok and res is not None:
                resources.append(res)
            else:
                failures += 1

        log.append(
            f"✅ 生成完成: {len(resources)} 段资源"
            + (f"，{failures} 段失败" if failures else "")
        )
        logger.info("内容生成: resources=%d failures=%d (并发=%d)",
                    len(resources), failures, max_workers)

        return {
            "generated_content": {
                "resources": resources,
                "node_count": len(target_nodes),
                "content_types": list(CONTENT_TYPES),
                "generated_at": datetime.utcnow().isoformat() + "Z",
            },
            "content_phase_entered": True,
            "orchestration_log": log,
        }

    return _node


# ============================================================
# W5 动态反馈闭环: 按 feedback.strategy 针对性再生内容
# ============================================================

# strategy → (内容类型, 节点选择策略, 生成提示)
FEEDBACK_STRATEGY_SPEC = {
    "remediate": {
        "content_type": "lecture",
        "node_source": "weak",  # 对弱项节点重讲
        "hint": "降维解释: 换一个角度、多用类比和生活化比喻重新讲解同一知识点，"
                "避免与之前讲解雷同，重点化解典型误解。",
    },
    "scaffold": {
        "content_type": "lecture",
        "node_source": "prereq",  # 补弱项的前置基础节点
        "hint": "补前置基础: 针对该节点的前置依赖节点生成入门讲义，夯实基础后再回看原节点。",
    },
    "advance": {
        "content_type": "test",
        "node_source": "next",  # 路径下一节点的进阶挑战题
        "hint": "进阶挑战: 生成跨知识点、需要额外推理的挑战题，附带测试用例。",
    },
}


def select_feedback_nodes(
    strategy: str,
    weak_topics: list[dict],
    learning_path: list[dict],
    kg: KnowledgeGraph = None,
) -> list[dict]:
    """根据 strategy 选择再生内容的目标节点 (纯函数, kg 仅 scaffold 取前置时用)。

    - remediate: 弱项节点本身 (最多2个)
    - scaffold:  弱项节点的前置依赖节点 (去重, 最多2个)
    - advance:   学习路径中弱项之后的下一节点 (最多1个)
    返回节点对象列表 (含 node_id/name/difficulty 等)。
    """
    spec = FEEDBACK_STRATEGY_SPEC.get(strategy)
    if spec is None:
        return []

    weak_ids = [t["node_id"] for t in weak_topics if isinstance(t, dict) and t.get("node_id")]

    if spec["node_source"] == "weak":
        # 弱项节点本身: 从 learning_path 中取 (含完整字段)
        path_by_id = {n["node_id"]: n for n in learning_path if isinstance(n, dict) and n.get("node_id")}
        return [path_by_id[wid] for wid in weak_ids[:2] if wid in path_by_id]

    if spec["node_source"] == "prereq":
        if kg is None:
            return []
        seen = set()
        result = []
        for wid in weak_ids[:3]:
            for pr in kg.get_prerequisites(wid):
                nid = pr.get("node_id")
                if nid and nid not in seen:
                    seen.add(nid)
                    result.append(pr)
                if len(result) >= 2:
                    break
            if len(result) >= 2:
                break
        return result

    if spec["node_source"] == "next":
        # 路径中弱项之后的下一节点 (统一用过滤后的 dict 列表，避免索引错位)
        dict_path = [n for n in learning_path if isinstance(n, dict)]
        path_ids = [n.get("node_id") for n in dict_path]
        for wid in weak_ids:
            if wid in path_ids:
                idx = path_ids.index(wid)
                if idx + 1 < len(dict_path):
                    return [dict_path[idx + 1]]
        return []

    return []


def regenerate_for_feedback(
    strategy: str,
    profile: dict,
    learning_path: list[dict],
    kg: KnowledgeGraph,
) -> dict:
    """按动态反馈策略针对性再生学习内容 (W4 计划⑤闭环)。

    返回 {strategy, resources, node_count, generated_at}。
    LLM 未配置/无目标节点 → 空 resources (不抛)。
    """
    log_hint = FEEDBACK_STRATEGY_SPEC.get(strategy, {}).get("hint", "")
    if not llm_configured():
        logger.warning("LLM 未配置，feedback 再生降级为空")
        return _empty_feedback_result(strategy)

    weak_topics = profile.get("weak_topics", [])
    target_nodes = select_feedback_nodes(strategy, weak_topics, learning_path, kg)

    if not target_nodes:
        logger.info("feedback 再生: strategy=%s 无目标节点 (weak=%d)", strategy, len(weak_topics))
        return _empty_feedback_result(strategy)

    theory_level = profile.get("theory_level", 2) or 2
    content_type = FEEDBACK_STRATEGY_SPEC[strategy]["content_type"]
    resources = []
    for node in target_nodes:
        try:
            res = _generate_feedback_one(node, theory_level, content_type, log_hint)
            resources.append(res)
        except Exception:
            logger.warning("feedback 再生失败 node=%s", node.get("node_id"), exc_info=True)

    logger.info("feedback 再生: strategy=%s resources=%d", strategy, len(resources))
    return {
        "strategy": strategy,
        "resources": resources,
        "node_count": len(target_nodes),
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


def _empty_feedback_result(strategy: str) -> dict:
    return {
        "strategy": strategy,
        "resources": [],
        "node_count": 0,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


def _generate_feedback_one(node: dict, theory_level: int, content_type: str, hint: str) -> dict:
    """按 feedback hint 生成单段针对性内容 (复用 _generate_one 的字段补全逻辑)。"""
    model = get_default_chat_model()
    kps = node.get("key_points", [])
    label = _adaptation_label(theory_level)

    type_spec = {
        "lecture": "生成【降维/补基础讲义】" if content_type == "lecture" else "",
        "test": (
            "生成【进阶挑战题】含跨知识点推理题 + 测试用例。"
            "\n【答案自检--消除答案幻觉】每道题答案/预期输出写入前须逐步心算执行验证, "
            "重点复核: pop(i)删索引i元素/ remove/sort返回None/ sorted返回新列表; "
            "find返回-1非None/ join由分隔符串调用/ 字符串方法返回新串不改原; "
            "切片 s[a:b] 不含 b。无法确定则改出题方式。"
        ),
    }.get(content_type, "")

    system = SystemMessage(content=(
        "你是 KMatch 领域知识生成 Agent，按动态反馈策略针对性再生学习内容。"
        f"{_adaptation_style(label)}。"
        f"特别要求: {hint}。"
        "\n【高保真约束——消除幻觉】只能依据本节点 summary/key_points/common_mistakes "
        "生成内容，严禁补充图谱外的实现细节/内部表示/具体数值/版本号/性能数据"
        "(训练记忆非图谱事实)。每条断言须能在节点信息中找到依据，未提供者留白不补全。"
        "严格输出 JSON 对象: "
        '{"content_type": "' + content_type + '", "target_node_id": "PY-xxx", '
        '"adaptation_profile": "beginner|intermediate|advanced", '
        '"source_nodes": ["PY-xxx.key_points[0]", "PY-xxx.summary"], '
        '"content": "markdown格式正文"}。'
        "\n注意: difficulty_level 由系统按知识点难度统一赋值, 你不要输出该字段。"
        "不要输出 JSON 以外文字。"
    ))
    user = HumanMessage(content=(
        f"知识图谱节点:\n"
        f"- node_id: {node['node_id']}\n- 名称: {node.get('name','')}\n"
        f"- 难度: {node.get('difficulty',1)}\n- summary: {node.get('summary','')}\n"
        f"- key_points: {json.dumps(kps, ensure_ascii=False)}\n\n{type_spec}"
    ))
    resp = model.invoke([system, user])
    data = parse_llm_json(resp.content)
    if not isinstance(data, dict):
        raise ValueError(f"feedback 生成响应非对象: {type(data)}")
    data.setdefault("content_type", content_type)
    data.setdefault("target_node_id", node.get("node_id"))
    # 难度由系统按知识点难度统一赋值 (BUG-043 一致性: 反馈再生路径同样强制, 避免 LLM 自填漂移)
    node_diff = node.get("difficulty", 1)
    data["difficulty_level"] = node_diff if isinstance(node_diff, (int, float)) else 1
    data.setdefault("adaptation_profile", label)
    if not isinstance(data.get("source_nodes"), list):
        data["source_nodes"] = [f"{node['node_id']}.summary"]
    data.setdefault("content", "")
    data["generated_at"] = datetime.utcnow().isoformat() + "Z"
    return data


def _adaptation_style(label: str) -> str:
    """label → 语言风格提示 (复用 _build_generation_prompt 的风格表)。"""
    return {
        "beginner": "面向初学者: 多用类比和生活化比喻，减少专业术语",
        "intermediate": "面向进阶者: 可引入底层原理和性能考量",
        "advanced": "面向高级者: 讨论设计模式选择与工程权衡",
    }.get(label, "")
