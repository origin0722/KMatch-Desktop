"""
内容审核 Agent (Content Reviewer Agent)

对齐 data/prompts/05_content_reviewer_agent.txt。

双模式审核 (第4周 BUG-016 审核对象迁移):
  - 画像模式 (W2 局部流程): state 无 generated_content.resources 时，审学情检测产出的画像
  - 内容模式 (W4 全流程): state 有 generated_content.resources 时，审领域知识生成产出的学习内容

两模式共用四维度加权 (40/30/20/10) 与阈值 0.85，复用 _normalize_dims/_merge_issues/_weighted_score。

画像模式硬规则: node_id 存在性 + known/weak 交叉。
内容模式硬规则: source_nodes 引用格式 + 目标节点存在性 + 溯源标记完整性。
LLM 语义审核: 画像审 level 自洽/error_patterns 质量；内容审事实准确性/幻觉/逻辑/教学适当性。
overall_score ≥ REVIEW_PASS_THRESHOLD 通过，否则打回。
"""

import json
from datetime import datetime

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.llm import _current_overrides, get_default_chat_model, llm_configured, with_state_overrides
from app.config import settings
from app.graph.engine import KnowledgeGraph
from app.utils.json_utils import parse_llm_json
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _hard_check_node_existence(kg: KnowledgeGraph, profile: dict) -> list[dict]:
    """硬规则: 画像引用的所有 node_id 必须真实存在于图谱。复用 engine.get_node。"""
    issues = []
    for section in ("known_topics", "weak_topics"):
        for t in profile.get(section, []):
            nid = t.get("node_id")
            if not nid:
                continue
            if kg.get_node(nid) is None:
                issues.append({
                    "severity": "high",
                    "dimension": "factual_accuracy",
                    "problem": f"画像引用了不存在的图谱节点 {nid}（{section}）",
                    "source_node": nid,
                })
    return issues


def _hard_check_overlap(profile: dict) -> list[dict]:
    """硬规则: known_topics 与 weak_topics 不得交叉重复（复用 validate_data 阶段2 规则）。"""
    known_ids = {t.get("node_id") for t in profile.get("known_topics", []) if isinstance(t, dict)}
    weak_ids = {t.get("node_id") for t in profile.get("weak_topics", []) if isinstance(t, dict)}
    overlap = known_ids & weak_ids
    return [
        {
            "severity": "high",
            "dimension": "hallucination",
            "problem": f"节点 {nid} 同时出现在 known_topics 和 weak_topics，状态矛盾",
            "source_node": nid,
        }
        for nid in overlap
    ]


def _llm_review(profile: dict, assessment: dict) -> dict:
    """LLM 语义审核: level 自洽性 + error_patterns 质量 + 教学适当性。返回各维度评分。"""
    model = get_default_chat_model()
    system = SystemMessage(content=(
        "你是 KMatch 内容审核 Agent，审核学情检测产出的用户画像。从四个维度打分(0-1)，"
        "并指出问题。严格输出 JSON: "
        '{"factual_accuracy":{"score":0-1,"issues":[]},'
        '"hallucination":{"score":0-1,"issues":[]},'
        '"logic_consistency":{"score":0-1,"issues":[]},'
        '"teaching_appropriateness":{"score":0-1,"issues":[]}}。'
        "issues 元素: {severity,problem,source_node}。不输出 JSON 以外文字。"
    ))
    user = HumanMessage(content=(
        f"待审画像:\n{json.dumps(profile, ensure_ascii=False, indent=2)}\n\n"
        f"测评明细(答题正确率等):\n{json.dumps(assessment, ensure_ascii=False)}\n\n"
        "审核要点: theory_level 是否与答题正确率自洽；"
        "weak_topics 的 error_patterns 是否具体可操作；mastery 值是否在 0-1 合理区间。\n"
        "字段说明(勿误判): last_test_score 为 0-10 分制掌握分(mastery×10, 满分10), "
        "非答对题数; preferred_pace/time_per_week 为默认值不作事实审核。\n"
        "learning_style/practical_level 按来源标记区分 (W5 三维测评): "
        "style_source=quiz / practical_source=code_test 为实测值, 须纳入事实审核 "
        "(如 practical_level 与 tests_passed/tests_total 是否相称); "
        "style_source=default / practical_source=unassessed 为占位值, 不作事实审核。\n"
        "mastery 分段: ≥0.8 已掌握(known), <0.8 未达掌握含0.5学习中(weak)。"
    ))
    resp = model.invoke([system, user])
    return parse_llm_json(resp.content)


# ============================================================
# 内容模式审核 (第4周: 审 generated_content，对齐 05 prompt)
# ============================================================

# 溯源标记格式: PY-xxx 或 PY-xxx.key_points[0] 等，取节点 ID 部分
import re as _re

