"""幻觉定向再生 (Judge → Diagnosis-Carrying Regeneration)

独立裁判 (quality_judge.judge_hallucination) 判为 hallucinated 的资源, 携带裁判诊断
(verdict.reason) 重新生成: 修正要求注入 correction_hint, 只重跑被标记的资源 (原位替换),
节点缺失/生成失败时保留原资源 (不丢内容)。

借鉴 J-Space Cognition Suite 的元认知控制原则: "不能改变动作的监控信号只是评论, 不是控制"
—— 裁判判定必须触发再生动作, 而非仅写入报告。

调用方: scripts/run_quality_test.py 离线质量脚本 (不入交互路径, 不增线上延迟)。
"""

from concurrent.futures import ThreadPoolExecutor

from app.agents.content_generator import _generate_one
from app.agents.llm import _current_overrides, safe_llm_call
from app.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

# 再生上限 (控量: 离线脚本每次运行最多再生资源数, 与 MAX_NODES_TO_GENERATE 对齐)
MAX_REGENS = 3

# adaptation_profile → theory_level 反映射 (对齐 _adaptation_label 的 <=2/<=4/其他 分段)
_PROFILE_TO_LEVEL = {"beginner": 2, "intermediate": 3, "advanced": 5}


def regenerate_flagged(resources: list[dict], hallucination_result: dict, kg) -> dict:
    """对判为 hallucinated 的资源定向再生 (judge reason 作为修正提示)。

    Args:
        resources: generated_content.resources 列表
        hallucination_result: judge_hallucination 的返回 (取 verdicts)
        kg: KnowledgeGraph 实例 (取节点事实; None 时全部跳过)

    Returns:
        {
            "resources": 再生后的资源列表 (原位替换, 顺序不变),
            "regenerated_count": 实际再生数,
            "regen_indexes": 被替换的资源下标列表,
            "failures": 再生失败数 (节点缺失/LLM 失败, 保留原资源),
        }
    """
    out = [r for r in (resources or [])]
    verdicts = [v for v in (hallucination_result or {}).get("verdicts", [])
                if isinstance(v, dict) and v.get("verdict") == "hallucinated"]

    # 按 resource_index 去重 (畸形重复 verdict 不致同一槽位再生两次, 保护调用方 before/after 算术)
    flagged_by_index: dict[int, dict] = {}
    for v in verdicts[:MAX_REGENS]:
        i = v.get("resource_index")
        if isinstance(i, int) and 0 <= i < len(out) and isinstance(out[i], dict):
            flagged_by_index.setdefault(i, v)
    flagged = list(flagged_by_index.items())

    if not flagged or kg is None:
        return {"resources": out, "regenerated_count": 0, "regen_indexes": [],
                "failures": len(flagged) if kg is None else 0}

    overrides = _current_overrides.get()  # Spec B: worker 内重设 (ContextVar 不跨线程)

    def _regen_one(item):
        i, v = item
        r = out[i]
        node = kg.get_node(r.get("target_node_id", ""))
        if not node:
            return None
        level = _PROFILE_TO_LEVEL.get(r.get("adaptation_profile", ""), 2)
        hint = (v.get("reason") or "").strip() or "上轮裁判判定存在幻觉, 请严格依据节点事实重新生成"
        ok, res = safe_llm_call(
            _generate_one, node, level, r.get("content_type", "lecture"), hint,
            overrides=overrides, logger=logger,
            label=f"regen node={r.get('target_node_id')} type={r.get('content_type')}",
        )
        return (i, res) if ok else None

    # max(1, ...) 防 CONTENT_GEN_CONCURRENCY=0 时 ThreadPoolExecutor 抛 ValueError
    max_workers = max(1, min(settings.CONTENT_GEN_CONCURRENCY, len(flagged)))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        results = list(pool.map(_regen_one, flagged))

    regen_indexes = []
    failures = 0
    for item in results:
        if item and isinstance(item[1], dict) and item[1].get("content"):
            i, res = item
            out[i] = res  # 原位替换, 顺序稳定
            regen_indexes.append(i)
        else:
            failures += 1  # 节点缺失/LLM 失败/空内容 → 保留原资源

    logger.info("幻觉定向再生: flagged=%d regenerated=%d failures=%d",
                len(flagged), len(regen_indexes), failures)
    return {
        "resources": out,
        "regenerated_count": len(regen_indexes),
        "regen_indexes": regen_indexes,
        "failures": failures,
    }
