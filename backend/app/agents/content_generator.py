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
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeout
from datetime import datetime

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.llm import _current_overrides, get_chat_model, get_default_chat_model, llm_configured, safe_llm_call, with_state_overrides
from app.graph.engine import KnowledgeGraph
from app.config import settings
from app.utils.json_utils import parse_llm_json
from app.utils.logging import get_logger

logger = get_logger(__name__)

# 单次生成的节点数上限 (控量: 每节点3次LLM调用；5 节点=15 次调用, 并发5 下 wall-clock 仍 ≈ 单节点耗时)
MAX_NODES_TO_GENERATE = 5
# 每节点3种资源
CONTENT_TYPES = ("lecture", "practice_guide", "test")

# 内容类型中文标签 (SSE 进度文案 / 前端展示单一源)
CONTENT_TYPE_LABELS = {"lecture": "讲义", "practice_guide": "实操指南", "test": "测试题"}


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
            "生成【分层讲义】: 首行 # 标题(带难度标签)、核心概念讲解(缩进≤3层, 结论先行)、"
            "带注释代码示例、常见误区提醒; 「学习目标/小节总结」仅当对学习者有实际价值时出现, "
            "无信息量则省略(骨架按需, 非固定模板)。"
            "\n【内容丰富度要求(只用节点已有事实, 禁编造新事实)】"
            "①覆盖全部key_points, 每条充分展开(以讲清为准, 不以字数为准); "
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
            "\n【格式冻结——前端本地判分解析依赖, 必须逐字保持】题目用「**题目**：…」、"
            "选项行用「A. …」「B. …」、答案用「**答案**：X」、解析用「**解析**：…」。"
            "\n【答案自检--消除测试题答案幻觉】每道题的答案/预期输出在写入前必须逐步心算执行验证, "
            "重点复核以下高频易错点(历次独立裁判质检发现的真实错误): "
            "①列表方法: pop(i)删除并返回索引i的元素(非删除末尾), remove(v)删首个等于v的元素且返回None, "
            "sort()原地排序返回None(非新列表), sorted()返回新列表不改原对象; "
            "②字符串方法: find()找不到返回-1(非None/非False), join()由分隔符字符串调用(非列表调用), "
            "strip()/replace()/upper()/lower()返回新字符串不改原串(字符串不可变); "
            "③切片: s[a:b]不含索引b(右界不包含), 负索引从末尾计数。"
            "心算自检在生成时完成, 验证标记不得写入正文; 无法确定则改出题方式避免写不确定的答案。"
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
        "\n【文风契约——内容直接展示给用户, 见 00 共享契约第 7 节】"
        "\n结论先行, 禁「首先/其次/总之/综上所述」式模板行文与空总结段; 列表连续≤6条且"
        "每条承载事实, 不凑空心列表; 禁 emoji; 加粗每屏≤3处; 表格仅用于真正多维对比; "
        "每段承载节点事实或可操作动作, 讲清即止反对灌水。"
        "溯源写 source_nodes 字段; [ref: ...] 与 [已心算验证] 等机器标记不得写入 content 正文。"
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
        '"content": "markdown格式正文, 首行 # 标题; 不含 [ref:] 等机器标记"}。'
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
    def _node(state, progress_cb=None, cancel_check=None) -> dict:
        # progress_cb(done, total, node, ctype) / cancel_check() -> bool:
        # SSE 流式端点注入的进度打点与取消检查点 (LangGraph 调用不传 → None, 行为不变)。
        profile = state.get("user_profile", {})
        kg_state = state.get("knowledge_graph", {}) or {}
        log = [f"[{datetime.utcnow().isoformat()}] 📚 领域知识生成: 开始"]

        return _node_body(state, profile, kg_state, log,
                          progress_cb=progress_cb, cancel_check=cancel_check)

    def _node_body(state, profile, kg_state, log, progress_cb=None, cancel_check=None) -> dict:
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

        # 节点级再生缓存 (v1.3.3 提速): 打回时只重生成被审核点名的节点 (issues[].source_node),
        # 未被点名且有既有资源的节点直接沿用 (免 15 次全量重跑)。点名信息缺失或该节点
        # 此前生成失败 (无资源) → 仍重生成; 首轮 (无既有资源) → 全量, 行为与旧版一致。
        previous_resources: list[dict] = []
        flagged_ids: set[str] = set()
        if retry_hint and isinstance(state.get("generated_content"), dict):
            previous_resources = [r for r in (state["generated_content"].get("resources") or [])
                                  if isinstance(r, dict) and (r.get("content") or "").strip()]
            rv = state.get("review_results") or {}
            # reviewer 真实产出形状: issues 在 review_results.dimensions.<dim>.issues (两层深);
            # 顶层 rv["issues"] 为兼容保留。终审修复: 此前只取一层导致 flagged 恒空 → 缓存永不生效。
            buckets = [rv.get("issues")] if isinstance(rv.get("issues"), list) else []
            dims = rv.get("dimensions")
            if isinstance(dims, dict):
                buckets += [d.get("issues") for d in dims.values()
                            if isinstance(d, dict) and isinstance(d.get("issues"), list)]
            for bucket in buckets:
                for issue in bucket:
                    if isinstance(issue, dict) and issue.get("source_node"):
                        flagged_ids.add(str(issue["source_node"]))
            # 防空转兜底: LLM 产出的 source_node 可能是自由文本 (如 "resources[2]") 而非裸
            # node_id — 点名与路径节点零交集时保守全量再生, 避免零再生沿用被点名的问题内容
            target_ids = {n.get("node_id") for n in learning_path[:MAX_NODES_TO_GENERATE]}
            if flagged_ids and not (flagged_ids & target_ids):
                flagged_ids = set()

        theory_level = profile.get("theory_level", 2) or 2
        style_extra = _background_style_hint(profile)  # 赛题背景适配: VARK 风格 + 学历/专业
        target_nodes = learning_path[:MAX_NODES_TO_GENERATE]
        log.append(f"📖 为 {len(target_nodes)} 个节点生成资源 (每节点3种, level={theory_level})")

        prev_by_node = {r.get("target_node_id") for r in previous_resources}
        regen_nodes = [
            n for n in target_nodes
            if not flagged_ids  # 审核未点名任何节点 → 保守全量再生 (行为不变)
            or n.get("node_id") in flagged_ids  # 被点名的节点重生成
            or n.get("node_id") not in prev_by_node  # 无既有资源 (此前失败) 也重生成
        ]
        if flagged_ids and len(regen_nodes) < len(target_nodes):
            log.append(f"⚡ 审核点名 {len(flagged_ids)} 个节点 → 重生成 {len(regen_nodes)} 个, "
                       f"沿用 {len(target_nodes) - len(regen_nodes)} 个未点名节点的既有资源")
        tasks = [(node, ctype) for node in regen_nodes for ctype in CONTENT_TYPES]

        # Spec B: ContextVar 不跨线程传播；safe_llm_call 在 worker 内重设 overrides。
        overrides = _current_overrides.get()

        # 沿用未被点名的既有资源 (重生成节点的新资源稍后合并)
        resources: list[dict] = [r for r in previous_resources
                                 if r.get("target_node_id") not in {n.get("node_id") for n in regen_nodes}]
        generation_failures = []
        # 并发度: 可配 (CONTENT_GEN_CONCURRENCY), 默认 5; max(1,...) 防配置为 0 崩溃。
        # 实测 (DeepSeek V4 Pro API, 9 次生成): 并发5 内容生成 137s, 并发3 反而 190s。
        # 降并发未能减少 429 退避 (DeepSeek 对并发5 限流不严重), 却多了轮次 (2轮 vs 3轮) 更慢。
        # 故默认 5; 仅在确认重度限流时调低, 或换更快模型/减资源数 (减 LLM 调用) 才能真降耗时。
        max_workers = max(1, min(settings.CONTENT_GEN_CONCURRENCY, len(tasks)))
        # submit + as_completed (原 pool.map 无法在完成时打点/取消): 每段资源完成即回调
        # progress_cb(done, total, node, ctype) 供 SSE 上报「3/15 · 循环·讲义」; cancel_check
        # 在检查点为真时停止提交后续等待任务 (运行中的单次 LLM 调用自然收尾, 结果丢弃)。
        total = len(tasks)
        outcomes: dict = {}
        cancelled = False
        _gen_t0 = time.perf_counter()  # 生成段耗时打点 (与 submit _tick 同口径, 入 orchestration_log)
        pool = ThreadPoolExecutor(max_workers=max_workers)
        future_args = {
            pool.submit(
                safe_llm_call,
                _generate_one, node, theory_level, ctype, retry_hint, style_extra,
                overrides=overrides, logger=logger,
                label=f"node={node.get('node_id')} type={ctype}"): (node, ctype)
            for node, ctype in tasks
        }
        try:
            for future in as_completed(future_args):
                node_arg, ctype = future_args[future]
                outcomes[(node_arg.get("node_id"), ctype)] = future.result()
                if progress_cb:
                    progress_cb(len(outcomes), total, node_arg, ctype)
                if cancel_check and cancel_check() and len(outcomes) < total:
                    cancelled = True
                    log.append("⏹ 用户停止等待, 内容生成提前收摊 (已完成部分保留)")
                    break
        finally:
            pool.shutdown(wait=False, cancel_futures=cancelled)

        for (node, ctype) in tasks:
            outcome = outcomes.get((node.get("node_id"), ctype))
            if outcome is None:
                # 未跑到的任务: 仅取消时出现 (无超时语义, safe_llm_call 内部已兜底异常)
                generation_failures.append(_failure_record(node, ctype, "已取消（用户停止等待）"))
                continue
            ok, res = outcome
            if ok and res is not None and str(res.get("content") or "").strip():
                resources.append(res)
            elif ok:
                generation_failures.append(_failure_record(node, ctype, "生成内容为空（模型未返回正文）"))
            else:
                generation_failures.append(_failure_record(node, ctype, "LLM 调用失败（网络/限流/响应格式）"))

        if generation_failures:
            log.append(f"⚠️ {len(generation_failures)} 段生成失败 (详见 generation_failures)")
        _gen_elapsed = int((time.perf_counter() - _gen_t0) * 1000)
        log.append(f"✅ 生成完成: {len(resources)} 段资源 (耗时 {_gen_elapsed}ms, "
                   f"重生成 {len(regen_nodes)}/{len(target_nodes)} 节点)")
        logger.info("内容生成: resources=%d failures=%d (并发=%d, 耗时=%dms, regen_nodes=%d/%d)",
                    len(resources), len(generation_failures), max_workers, _gen_elapsed,
                    len(regen_nodes), len(target_nodes))

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