_SOURCE_NODE_PATTERN = _re.compile(r"^([A-Z]{2}-\d{3})(?:\.|$)")


def _extract_source_node_id(ref: str) -> str | None:
    """从溯源引用 'PY-012.key_points[0]' 提取节点 ID 'PY-012'；非法格式返回 None。"""
    if not isinstance(ref, str):
        return None
    m = _SOURCE_NODE_PATTERN.match(ref.strip())
    return m.group(1) if m else None


def _hard_check_content_sources(kg: KnowledgeGraph, resources: list[dict]) -> list[dict]:
    """内容模式硬规则: 每段资源的 source_nodes 引用必须格式合法且节点真实存在。

    对齐 05 prompt 规则1(事实准确性) + 规则5(溯源完整性)。
    """
    issues = []
    for i, res in enumerate(resources):
        if not isinstance(res, dict):
            issues.append({
                "severity": "high", "dimension": "factual_accuracy",
                "problem": f"resources[{i}] 非对象",
                "source_node": "",
            })
            continue
        sources = res.get("source_nodes", [])
        if not isinstance(sources, list) or not sources:
            # 溯源完整性: 无任何溯源标记 → 幻觉风险
            issues.append({
                "severity": "high", "dimension": "hallucination",
                "problem": f"resources[{i}] (target={res.get('target_node_id')}) 无 source_nodes 溯源标记",
                "source_node": res.get("target_node_id", ""),
            })
            continue
        for ref in sources:
            nid = _extract_source_node_id(ref)
            if nid is None:
                issues.append({
                    "severity": "medium", "dimension": "factual_accuracy",
                    "problem": f"resources[{i}] 溯源引用格式非法: '{ref}'",
                    "source_node": "",
                })
            elif kg.get_node(nid) is None:
                issues.append({
                    "severity": "high", "dimension": "factual_accuracy",
                    "problem": f"resources[{i}] 溯源引用了不存在的图谱节点 {nid}",
                    "source_node": nid,
                })
    return issues


def _llm_review_content(resources: list[dict], profile: dict) -> dict:
    """内容模式 LLM 语义审核: 事实准确性/幻觉/逻辑一致性/教学适当性。返回各维度评分。"""
    model = get_default_chat_model()
    system = SystemMessage(content=(
        "你是 KMatch 内容审核 Agent，逐条校验领域知识生成Agent产出的学习内容。"
        "对照知识图谱事实节点检测幻觉、错误与不一致。从四个维度打分(0-1)并指出问题。"
        "严格输出 JSON: "
        '{"factual_accuracy":{"score":0-1,"issues":[]},'
        '"hallucination":{"score":0-1,"issues":[]},'
        '"logic_consistency":{"score":0-1,"issues":[]},'
        '"teaching_appropriateness":{"score":0-1,"issues":[]}}。'
        "issues 元素: {severity,problem,source_node}。不输出 JSON 以外文字。"
    ))
    # 截断超长内容避免 token 爆炸
    payload = json.dumps(resources, ensure_ascii=False)
    if len(payload) > 6000:
        payload = payload[:6000] + "\n...(截断)"
    user = HumanMessage(content=(
        f"待审生成内容:\n{payload}\n\n"
        f"目标用户画像 (theory_level={profile.get('theory_level')}):\n"
        f"{json.dumps({k: profile.get(k) for k in ('theory_level','target_direction')}, ensure_ascii=False)}\n\n"
        "审核要点(只判真实幻觉，勿过严): "
        "①事实幻觉——内容是否编造了图谱节点 summary/key_points/common_mistakes "
        "以外的实现细节/内部表示/具体数值/版本号/性能数据(如「int 内部位数组」「对象头字节数」"
        "等节点未提供的技术断言)，编造即扣 hallucination/factual_accuracy 分；"
        "②难度/语言风格是否匹配用户 level；③内容内部是否前后矛盾；④溯源标记是否完整；"
        "⑤测试题答案复核--对 content_type=test 的资源, 逐题复核答案/预期输出的正确性: "
        "列表方法(pop(i)删索引i元素/remove/sort返回None/sorted返回新列表)、"
        "字符串方法(find返回-1非None/join由分隔符串调用/不可变方法返回新串)、"
        "切片右界不包含(s[a:b]不含b)。答案与 Python 实际行为不符即扣 factual_accuracy 分(severity=high)并打回。"
        "注意: 节点未覆盖的技术深度(如某概念节点未讲底层实现)不算幻觉，不扣分；"
        "只扣'编造图谱外事实'，不扣'图谱未覆盖'。"
    ))
    resp = model.invoke([system, user])
    return parse_llm_json(resp.content)


