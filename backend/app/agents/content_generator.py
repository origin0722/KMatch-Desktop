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

from app.agents.llm import _current_overrides, get_default_chat_model, llm_configured, safe_llm_call, with_state_overrides
from app.graph.engine import KnowledgeGraph
from app.config import settings
from app.utils.json_utils import parse_llm_json
from app.utils.logging import get_logger

logger = get_logger(__name__)

# 单次生成的节点数上限 (控量: 每节点3次LLM调用；5 节点=15 次调用, 并发5 下 wall-clock 仍 ≈ 单节点耗时)
MAX_NODES_TO_GENERATE = 5
# 每节点3种资源
CONTENT_TYPES = ("lecture", "practice_guide", "test")


def _failure_record(node: dict, content_type, reason: str) -> dict:
    """单条生成失败记录 (B 端透出, 治"失败静默为空")。"""
    return {"node_id": (node or {}).get("node_id"), "content_type": content_type, "reason": reason}


def _empty_generated_content(reason: str = None) -> dict:
    """降级时返回的结构 (字段与正常分支对齐，避免 B 端契约缺口)。

    reason 非空时写入 generation_failures, 让前端能区分"路径为空/LLM 未配置"而非空白。
    """
    return {
        "resources": [],
        "node_count": 0,
        "content_types": list(CONTENT_TYPES),
        "generation_failures": [_failure_record({}, None, reason)] if reason else [],
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }

# level → 适配画像标签 (对齐 prompt 04 语言风格调整)
def _adaptation_label(theory_level: int) -> str:
    if theory_level <= 2:
        return "beginner"
    if theory_level <= 4:
        return "intermediate"
    return "advanced"


# VARK 学习风格 → 表达方式偏好 (赛题"对不同背景学习者适配"; W5 采集建模后接入生成)
_STYLE_HINT_BY_LEARNING_STYLE = {
    "visual": "学习者偏好视觉型输入——优先图示化描述、Markdown 表格对比、流程步骤化呈现",
    "auditory": "学习者偏好听觉型输入——口语化行文、多用比喻, 像「有人在旁边讲给你听」",
    "read_write": "学习者偏好读写型输入——要点式陈述、关键术语加粗标注、附笔记整理建议",
    "kinesthetic": "学习者偏好动手型输入——优先给可运行代码片段与练习, 边做边学, 压缩纯理论铺陈",
}

# 学历/专业背景 → 讲解深度与用语 (赛题(2) 先验画像 demographics 可选采集)
_EDU_HINT_NON_TECH = "学习者偏非科班/低年级背景——避免未解释的科班术语, 类比尽量取自日常生活场景"
_EDU_HINT_CS = "学习者有计算机相关专业背景——可直接使用科班术语, 侧重底层原理与工程实践"


def _background_style_hint(profile: dict) -> str:
    """画像背景 (VARK 学习风格 + 学历/专业) → 追加风格提示串 (无适配信息时为空串)。

    VARK 仅在实测时接入 (style_source=default 为占位, 不据占位调整); 学历/专业为
    启发式判断: 高中及以下/非科班自学者或专业名不含计算机相关词 → 非科班提示。
    """
    if not isinstance(profile, dict):
        return ""
    parts = []
    if profile.get("style_source") == "quiz":
        hint = _STYLE_HINT_BY_LEARNING_STYLE.get(profile.get("learning_style"))
        if hint:
            parts.append(hint)
    demo = profile.get("demographics") or {}
    if isinstance(demo, dict):
        edu = str(demo.get("education") or "")
        major = str(demo.get("major") or "")
        if edu or major:
            cs_like = any(k in major for k in ("计算机", "软件", "信息", "人工智能", "数据", "电子")) or "博士" in edu or "硕士" in edu
            parts.append(_EDU_HINT_CS if cs_like else _EDU_HINT_NON_TECH)
    return ("；" + "；".join(parts)) if parts else ""