# feedback 再生时间预算 (issue: 路由 120s 硬超时把慢端点的整单结果掐掉, 用户感知"自动取消"):
# 前端等待 330s > 路由硬上限 300s > 再生截止 270s; 到点收已完成的, 未完成记失败而非整单丢弃。
FEEDBACK_REGEN_DEADLINE = 270
# 单调用封顶: 显式超时 + SDK 重试至多 1 次 (默认静默重试 2 次可把坏端点拖到 3×timeout+, 必撞硬上限)
FEEDBACK_CALL_TIMEOUT = 90


def _feedback_chat_model():
    """feedback 单调用模型: 显式封顶超时与重试 (ContextVar overrides 同样生效)。"""
    return get_chat_model(max_retries=1, timeout=FEEDBACK_CALL_TIMEOUT)


def regenerate_for_feedback(
    strategy: str,
    profile: dict,
    learning_path: list[dict],
    kg: KnowledgeGraph,
    progress_cb=None,
    cancel_check=None,
) -> dict:
    """按动态反馈策略针对性再生学习内容 (W4 计划⑤闭环)。

    返回 {strategy, resources, node_count, generated_at}。
    LLM 未配置/无目标节点 → 空 resources (不抛)。
    progress_cb(done, total, node, ctype) / cancel_check() -> bool:
    SSE 流式端点注入的进度打点与取消检查点 (REST 调用不传 → 行为不变)。
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
    # 并行生成 + 截止时间有界收集: 全部完成提前返回; 到点未完成的记"生成超时"失败,
    # 已完成的照常返回 (issue: 此前上层 wait_for 到点整单 504, 已生成结果一并丢弃)。
    # shutdown(wait=False, cancel_futures=True): 未启动的任务直接取消, 运行中的自然收尾,
    # 孤儿线程结果丢弃 (与 to_thread 超时同代价, 不阻塞响应)。
    pool = ThreadPoolExecutor(max_workers=min(len(tasks), 6))
    futures = [
        pool.submit(
            safe_llm_call,
            _generate_feedback_one, node, theory_level, ctype, log_hint, style_extra,
            overrides=overrides, logger=logger,
            label=f"feedback node={node.get('node_id')} {ctype}")
        for node, ctype in tasks
    ]
    index_by_future = {f: i for i, f in enumerate(futures)}
    outcomes: dict = {}
    cancelled = False
    try:
        for future in as_completed(futures, timeout=FEEDBACK_REGEN_DEADLINE):
            idx = index_by_future[future]
            outcomes[idx] = future.result()
            if progress_cb:
                node_arg, ctype = tasks[idx]
                progress_cb(len(outcomes), len(tasks), node_arg, ctype)
            if cancel_check and cancel_check():
                cancelled = True
                logger.info("feedback 再生: 用户停止等待, 提前收摊 (已完成 %d/%d)", len(outcomes), len(tasks))
                break
    except FuturesTimeout:
        pass  # 到点收摊: 未完成的调用记"生成超时"失败, 不再无限等
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    for i, (node, ctype) in enumerate(tasks):
        outcome = outcomes.get(i)
        if outcome is None:
            reason = "已取消（用户停止等待）" if cancelled else \
                f"生成超时（>{FEEDBACK_REGEN_DEADLINE}s，端点过慢或网络不稳，已返回其余已完成内容）"
            generation_failures.append(_failure_record(node, ctype, reason))
            continue
        ok, res = outcome
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
    model = _feedback_chat_model()
    kps = node.get("key_points", [])
    label = _adaptation_label(theory_level)

    type_spec = {
        "lecture": (
            "生成【分层讲义】(issue-67 专业性升级): 正文 500–800 字。结构: "
            "①标题(首行 # 标题, 带难度标签) ②核心概念讲解: 覆盖该节点 >=3 个 key_points, "
            "每个充分展开, 含至少 1 个带注释的代码/结构示例 ③常见误区: 每条 common_mistake 做"
            "「错误做法 → 正确做法」对照; 「学习目标/小节总结」仅当对学习者有实际价值时出现, "
            "无信息量则省略。难度>=3 时用 Markdown 表格对比 >=3 行。"
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
            "每道题格式冻结 (前端本地判分解析依赖, 逐字保持): **题目**、选项(若有)、**答案**、"
            "**解析**(一句到位, 说明为什么/错在哪)。"
            "挑战题须跨 2-3 个 key_points 推理。"
            "【答案自检--消除测试题答案幻觉】每道题答案/预期输出在写入前必须逐步心算验证 "
            "(验证标记不入正文); 无法确定的答案宁可改题, 不得编造。总字数 300–600 字, 只用节点已有事实, 禁编造。"
        ),
    }.get(content_type, "")

    system = SystemMessage(content=(
        "你是 KMatch 领域知识生成 Agent，按动态反馈策略针对性再生学习内容。"
        f"{_adaptation_style(label)}{style_extra}。"
        f"特别要求: {hint}。"
        "\n【文风契约——内容直接展示给用户, 见 00 共享契约第 7 节】"
        "结论先行, 禁「首先/其次/总之/综上所述」式模板行文与空总结段; 列表连续≤6条且每条"
        "承载事实; 禁 emoji; 加粗每屏≤3处; 每段承载节点事实或可操作动作, 讲清即止。"
        "test 类资源的题目/选项/答案/解析加粗格式为豁免区, 必须逐字保持。"
        "溯源写 source_nodes 字段; [ref: ...] 等机器标记不得写入 content 正文。"
        "\n【高保真约束——消除幻觉】只能依据本节点 summary/key_points/common_mistakes "
        "生成内容，严禁补充图谱外的实现细节/内部表示/具体数值/版本号/性能数据"
        "(训练记忆非图谱事实)。每条断言须能在节点信息中找到依据，未提供者留白不补全。"
        "严格输出 JSON 对象: "
        '{"content_type": "' + content_type + '", "target_node_id": "PY-xxx", '
        '"adaptation_profile": "beginner|intermediate|advanced", '
        '"source_nodes": ["PY-xxx.key_points[0]", "PY-xxx.summary"], '
        '"unverified_claims": ["图谱事实之外的陈述; 完全锚定为空数组"], '
        '"content": "markdown格式正文, 首行 # 标题; 不含 [ref:] 等机器标记"}。'
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
