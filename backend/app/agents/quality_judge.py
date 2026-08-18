"""独立裁判 (LLM-as-Judge) — 与 generator/reviewer 解耦的质量判定 (M5 升级)。

循环验证风险: 幻觉率由 reviewer 自评, 而 reviewer 与 content_generator 共用同一 LLM 与
同源 prompt 体系 —— 等价于"作者自批", 0% 数字对评委缺乏说服力。本模块引入独立裁判:

  - judge_hallucination: 只看资源内容 + 图谱事实节点 (summary/key_points), 不拿生成
    推理过程与 reviewer 结论, 判定 grounded|hallucinated|unverifiable
  - judge_adaptation: 独立评资源教学难度 (1-5), 与画像理论水平比对 (|gap|<=1)

裁判 LLM 配置: JUDGE_LLM_* (.env 独立配置, 可与主 LLM 不同源)。
未配置 → 回退主 LLM 并标记 same_source=True (诚实降级, 报告标注可信度)。

纯函数可单测: 判定函数接受 judge_llm 参数, 单测传 mock; 默认走 get_judge_llm()。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.agents.llm import get_default_chat_model
from app.config import settings
from app.utils.json_utils import parse_llm_json
from app.utils.logging import get_logger

logger = get_logger(__name__)

PROMPTS_DIR = Path(settings.DATA_DIR).parent / "data" / "prompts"

_judge_prompts: dict[str, str] = {}


def _load_prompt(name: str) -> str:
    """惰性读取裁判 prompt 文件 (仅成功时缓存, 失败回退内置摘要)。"""
    if name not in _judge_prompts:
        try:
            _judge_prompts[name] = (PROMPTS_DIR / f"{name}.txt").read_text(encoding="utf-8")
        except OSError:
            logger.warning("裁判 prompt 缺失: %s, 使用内置摘要", name)
            _judge_prompts[name] = ""
    return _judge_prompts[name]


def get_judge_llm():
    """构造裁判 LLM。JUDGE_LLM_* 配置了独立 key → 独立模型 (same_source=False);
    否则回退主 LLM (same_source=True)。
    """
    if settings.JUDGE_LLM_API_KEY:
        from langchain_openai import ChatOpenAI
        judge = ChatOpenAI(
            api_key=settings.JUDGE_LLM_API_KEY,
            base_url=settings.JUDGE_LLM_BASE_URL or settings.LLM_BASE_URL,
            model=settings.JUDGE_LLM_MODEL or settings.LLM_MODEL,
            temperature=0.0,
            timeout=settings.LLM_TIMEOUT,
            max_retries=2,
        )
        return judge, False
    return get_default_chat_model(), True


def _invoke_judge(prompt: str, judge_llm) -> dict:
    """调裁判 LLM 并解析 JSON。失败 → 返回 {"error": ...} (由调用方按 unverifiable 处理)。"""
    try:
        resp = judge_llm.invoke(prompt)
        text = getattr(resp, "content", "") or ""
        parsed = parse_llm_json(text)
        return parsed if isinstance(parsed, dict) else {"error": "裁判输出非对象"}
    except Exception as e:  # LLM 超时/解析失败 → 不中断批量, 记为无法判定
        logger.warning("裁判调用失败: %s", e)
        return {"error": str(e)}


# ---------------------------------------------------------------
# 幻觉判定
# ---------------------------------------------------------------

def _node_facts_text(kg, node_id: str, source_nodes: list) -> str:
    """收集图谱事实文本 (节点 summary + key_points)。kg 为 None 或节点缺失 → 仅列引用。"""
    lines = []
    if kg is not None:
        node = kg.get_node(node_id) if node_id else None
        if node:
            if node.get("summary"):
                lines.append(f"- [{node_id}.summary] {node['summary']}")
            for i, kp in enumerate(node.get("key_points") or []):
                lines.append(f"- [{node_id}.key_points[{i}]] {kp}")
    if not lines:
        lines.append(f"- 图谱事实缺失 (仅声明引用: {', '.join(source_nodes or [node_id])})")
    return "\n".join(lines)


def _build_hallucination_prompt(content: str, facts_text: str, unverified: list = None) -> str:
    claims_block = ""
    if unverified:
        claims = "\n".join(f"- {c}" for c in unverified[:10])
        claims_block = (
            "\n\n## 资源自声明待验证补充 (生成方主动声明的图谱外陈述, 优先核验)\n" + claims
        )
    prompt = _load_prompt("judge_hallucination")
    if prompt:
        return (
            prompt
            + "\n\n## 待判定资源内容\n"
            + "```\n" + content + "\n```\n\n## 图谱事实\n" + facts_text
            + claims_block
        )
    # 内置降级摘要 (prompt 文件缺失时兜底, 语义与文件一致)
    return (
        "你是独立知识质量裁判。判定下列学习资源内容是否全部可溯源至给定图谱事实, "
        "输出 JSON {\"verdict\": \"grounded|hallucinated|unverifiable\", \"reason\": \"...\"}。"
        "资源内容:\n" + content + "\n\n图谱事实:\n" + facts_text + claims_block
    )


def judge_hallucination(resources: list[dict], kg=None, judge_llm=None) -> dict:
    """独立幻觉判定 — 逐条资源: 内容 vs 图谱事实 → grounded/hallucinated/unverifiable。

    Args:
        resources: generated_content.resources 列表 (需含 content, 可含 target_node_id/source_nodes)
        kg: KnowledgeGraph 实例 (取节点事实); None 则仅凭引用判定 (更易 unverifiable)
        judge_llm: 裁判 LLM; None → get_judge_llm()

    Returns:
        {rate, total, grounded, hallucinated, unverifiable, same_source, verdicts}
        rate = hallucinated / total (unverifiable 不计入幻觉, 单独报告)
    """
    judge, same_source = (judge_llm, False) if judge_llm is not None else get_judge_llm()
    resources = resources or []
    verdicts = []
    counts = {"grounded": 0, "hallucinated": 0, "unverifiable": 0}
    # 遍历原始列表, 下标即原始坐标 (issue-04): 旧实现先过滤再 enumerate, resource_index 是
    # 过滤后下标, 与 quality_regen 用原始列表 out 索引不一致 → 含 content="" 资源时定向再生改错资源。
    # 现在仅"跳过"无内容资源本身, 下标保持原始列表位置。
    for i, r in enumerate(resources):
        if not (isinstance(r, dict) and r.get("content")):
            continue
        node_id = r.get("target_node_id", "")
        facts = _node_facts_text(kg, node_id, r.get("source_nodes"))
        unverified = r.get("unverified_claims") if isinstance(r.get("unverified_claims"), list) else None
        result = _invoke_judge(_build_hallucination_prompt(r["content"], facts, unverified), judge)
        verdict = result.get("verdict", "") if isinstance(result, dict) else ""
        if verdict not in counts:
            verdict = "unverifiable"  # 解析失败/非法判定 → 保守计为无法核实
        counts[verdict] += 1
        # 验证依据 + 锚定覆盖双记录 (阶段四): evidence_node_ids 留档可追溯,
        # coverage 评估内容对 key_points 的覆盖 (与 verdict 正交, 非法值兜底 none)
        evidence = result.get("evidence_node_ids") if isinstance(result, dict) else None
        coverage = result.get("coverage") if isinstance(result, dict) else None
        verdicts.append({
            "resource_index": i,
            "content_type": r.get("content_type", ""),
            "target_node_id": node_id,
            "verdict": verdict,
            "evidence_node_ids": [str(n) for n in evidence if n] if isinstance(evidence, list) else [],
            "coverage": coverage if coverage in ("full", "partial", "none") else "none",
            "reason": (result.get("reason", "") if isinstance(result, dict) else "") or "",
        })
    total = len(verdicts)
    rate = round(counts["hallucinated"] / total, 3) if total else 0.0
    return {
        "rate": rate,
        "total": total,
        **counts,
        "same_source": same_source,
        "verdicts": verdicts,
    }


# ---------------------------------------------------------------
# 难度适配判定
# ---------------------------------------------------------------

def _build_difficulty_prompt(content: str) -> str:
    prompt = _load_prompt("judge_difficulty")
    if prompt:
        return prompt + "\n\n## 待判定资源内容\n```\n" + content + "\n```"
    return (
        "你是独立教学内容难度裁判。按 1(入门)-5(专家) 评估下列学习资源的教学难度, "
        "输出 JSON {\"difficulty\": 1, \"reason\": \"...\"}。\n资源内容:\n" + content
    )


def judge_adaptation(resources: list[dict], profile: dict, judge_llm=None) -> dict:
    """独立难度适配判定 — 裁判评资源难度 vs 画像理论水平 (|gap|<=1)。

    Args:
        resources: generated_content.resources 列表
        profile: 用户画像 (取 theory_level, 1-5)
        judge_llm: 裁判 LLM; None → get_judge_llm()

    Returns:
        {rate, matched, total, same_source, judged}
        judged 每条含 {resource_index, content_type, difficulty, matched, reason}
    """
    judge, same_source = (judge_llm, False) if judge_llm is not None else get_judge_llm()
    theory = int((profile or {}).get("theory_level") or 0)
    resources = [r for r in (resources or []) if isinstance(r, dict) and r.get("content")]
    judged = []
    matched = 0
    for i, r in enumerate(resources):
        result = _invoke_judge(_build_difficulty_prompt(r["content"]), judge)
        difficulty = result.get("difficulty") if isinstance(result, dict) else None
        if not isinstance(difficulty, (int, float)) or isinstance(difficulty, bool):
            difficulty = None  # 判定失败
        hit = bool(theory and difficulty is not None and abs(float(difficulty) - theory) <= 1)
        matched += int(hit)
        judged.append({
            "resource_index": i,
            "content_type": r.get("content_type", ""),
            "difficulty": difficulty,
            "matched": hit,
            "reason": (result.get("reason", "") if isinstance(result, dict) else "") or "",
        })
    total = len(resources)
    rate = round(matched / total, 3) if total else 0.0
    return {
        "rate": rate,
        "matched": matched,
        "total": total,
        "same_source": same_source,
        "judged": judged,
    }