def _normalize_dims(dims) -> dict:
    """归一化 LLM 审核输出为 {dim: {score, issues}} 结构。

    防 LLM 返回非 conforming JSON 导致后续 merge/weighted 崩溃:
      - 非 dict / 空 → 四维度默认满分
      - 维度值为非 dict (如扁平 {"factual_accuracy": 0.8}) → 包成 {"score": 值}
      - 缺 score/issues → 补默认 (1.0 / [])
      - score 非 number → 1.0
    """
    if not isinstance(dims, dict) or not dims:
        return _default_dims()

    normalized = {}
    for dim in ("factual_accuracy", "hallucination", "logic_consistency", "teaching_appropriateness"):
        val = dims.get(dim, {})
        if not isinstance(val, dict):
            val = {"score": val} if isinstance(val, (int, float)) else {}
        score = val.get("score", 1.0)
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            score = 1.0
        issues = val.get("issues", [])
        if not isinstance(issues, list):
            issues = []
        normalized[dim] = {"score": float(score), "issues": issues}
    return normalized


def _default_dims() -> dict:
    """LLM 失败/未配置时的四维度默认满分。"""
    return {
        "factual_accuracy": {"score": 1.0, "issues": []},
        "hallucination": {"score": 1.0, "issues": []},
        "logic_consistency": {"score": 1.0, "issues": []},
        "teaching_appropriateness": {"score": 1.0, "issues": []},
    }


def _merge_issues(dims: dict, hard_issues: list[dict]) -> dict:
    """把硬规则发现的问题并入对应维度，并重算该维度分数。

    BUG B12: 旧实现对所有"有 issues"的维度封顶 0.6, 但 LLM 返回的 dims 本身可能带 issues
    且已降分 → 二次封顶 = 双重惩罚, 导致 otherwise 合格内容因一条轻微 LLM issue 跌破 0.85 误打回。
    修复: 仅对被 hard_issues 命中的维度封顶 (硬规则问题才该刚性扣分), LLM 维度保留其原 score。
    """
    hard_hit_dims: set[str] = set()
    for issue in hard_issues:
        dim = issue.get("dimension", "factual_accuracy")
        dims.setdefault(dim, {"score": 1.0, "issues": []})
        dims[dim]["issues"].append(issue)
        hard_hit_dims.add(dim)
    # 仅硬规则命中的维度分数上限下调 (LLM 维度保留原 score, 不二次惩罚)
    for dim in hard_hit_dims:
        data = dims[dim]
        data["score"] = min(data.get("score", 1.0), 0.6)
    return dims


def _weighted_score(dims: dict) -> float:
    """四维度加权（对齐 reviewer prompt 权重）。"""
    weights = {
        "factual_accuracy": 0.4,
        "hallucination": 0.3,
        "logic_consistency": 0.2,
        "teaching_appropriateness": 0.1,
    }
    total = 0.0
    for dim, w in weights.items():
        total += w * dims.get(dim, {"score": 0.0}).get("score", 0.0)
    return round(total, 3)