def _build_generation_prompt(node: dict, theory_level: int, content_type: str, correction_hint: str = "", style_extra: str = "") -> list:
    """构造单节点单资源类型的生成 prompt，要求 LLM 返回带溯源标记的结构化 JSON。

    correction_hint 非空时注入"上轮判定修正要求" (reviewer retry_hint / 独立裁判 reason)，
    使重试从盲重跑变为携带诊断的定向再生。
    style_extra: 背景适配追加提示 (VARK 学习风格 + 学历/专业, _background_style_hint 产出)。
    """
    kps = node.get("key_points", [])
    mistakes = node.get("common_mistakes", [])
    label = _adaptation_label(theory_level)

    style_hint = {
        "beginner": "面向初学者: 多用类比和生活化比喻，减少专业术语，每步详尽",
        "intermediate": "面向进阶者: 可引入底层原理和性能考量，适度精简",
        "advanced": "面向高级者: 讨论设计模式选择与工程权衡，重点突出",
    }[label] + style_extra

    type_spec = {
        "lecture": (
            "生成【分层讲义】: 含标题(带难度标签)、3-5条可检验学习目标、"
            "核心概念讲解(缩进≤3层)、带注释代码示例、常见误区提醒、小节总结。"
            "\n【内容丰富度要求(只用节点已有事实, 禁编造新事实)】"
            "①覆盖全部key_points, 每条至少独立展开; "
            "②难度≥3且key_points含可比概念时, 用Markdown表格对比(≥3行); "
            "③每条key_point配一个边界/反例(优先取自common_mistakes); "
            "④开头1-2句衔接prerequisites(已提供), 无前置则点明基础地位; "
            "⑤难度≥4增设「工程权衡」小节(只用已有信息, 不编造数值/版本号); "
            "⑥每条common_mistakes展开为「错误做法->正确做法」对照。"
            "信息不足以支撑某条则该条可缺省, 但不得编造填充。"
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

    # 定向再生修正块 (非空 = 上轮 reviewer retry_hint / 独立裁判 reason 注入)
    correction_block = (
        f"\n\n【上轮判定修正要求——定向再生】\n{correction_hint}\n"
        "重点修正上述问题 (以图谱事实为准), 其余结构保持原样; 无法依据节点事实修正的部分宁可删去。"
        "\n【申诉举证 (rebuttal)——生成↔审核辩论机制】对上轮判定你有不同意见的条目, "
        "必须在输出 JSON 增加 rebuttal 数组逐条申诉: "
        '{"issue": "被指摘问题(概括)", "response": "你的回应——已如何依据节点事实修正, '
        '或举证原内容有据", "evidence": ["PY-xxx.key_points[0]"]}；'
        "evidence 必须是节点内真实引用 (会经审核 Agent 复审裁定采纳与否); 无不同意见则输出空数组。"
        if correction_hint else ""
    )

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
        "\n【先锚定后展开——防结论先行合理化】"
        "\n资源的第一小节 (讲义) / 任务目标 (实操) / 首个考察点 (测试题) 必须先用 1-3 句"
        "复述节点 summary/key_points 已给事实 (不加新信息) 作为锚定; 随后的展开只能"
        "阐释已锚定的事实; 结论不得先于其图谱依据出现 (先有桥再有结论)。"
        + correction_block
        + "\n【认识状态自声明 (unverified_claims)】"
        "\n类比、背景性铺垫等图谱事实之外的陈述是允许的, 但必须如实浮出: 在输出的"
        " unverified_claims 数组里逐条列出这些陈述 (每条一句话)。完全只用节点事实时输出空数组。"
        "自声明用于独立裁判定向审计, 不是禁止——未声明比声明更严重 (隐性不可控)。"
        "\n【内容丰富度】讲义须在只用节点已有事实前提下充分展开: 逐条覆盖key_points、"
        "配边界反例、衔接前置知识(prerequisites)、误区全转化为对照(详见type_spec)。"
        "\n严格输出 JSON 对象: "
        '{"content_type": "' + content_type + '", "target_node_id": "PY-xxx", '
        '"adaptation_profile": "beginner|intermediate|advanced", '
        '"source_nodes": ["PY-xxx.key_points[0]", "PY-xxx.summary", ...], '
        '"unverified_claims": ["图谱事实之外的陈述, 每条一句; 完全锚定为空数组"], '
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
        f"- common_mistakes: {json.dumps(mistakes, ensure_ascii=False)}\n"
        f"- prerequisites: {json.dumps(node.get('prerequisites', []), ensure_ascii=False)}\n\n"
        f"{type_spec}"
    ))
    return [system, user]