def reviewer_node(kg: KnowledgeGraph):
    """返回 LangGraph 节点函数。闭包注入 KnowledgeGraph 实例。"""

    @with_state_overrides
    def _node(state) -> dict:
        profile = state.get("user_profile", {})
        assessment = state.get("assessment", {})
        retry = state.get("retry_count", 0)
        log = [f"[{datetime.utcnow().isoformat()}] 🔍 内容审核: 开始审画像 (第{retry+1}轮)"]

        return _node_body(state, profile, assessment, retry, log)

    def _node_body(state, profile, assessment, retry, log) -> dict:
        # 空画像（LLM 未配置/降级/失败）→ 直接判不通过
        # dimensions 仍返回四维度默认满分 (履行对接契约: 不会缺失 key)，
        # overall_score=0 因 passed=False，B 端可安全访问 dimensions.*.score
        if not profile:
            reason = "LLM 未配置" if not llm_configured() else "学情检测未产出有效画像"
            log.append(f"⚠️ 画像为空 ({reason})，审核无法进行，判不通过")
            return {
                "review_results": {
                    "passed": False,
                    "overall_score": 0.0,
                    "threshold": settings.REVIEW_PASS_THRESHOLD,
                    "dimensions": _default_dims(),
                    "verdict": "reject",
                    "retry_hint": f"{reason}，请检查后端 LLM 配置后重试",
                    "reviewed_at": datetime.utcnow().isoformat() + "Z",
                },
                "retry_count": retry + 1,
                "orchestration_log": log,
            }

        try:
            # --- 双模式分发 (BUG-016 + BUG-031) ---
            # 进入过内容阶段 (content_phase_entered) → 内容模式;
            # 即使本轮 resources 为空 (路径空/生成全失败) 也保持内容模式，
            # 由 _hard_check_content_sources 把"无溯源"判为问题 → 不通过，
            # 避免回退画像模式 + 画像通过 → graph_controller 无限循环。
            gen_content = state.get("generated_content") or {}
            resources = gen_content.get("resources") if isinstance(gen_content, dict) else None
            if resources is None:
                resources = []
            content_mode = bool(state.get("content_phase_entered"))

            if content_mode:
                # 内容阶段无资源 (路径空/生成全失败) → 直接判不通过 (BUG-031: 防无限循环)
                if not resources:
                    log.append("⚠️ 内容阶段无生成资源，判不通过")
                    return {
                        "review_results": {
                            "passed": False,
                            "overall_score": 0.0,
                            "threshold": settings.REVIEW_PASS_THRESHOLD,
                            "dimensions": _default_dims(),
                            "verdict": "reject",
                            "retry_hint": "学习路径为空或内容生成全部失败，无法交付学习资源",
                            "reviewed_at": datetime.utcnow().isoformat() + "Z",
                        },
                        "retry_count": retry + 1,
                        "orchestration_log": log,
                    }
                log.append(f"📝 内容模式: 审核 {len(resources)} 段生成资源")
                hard_issues = _hard_check_content_sources(kg, resources)
                if hard_issues:
                    log.append(f"⚠️ 硬规则发现 {len(hard_issues)} 个溯源/事实问题")
                llm_review = _llm_review_content
                llm_arg = (resources, profile)  # BUG-037: 漏传 profile 致 TypeError 降级
                review_subject = "生成内容"
            else:
                log.append("📊 画像模式: 审核学情检测产出的用户画像")
                hard_issues = _hard_check_node_existence(kg, profile) + _hard_check_overlap(profile)
                if hard_issues:
                    log.append(f"⚠️ 硬规则发现 {len(hard_issues)} 个问题")
                llm_review = _llm_review
                llm_arg = (profile, assessment)
                review_subject = "画像"

            # --- LLM 语义审核（内部保护，失败不影响硬规则结果） ---
            dims = {}
            if llm_configured():
                try:
                    dims = llm_review(*llm_arg) if isinstance(llm_arg, tuple) else llm_review(llm_arg)
                except Exception:
                    logger.warning("LLM 审核调用失败，降级为仅硬规则评分", exc_info=True)
                    log.append("⚠️ LLM 审核异常，仅使用硬规则结果")
            else:
                log.append("⚠️ LLM 未配置，仅硬规则审核")

            # 归一化 LLM 输出 (非 conforming JSON → 默认满分，防后续 merge/weighted 崩溃)
            dims = _normalize_dims(dims) if dims else _default_dims()

            # 硬规则发现的问题并入对应维度（维度分数上限下调至 0.6）
            dims = _merge_issues(dims, hard_issues)
            overall = _weighted_score(dims)
            passed = overall >= settings.REVIEW_PASS_THRESHOLD

            verdict = "pass" if passed else "reject"
            hint = "" if passed else _build_retry_hint(dims)

            log.append(
                f"{'✅' if passed else '❌'} {review_subject}审核{'通过' if passed else '不通过'}: "
                f"总分={overall} (阈值{settings.REVIEW_PASS_THRESHOLD})"
            )
            logger.info("%s审核完成: score=%s passed=%s", review_subject, overall, passed)

            return {
                "review_results": {
                    "passed": passed,
                    "overall_score": overall,
                    "threshold": settings.REVIEW_PASS_THRESHOLD,
                    "dimensions": dims,
                    "verdict": verdict,
                    "retry_hint": hint,
                    "reviewed_at": datetime.utcnow().isoformat() + "Z",
                },
                "retry_count": retry + 1,
                "orchestration_log": log,
            }
        except Exception as e:
            # 顶层保护 (F6): 硬规则 kg.get_node 抖动等意外异常 → 降级为审核不通过，
            # 不让整条测评流程 500。与 diagnostics_node / graph_controller_node 一致。
            logger.error("审核节点异常，降级为审核不通过", exc_info=True)
            log.append(f"❌ 审核节点异常: {e}，降级为审核不通过")
            return {
                "review_results": {
                    "passed": False,
                    "overall_score": 0.0,
                    "threshold": settings.REVIEW_PASS_THRESHOLD,
                    "dimensions": _default_dims(),
                    "verdict": "reject",
                    "retry_hint": f"审核节点异常: {e}",
                    "reviewed_at": datetime.utcnow().isoformat() + "Z",
                },
                "retry_count": retry + 1,
                "orchestration_log": log,
            }

    return _node


def _build_retry_hint(dims: dict) -> str:
    """从各维度问题生成可操作的打回提示。"""
    hints = []
    for dim, data in dims.items():
        for issue in data.get("issues", [])[:2]:
            hints.append(issue.get("problem", ""))
    return "；".join(hints) if hints else "请修正审核标记的问题后重新提交"