def _finalize_resource(data: dict, node: dict, content_type: str, adaptation_label: str) -> dict:
    """LLM 输出 → 资源契约的统一兜底 (_generate_one 与 _generate_feedback_one 共用)。

    - 难度由系统按知识点难度统一赋值 (BUG-043: 资源难度对齐节点难度, 强制覆盖 LLM 自填值)
    - content_type 由调用方指定, 强制覆盖 LLM 自填值 (防模型回错类型导致 tab 分类错位:
      practice_guide/test 被 LLM 写成 lecture 等)
    - source_nodes 非法时回退节点 summary 引用
    - unverified_claims (认识状态自声明): 非 list 强转空 (缺失视为完全锚定, 由裁判复核)
    """
    data["content_type"] = content_type
    data.setdefault("target_node_id", node.get("node_id"))
    node_diff = node.get("difficulty", 1)
    data["difficulty_level"] = node_diff if isinstance(node_diff, (int, float)) else 1
    data.setdefault("adaptation_profile", adaptation_label)
    if not isinstance(data.get("source_nodes"), list):
        data["source_nodes"] = [f"{node['node_id']}.summary"]
    ucs = data.get("unverified_claims")
    data["unverified_claims"] = [str(c) for c in ucs if c] if isinstance(ucs, list) else []
    # 申诉举证 (赛题(4)① 生成↔审核辩论): 仅定向再生带 correction_hint 时 LLM 输出, 归一化结构
    rb = data.get("rebuttal")
    data["rebuttal"] = [
        {
            "issue": str(r.get("issue", "")),
            "response": str(r.get("response", "")),
            "evidence": [str(e) for e in (r.get("evidence") or []) if e],
        }
        for r in rb if isinstance(r, dict)
    ] if isinstance(rb, list) else []
    data.setdefault("content", "")
    data["generated_at"] = datetime.utcnow().isoformat() + "Z"
    return data


def _generate_one(node: dict, theory_level: int, content_type: str, correction_hint: str = "", style_extra: str = "") -> dict:
    """调 LLM 为单节点生成单类型资源，返回带溯源标记的内容 dict。

    correction_hint: 上轮 reviewer retry_hint / 独立裁判 reason (定向再生时非空)。
    style_extra: 背景适配追加提示 (VARK 学习风格 + 学历/专业)。
    """
    model = get_default_chat_model()
    resp = model.invoke(_build_generation_prompt(node, theory_level, content_type, correction_hint, style_extra))
    data = parse_llm_json(resp.content)
    # BUG-041: LLM 偶发返回数组而非对象 (把多资源放数组) → 取首个 dict 元素。
    # 无可用 dict → 抛 ValueError 计入 generation_failures (原先降级空资源卡片,
    # B 端只见空白讲义不知原因; 现与 _generate_feedback_one 对齐改为显式失败上浮)。
    if isinstance(data, list):
        data = next((x for x in data if isinstance(x, dict)), None)
    if not isinstance(data, dict):
        logger.warning("生成响应非对象 node=%s type=%s",
                       node.get("node_id"), type(data))
        raise ValueError(f"LLM 响应非 JSON 对象 (type={type(data).__name__})")
    return _finalize_resource(data, node, content_type, _adaptation_label(theory_level))


def content_generator_node(kg: KnowledgeGraph):
    """返回 LangGraph 节点函数。闭包注入 KnowledgeGraph 实例。"""

    @with_state_overrides
    def _node(state) -> dict:
        profile = state.get("user_profile", {})
        kg_state = state.get("knowledge_graph", {}) or {}
        log = [f"[{datetime.utcnow().isoformat()}] 📚 领域知识生成: 开始"]

        return _node_body(state, profile, kg_state, log)

    def _node_body(state, profile, kg_state, log) -> dict:
        # 无学习路径 (图谱未组装/降级) → 跳过生成 (字段结构与正常分支对齐)
        # 仍标记 content_phase_entered=True: 防止 reviewer 回退画像模式 (BUG-031)
        learning_path = kg_state.get("learning_path", [])
        if not learning_path:
            log.append("⚠️ 学习路径为空，跳过内容生成")
            return {
                "generated_content": _empty_generated_content("学习路径为空（图谱未组装或降级），无法生成资源"),
                "content_phase_entered": True,
                "orchestration_log": log,
            }

        # LLM 未配置 → 降级: 不生成 (reviewer 会判不通过触发降级)
        if not llm_configured():
            log.append("⚠️ LLM 未配置，内容生成降级为空资源")
            logger.warning("LLM 未配置(sk-placeholder)，内容生成降级")
            return {
                "generated_content": _empty_generated_content("LLM 未配置（API Key 缺失或为占位符），请在设置页或 .env 配置"),
                "content_phase_entered": True,
                "orchestration_log": log,
            }

        # 定向重试: 内容阶段被 reviewer 打回时, 注入其 retry_hint (诊断携带再生, 取代盲重跑)。
        # 首轮 content_phase_entered 为 False → 不注入 (此时 review_results 是画像阶段结论, 语义不符)。
        retry_hint = ""
        if state.get("content_phase_entered") and isinstance(state.get("review_results"), dict):
            retry_hint = (state["review_results"].get("retry_hint") or "").strip()
            if retry_hint:
                log.append(f"🔁 携带审核诊断定向再生: {retry_hint[:80]}")

        theory_level = profile.get("theory_level", 2) or 2
        style_extra = _background_style_hint(profile)  # 赛题背景适配: VARK 风格 + 学历/专业
        target_nodes = learning_path[:MAX_NODES_TO_GENERATE]
        log.append(f"📖 为 {len(target_nodes)} 个节点生成资源 (每节点3种, level={theory_level})")

        # 并行生成: _generate_one 是无共享状态的纯调用 (LangChain ChatModel 线程安全，
        # 内部 httpx 连接池)，9 次独立 LLM 调用可并发。
        # 按原 (node, ctype) 顺序提交并聚合结果，保持 resources 顺序稳定 (B 端虽不依赖顺序，
        # 但稳定顺序便于调试与回归比对)。
        tasks = [(node, ctype) for node in target_nodes for ctype in CONTENT_TYPES]

        # Spec B: ContextVar 不跨线程传播；safe_llm_call 在 worker 内重设 overrides。
        overrides = _current_overrides.get()

        resources = []
        generation_failures = []
        # 并发度: 可配 (CONTENT_GEN_CONCURRENCY), 默认 5; max(1,...) 防配置为 0 崩溃。
        # 实测 (DeepSeek V4 Pro API, 9 次生成): 并发5 内容生成 137s, 并发3 反而 190s。
        # 降并发未能减少 429 退避 (DeepSeek 对并发5 限流不严重), 却多了轮次 (2轮 vs 3轮) 更慢。
        # 故默认 5; 仅在确认重度限流时调低, 或换更快模型/减资源数 (减 LLM 调用) 才能真降耗时。
        max_workers = max(1, min(settings.CONTENT_GEN_CONCURRENCY, len(tasks)))
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            results = list(pool.map(
                lambda args: safe_llm_call(
                    _generate_one, args[0], theory_level, args[1], retry_hint, style_extra,
                    overrides=overrides, logger=logger,
                    label=f"node={args[0].get('node_id')} type={args[1]}"),
                tasks,
            ))

        for (node, ctype), (ok, res) in zip(tasks, results):
            if ok and res is not None and str(res.get("content") or "").strip():
                resources.append(res)
            elif ok:
                generation_failures.append(_failure_record(node, ctype, "生成内容为空（模型未返回正文）"))
            else:
                generation_failures.append(_failure_record(node, ctype, "LLM 调用失败（网络/限流/响应格式）"))

        if generation_failures:
            log.append(f"⚠️ {len(generation_failures)} 段生成失败 (详见 generation_failures)")
        log.append(f"✅ 生成完成: {len(resources)} 段资源")
        logger.info("内容生成: resources=%d failures=%d (并发=%d)",
                    len(resources), len(generation_failures), max_workers)

        return {
            "generated_content": {
                "resources": resources,
                "node_count": len(target_nodes),
                "content_types": list(CONTENT_TYPES),
                "generation_failures": generation_failures,
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

    - remediate: 弱项节点本身 (1 个)
    - scaffold:  弱项节点的前置依赖节点 (1 个)
    - advance:   学习路径中弱项之后的下一节点 (1 个)
    返回节点对象列表 (含 node_id/name/difficulty 等)。

    每策略 1 节点: 反馈是交互式按需触发, 用户等待敏感; 单节点 LLM 调用 ≈30s,
    多节点并发不降 wall-clock(瓶颈在单次生成), 徒增成本与超时风险。
    """
    spec = FEEDBACK_STRATEGY_SPEC.get(strategy)
    if spec is None:
        return []

    weak_ids = [t["node_id"] for t in weak_topics if isinstance(t, dict) and t.get("node_id")]

    if spec["node_source"] == "weak":
        # 弱项节点本身: 从 learning_path 中取 (含完整字段)
        path_by_id = {n["node_id"]: n for n in learning_path if isinstance(n, dict) and n.get("node_id")}
        return [path_by_id[wid] for wid in weak_ids[:1] if wid in path_by_id]

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
                if len(result) >= 1:
                    break
            if len(result) >= 1:
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
        return _empty_feedback_result(strategy, "LLM 未配置（API Key 缺失或为占位符）")

    weak_topics = profile.get("weak_topics", [])
    target_nodes = select_feedback_nodes(strategy, weak_topics, learning_path, kg)

    if not target_nodes:
        logger.info("feedback 再生: strategy=%s 无目标节点 (weak=%d)", strategy, len(weak_topics))
        return _empty_feedback_result(
            strategy,
            f"策略 {strategy} 无目标节点（弱项不在当前学习路径中或无前置依赖）",
        )

    theory_level = profile.get("theory_level", 2) or 2
    style_extra = _background_style_hint(profile)  # 赛题背景适配: VARK 风格 + 学历/专业
    # 全类型生成: 每个目标节点都产 lecture + practice_guide + test,
    # 保证"针对性反馈"后学习资源四 tab (讲义/实操/测试) 都有内容, 不随策略单类型缺失。
    resources = []
    generation_failures = []
    overrides = _current_overrides.get()  # Spec B: 捕获主线程 override, worker 内重设 (ContextVar 不跨线程)

    # 任务 = 目标节点 × 三种内容类型 (通常 1-2 节点 × 3 = 3-6 次 LLM 调用)
    tasks = [(node, ctype) for node in target_nodes for ctype in CONTENT_TYPES]
    # 并行生成: 全部任务并发 (wall-clock ≈ 单次调用, 而非 N×串行)。
    # _generate_feedback_one 是无共享状态的纯 LLM 调用 (LangChain ChatModel 线程安全)。
    with ThreadPoolExecutor(max_workers=min(len(tasks), 6)) as pool:
        results = list(pool.map(
            lambda task: safe_llm_call(
                _generate_feedback_one, task[0], theory_level, task[1], log_hint, style_extra,
                overrides=overrides, logger=logger,
                label=f"feedback node={task[0].get('node_id')} {task[1]}"),
            tasks,
        ))

    for (node, ctype), (ok, res) in zip(tasks, results):
        if ok and res is not None and str(res.get("content") or "").strip():
            resources.append(res)
        elif ok:
            generation_failures.append(_failure_record(node, ctype, "生成内容为空（模型未返回正文）"))
        else:
            generation_failures.append(_failure_record(node, ctype, "LLM 调用失败（网络/限流/响应格式）"))

    logger.info("feedback 再生: strategy=%s resources=%d failures=%d",
                strategy, len(resources), len(generation_failures))
    return {
        "strategy": strategy,
        "resources": resources,
        "node_count": len(target_nodes),
        "generation_failures": generation_failures,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


def _empty_feedback_result(strategy: str, reason: str = None) -> dict:
    return {
        "strategy": strategy,
        "resources": [],
        "node_count": 0,
        "generation_failures": [{"node_id": None, "content_type": None, "reason": reason}] if reason else [],
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


def _generate_feedback_one(node: dict, theory_level: int, content_type: str, hint: str, style_extra: str = "") -> dict:
    """按 feedback hint 生成单段针对性内容 (复用 _generate_one 的字段补全逻辑)。"""
    model = get_default_chat_model()
    kps = node.get("key_points", [])
    label = _adaptation_label(theory_level)

    type_spec = {
        "lecture": (
            "生成【分层讲义】(issue-67 专业性升级): 正文 500–800 字。结构: "
            "①标题(带难度标签) ②3-5 条可检验学习目标 ③核心概念讲解: 覆盖该节点 >=3 个 key_points, "
            "每个独立展开, 含至少 1 个带注释的代码/结构示例 ④常见误区: 每条 common_mistake 做"
            "「错误做法 → 正确做法」对照 ⑤小节总结 + 1 个自检问题。难度>=3 时用 Markdown 表格对比 >=3 行。"
            "只用节点已有事实充分展开, 禁编造新事实/数值/版本号 (高保真约束见 system)。"
        ),
        "practice_guide": (
            "生成【阶梯式实操指南】(issue-67 专业性升级): 含任务目标、环境准备、步骤 1-N(每步含目标/提示/检查点)、"
            "反思问题(引导思考不给答案)、扩展挑战(选做)。"
            "脚手架式引导: 第 1 级只给功能描述与预期输入输出; 第 2 级补算法思路提示; "
            "第 3 级给伪代码框架; 第 4 级给关键代码片段(含空白); 第 5 级给完整参考代码+详细注释。"
            "目标/步骤须具体可执行(含输入输出示例), 正文 400–700 字; 只用节点已有事实, 禁编造。"
        ),
        "test": (
            "生成【分阶测试题】(issue-67 专业性升级): 共 3 道 (基础 1 + 进阶 1 + 挑战 1), "
            "题型覆盖选择题(4 选项, 干扰项来自 common_mistakes)/填空题/代码题(代码题附测试用例)。"
            "每道题格式: **题目**、选项(若有)、**答案**、**解析**(一句到位, 说明为什么/错在哪)。"
            "挑战题须跨 2-3 个 key_points 推理。"
            "【答案自检--消除测试题答案幻觉】每道题答案/预期输出在写入前必须逐步心算验证; "
            "无法确定的答案宁可改题, 不得编造。总字数 300–600 字, 只用节点已有事实, 禁编造。"
        ),
    }.get(content_type, "")

    system = SystemMessage(content=(
        "你是 KMatch 领域知识生成 Agent，按动态反馈策略针对性再生学习内容。"
        f"{_adaptation_style(label)}{style_extra}。"
        f"特别要求: {hint}。"
        "\n【高保真约束——消除幻觉】只能依据本节点 summary/key_points/common_mistakes "
        "生成内容，严禁补充图谱外的实现细节/内部表示/具体数值/版本号/性能数据"
        "(训练记忆非图谱事实)。每条断言须能在节点信息中找到依据，未提供者留白不补全。"
        "严格输出 JSON 对象: "
        '{"content_type": "' + content_type + '", "target_node_id": "PY-xxx", '
        '"adaptation_profile": "beginner|intermediate|advanced", '
        '"source_nodes": ["PY-xxx.key_points[0]", "PY-xxx.summary"], '
        '"unverified_claims": ["图谱事实之外的陈述; 完全锚定为空数组"], '
        '"content": "markdown格式正文"}。'
        "\n注意: difficulty_level 由系统按知识点难度统一赋值, 你不要输出该字段。"
        "不要输出 JSON 以外文字。"
    ))
    user = HumanMessage(content=(
        f"知识图谱节点:\n"
        f"- node_id: {node['node_id']}\n- 名称: {node.get('name','')}\n"
        f"- 难度: {node.get('difficulty',1)}\n- summary: {node.get('summary','')}\n"
        f"- key_points: {json.dumps(kps, ensure_ascii=False)}\n"
        f"- common_mistakes: {json.dumps(node.get('common_mistakes', []), ensure_ascii=False)}\n"
        f"- prerequisites: {json.dumps(node.get('prerequisites', []), ensure_ascii=False)}\n\n{type_spec}"
    ))
    resp = model.invoke([system, user])
    data = parse_llm_json(resp.content)
    if not isinstance(data, dict):
        raise ValueError(f"feedback 生成响应非对象: {type(data)}")
    return _finalize_resource(data, node, content_type, label)


def _adaptation_style(label: str) -> str:
    """label → 语言风格提示 (复用 _build_generation_prompt 的风格表)。"""
    return {
        "beginner": "面向初学者: 多用类比和生活化比喻，减少专业术语",
        "intermediate": "面向进阶者: 可引入底层原理和性能考量",
        "advanced": "面向高级者: 讨论设计模式选择与工程权衡",
    }.get(label, "")
