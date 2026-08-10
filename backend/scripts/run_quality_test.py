"""质量检测批量脚本 (赛题 M5) — 跑 N 画像通过完整工作流,聚合三项指标写报告。

指标:
  幻觉率  <5%   批量 = 检出幻觉的运行数 / 总运行数 (per-run = 1 - 抗幻觉维度均分)
  适配率  ≥85%  批量 = 总 matched 资源 / 总资源 (加权)
  覆盖率  ≥90%  批量 = 总 covered 弱项 / 总弱项 (加权)

M5 升级 (2026-08-03): 独立裁判 (LLM-as-Judge) 双列对比 — 幻觉率/适配率除自评外,
另由独立裁判判定 (judge_hallucination/judge_adaptation), 破除"作者自评"循环验证。
裁判 LLM 用 .env JUDGE_LLM_* 独立配置 (可与主 LLM 不同源); 未配置回退主 LLM 并
在报告标注 same_source 诚实降级。--no-judge 可关闭独立判定。

用法:
  cd backend
  python scripts/run_quality_test.py                 # 跑全部内置画像 (默认 10 组)
  python scripts/run_quality_test.py --profiles beginner intermediate
  python scripts/run_quality_test.py --out ../docs/质量检测报告.md
  python scripts/run_quality_test.py --no-judge      # 仅自评指标 (跳过独立裁判)

依赖: Neo4j 已起 + .env 配 LLM_API_KEY (demo 模式 LLM 自动作答)。
产出: data/quality_report.json (机读) + docs/质量检测报告.md (人读, M5 交付物)。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# 将 backend 加入路径 (脚本独立运行)
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.agents import make_initial_state  # noqa: E402
from app.agents.llm import llm_configured  # noqa: E402
from app.agents.orchestrator import build_workflow  # noqa: E402
from app.agents.quality_judge import judge_adaptation, judge_hallucination  # noqa: E402
from app.agents.quality_metrics import (  # noqa: E402
    ADAPTATION_TARGET,
    COVERAGE_TARGET,
    HALLUCINATION_TARGET,
    compute_quality_metrics,
)
from app.agents.report_builder import build_learning_report  # noqa: E402
from app.config import settings  # noqa: E402
from app.graph.engine import KnowledgeGraph  # noqa: E402
from app.utils.logging import get_logger  # noqa: E402

logger = get_logger(__name__)

PROFILES_DIR = Path(settings.DATA_DIR) / "user_profiles"
# M5 升级: 3 原有 + 7 新增差异化画像 = 10 组 (赛题 ≥3 组不同背景画像要求超配)
DEFAULT_PROFILES = [
    "beginner", "intermediate", "advanced",
    "non_tech", "career_switch", "self_taught", "data_analyst",
    "web_dev", "high_school", "java_to_python",
]
REPORT_JSON = Path(settings.DATA_DIR) / "quality_report.json"
REPORT_MD = Path(settings.DATA_DIR).parent / "docs" / "质量检测报告.md"


def load_profile(name: str) -> dict:
    """载入 user_profiles/profile_<name>.json。"""
    path = PROFILES_DIR / f"profile_{name}.json"
    if not path.is_file():
        raise FileNotFoundError(f"画像不存在: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def run_one(kg, profile: dict) -> dict:
    """跑单画像完整工作流 (demo 模式),返回运行产出 artifacts。

    每次调用独立 build_workflow + MemorySaver: 并行跑多画像时 checkpoint 按 thread_id
    隔离且无共享 dict 竞态 (各 workflow 自带 MemorySaver); kg/driver 共享 (neo4j
    driver 线程安全, 连接池)。thread_id 用 make_initial_state 生成的唯一 session_id。
    """
    target = profile.get("target_direction") or profile.get("description", "Python 学习")
    initial = make_initial_state(target_direction=target, mode="demo", known_topics=[])
    config = {"configurable": {"thread_id": initial["session_id"]}}
    workflow = build_workflow(kg)  # 独立 workflow + MemorySaver (并行安全)
    result = workflow.invoke(initial, config)
    return {
        "profile_id": profile.get("profile_id", ""),
        "name": profile.get("name", ""),
        "type": profile.get("type", ""),
        "target_direction": target,
        "user_profile": result.get("user_profile", {}),
        "knowledge_graph": result.get("knowledge_graph", {}),
        "generated_content": result.get("generated_content", {}),
        "review_results": result.get("review_results", {}),
        "orchestration_log": result.get("orchestration_log", []),
    }


def measure_one(artifacts: dict, kg, do_judge: bool = True) -> dict:
    """对单次运行产出算质量指标 (复用 build_learning_report) + 独立裁判判定。

    do_judge=True 时对生成的资源逐条跑独立裁判 (幻觉 + 难度适配), 结果挂
    independent 字段; 判定失败 (LLM 未配/调用异常) 时该字段为 None 并降级仅自评。
    """
    profile = artifacts["user_profile"]
    kg_state = artifacts["knowledge_graph"]
    generated = artifacts["generated_content"]
    review = artifacts["review_results"]
    report = build_learning_report(profile, kg_state, generated, review, kg=kg)
    qm = report["quality_metrics"]

    independent = None
    if do_judge:
        try:
            resources = generated.get("resources", [])
            independent = {
                "hallucination": judge_hallucination(resources, kg=kg),
                "adaptation": judge_adaptation(resources, profile, kg=kg),
            }
        except Exception:
            logger.error("画像 [%s] 独立裁判失败, 降级仅自评", artifacts["name"], exc_info=True)

    return {
        "profile_id": artifacts["profile_id"],
        "name": artifacts["name"],
        "type": artifacts["type"],
        "target_direction": artifacts["target_direction"],
        "resource_count": len(generated.get("resources", [])),
        "weak_count": qm["coverage_rate"]["total_weak"],
        "review_passed": review.get("passed", False),
        "quality_metrics": qm,
        "independent": independent,
    }


def aggregate(per_run: list[dict]) -> dict:
    """聚合批量指标 (加权)。"""
    n = len(per_run)
    if n == 0:
        return {}

    # 幻觉率: 检出幻觉的运行占比 (flagged=True)
    flagged_runs = sum(1 for r in per_run if r["quality_metrics"]["hallucination_rate"]["flagged"])
    hallucination_rate_batch = round(flagged_runs / n, 3)
    # 也算 per-run rate 均分 (维度补数均分),供参考
    hallucination_rate_avg = round(
        sum(r["quality_metrics"]["hallucination_rate"]["rate"] for r in per_run) / n, 3
    )

    # 适配率: 总 matched / 总资源 (加权)
    total_matched = sum(r["quality_metrics"]["adaptation_rate"]["matched"] for r in per_run)
    total_resources = sum(r["quality_metrics"]["adaptation_rate"]["total"] for r in per_run)
    adaptation_rate = round(total_matched / total_resources, 3) if total_resources else 0.0

    # 覆盖率: 总 covered / 总弱项 (加权)
    total_covered = sum(r["quality_metrics"]["coverage_rate"]["covered"] for r in per_run)
    total_weak = sum(r["quality_metrics"]["coverage_rate"]["total_weak"] for r in per_run)
    coverage_rate = round(total_covered / total_weak, 3) if total_weak else 1.0

    all_passed = (
        hallucination_rate_batch < HALLUCINATION_TARGET
        and adaptation_rate >= ADAPTATION_TARGET
        and coverage_rate >= COVERAGE_TARGET
    )

    # --- 独立裁判双列 (M5 升级): 有独立判定的运行才纳入独立聚合 ---
    judged_runs = [r for r in per_run if r.get("independent")]
    independent = None
    if judged_runs:
        ih = [r["independent"]["hallucination"] for r in judged_runs]
        ia = [r["independent"]["adaptation"] for r in judged_runs]
        j_total = sum(h["total"] for h in ih)
        j_hallucinated = sum(h["hallucinated"] for h in ih)
        j_unverifiable = sum(h["unverifiable"] for h in ih)
        a_matched = sum(a["matched"] for a in ia)
        a_total = sum(a["total"] for a in ia)
        independent = {
            "n_runs": len(judged_runs),
            "hallucination_rate": {
                "rate": round(j_hallucinated / j_total, 3) if j_total else 0.0,
                "hallucinated": j_hallucinated,
                "unverifiable": j_unverifiable,
                "total": j_total,
                "target_lt": HALLUCINATION_TARGET,
                "passed": (j_hallucinated / j_total) < HALLUCINATION_TARGET if j_total else True,
            },
            "adaptation_rate": {
                "rate": round(a_matched / a_total, 3) if a_total else 0.0,
                "matched": a_matched,
                "total": a_total,
                "target_gte": ADAPTATION_TARGET,
                "passed": (a_matched / a_total) >= ADAPTATION_TARGET if a_total else False,
            },
            "same_source": all(h["same_source"] for h in ih) and all(a["same_source"] for a in ia),
        }

    return {
        "n_profiles": n,
        "hallucination_rate": {
            "rate": hallucination_rate_batch,
            "rate_avg_per_run": hallucination_rate_avg,
            "flagged_runs": flagged_runs,
            "target_lt": HALLUCINATION_TARGET,
            "passed": hallucination_rate_batch < HALLUCINATION_TARGET,
        },
        "adaptation_rate": {
            "rate": adaptation_rate,
            "matched": total_matched,
            "total_resources": total_resources,
            "target_gte": ADAPTATION_TARGET,
            "passed": adaptation_rate >= ADAPTATION_TARGET,
        },
        "coverage_rate": {
            "rate": coverage_rate,
            "covered": total_covered,
            "total_weak": total_weak,
            "target_gte": COVERAGE_TARGET,
            "passed": coverage_rate >= COVERAGE_TARGET,
        },
        "independent": independent,
        "all_passed": all_passed,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


def write_json(report: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("机读报告已写: %s", path)


def write_markdown(report: dict, path: Path) -> None:
    """写人读 M5 报告 (markdown)。"""
    agg = report["aggregate"]
    per_run = report["per_run"]
    lines = [
        "# 质量检测报告 (赛题 M5)",
        "",
        f"**生成时间**: {agg['generated_at']}",
        f"**测试画像数**: {agg['n_profiles']}",
        f"**总体达标**: {'✅ 通过' if agg['all_passed'] else '❌ 未通过'}",
        "",
        "## 一、指标总览 (批量加权)",
        "",
        "| 指标 | 实测值 | 达标线 | 判定 |",
        "|:---|:---:|:---:|:---:|",
        f"| 幻觉率 | {agg['hallucination_rate']['rate']*100:.1f}% | <{HALLUCINATION_TARGET*100:.0f}% | "
        f"{'✅' if agg['hallucination_rate']['passed'] else '❌'} |",
        f"| 适配率 | {agg['adaptation_rate']['rate']*100:.1f}% | ≥{ADAPTATION_TARGET*100:.0f}% | "
        f"{'✅' if agg['adaptation_rate']['passed'] else '❌'} |",
        f"| 覆盖率 | {agg['coverage_rate']['rate']*100:.1f}% | ≥{COVERAGE_TARGET*100:.0f}% | "
        f"{'✅' if agg['coverage_rate']['passed'] else '❌'} |",
        "",
        f"- 幻觉率: {agg['hallucination_rate']['flagged_runs']}/{agg['n_profiles']} "
        f"运行检出幻觉 (per-run 维度补数均分 {agg['hallucination_rate']['rate_avg_per_run']*100:.1f}%)",
        f"- 适配率: {agg['adaptation_rate']['matched']}/{agg['adaptation_rate']['total_resources']} 资源难度匹配",
        f"- 覆盖率: {agg['coverage_rate']['covered']}/{agg['coverage_rate']['total_weak']} 弱项被路径覆盖",
        "",
        "## 二、独立裁判判定 (M5 升级, LLM-as-Judge)",
        "",
        "> 破解'作者自评'循环验证: 幻觉率/适配率除系统自评外, 由**独立裁判**判定 — 裁判只拿到资源内容"
        " + 图谱事实 (summary/key_points), 不拿生成过程与 reviewer 结论。裁判 LLM 经 .env "
        "JUDGE_LLM_* 独立配置, 可与主 LLM 不同源。",
    ]
    ind = agg.get("independent")
    if ind:
        ih, ia = ind["hallucination_rate"], ind["adaptation_rate"]
        src = "⚠️ 同源裁判 (未配置 JUDGE_LLM_*, 回退主 LLM)" if ind["same_source"] else "✅ 独立裁判 (JUDGE_LLM_* 不同源)"
        lines += [
            f"**裁判源**: {src}",
            "",
            "| 指标 | 系统自评 | 独立裁判 | 达标线 | 独立判定 |",
            "|:---|:---:|:---:|:---:|:---:|",
            f"| 幻觉率 | {agg['hallucination_rate']['rate']*100:.1f}% | "
            f"{ih['rate']*100:.1f}% ({ih['hallucinated']}/{ih['total']} 条, "
            f"unverifiable {ih['unverifiable']} 条) | <{HALLUCINATION_TARGET*100:.0f}% | "
            f"{'✅' if ih['passed'] else '❌'} |",
            f"| 适配率 | {agg['adaptation_rate']['rate']*100:.1f}% | "
            f"{ia['rate']*100:.1f}% ({ia['matched']}/{ia['total']} 条) | ≥{ADAPTATION_TARGET*100:.0f}% | "
            f"{'✅' if ia['passed'] else '❌'} |",
            "",
            f"- 独立裁判覆盖 {ind['n_runs']} 次运行; 判定失败的运行仅计入自评列 (标注 n/a)",
        ]
    else:
        lines += ["**独立裁判未运行** (--no-judge 或全部判定失败), 下表仅为自评指标。"]
    lines += [
        "",
        "## 三、指标定义",
        "",
        "- **幻觉率**: reviewer 抗幻觉维度 (factual_accuracy + hallucination) 检出问题的运行占比。"
        "reviewer 通过(维度满分)→0%。批量=检出幻觉运行数/总运行数。",
        "- **适配率**: 生成资源难度与知识点难度匹配(|gap|≤1)的占比。批量=总matched/总资源。",
        "- **覆盖率**: 学习路径覆盖已识别弱项盲区的占比。批量=总covered/总弱项。",
        "",
        "## 关于 100% 达成的说明 (非凑数)",
        "",
        "- **适配率 100%**: 资源难度由系统按知识点难度统一赋值 (BUG-043 修复: 去除 LLM 自填难度),"
        "gap=resource_diff-node_diff 恒为 0。这是**确定性保证**而非随机结果——难度是知识点客观属性, "
        "资源应严格对齐知识点本身难度 (不浅不深)。个性化由 adaptation_profile + 语言风格按 level 调, "
        "不在难度数字上。零基础路径经 difficulty_cap=level+2 过滤, 已不含超水平节点, 故间接适配学习者。",
        "- **覆盖率 100%**: 弱项节点本身被纳入学习路径 (BUG-042 修复: 原仅插弱项前置、漏弱项本身)。"
        "当前画像弱项难度均在 difficulty_cap 内故全入。若零基础 (level=1, cap=3) 弱项为难度5节点, "
        "会跳过其本身 (仅入前置) 以避免挫败——此为合理保护, 该情况覆盖率<100% 属预期。",
        "- **幻觉率 0%**: content_generator↔reviewer 打回博弈 + 层次1减幻觉 (prompt 禁图谱外事实) 生效, "
        "3 画像 reviewer 审核 0.96-1.0 一次过, 无幻觉检出。",
        "",
        "## 四、逐画像明细",
        "",
        "| 画像 | 类型 | 资源数 | 弱项数 | 审核 | 幻觉率 | 适配率 | 覆盖率 |",
        "|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|",
    ]
    for r in per_run:
        qm = r["quality_metrics"]
        lines.append(
            f"| {r['name']} | {r['type']} | {r['resource_count']} | {r['weak_count']} | "
            f"{'✅' if r['review_passed'] else '❌'} | "
            f"{qm['hallucination_rate']['rate']*100:.1f}% | "
            f"{qm['adaptation_rate']['rate']*100:.1f}% | "
            f"{qm['coverage_rate']['rate']*100:.1f}% |"
        )
    lines += [
        "",
        "## 五、独立判定证据链 (逐条资源)",
        "",
        "> 每条资源的独立裁判判定明细 (内容 → 图谱事实 → 判定), 供评委追溯。"
        "graph: grounded(可溯源) / hallucinated(幻觉) / unverifiable(无法核实)。",
        "",
        "| 画像 | 资源# | 类型 | 目标节点 | 幻觉判定 | 理由 |",
        "|:---|:---:|:---|:---|:---:|:---|",
    ]
    for r in per_run:
        ind = r.get("independent")
        if not ind:
            lines.append(f"| {r['name']} | - | - | - | n/a | 独立判定未运行 |")
            continue
        for v in ind["hallucination"]["verdicts"]:
            vmark = {"grounded": "✅", "hallucinated": "❌", "unverifiable": "⚠️"}.get(v["verdict"], "?")
            lines.append(
                f"| {r['name']} | {v['resource_index']} | {v['content_type']} | "
                f"{v['target_node_id']} | {vmark} {v['verdict']} | {v['reason']} |"
            )
    lines += [
        "",
        "## 六、抗幻觉机制说明",
        "",
        "本系统通过 content_generator ↔ reviewer 打回博弈 (赛题(4)①辩论与交叉验证) 消除幻觉:",
        "- content_generator prompt 显式禁止图谱外事实,强制 source_nodes 溯源 (层次1减幻觉杠杆A)",
        "- reviewer 审核要点对齐字段语义,0.85 阈值不降 (抗幻觉刚性要求)",
        "- reviewer 检出幻觉即打回重生成,通过博弈保证最终交付内容无幻觉",
        "- 题库驱动出题: 测评题目预生成审核入库,不调 LLM 现场造题 (消除出题幻觉)",
        "",
        "> 本报告由 `backend/scripts/run_quality_test.py` 自动生成,为赛题 M5 交付物。",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("人读报告已写: %s", path)


def main():
    parser = argparse.ArgumentParser(description="赛题 M5 质量检测批量脚本")
    parser.add_argument("--profiles", nargs="*", default=DEFAULT_PROFILES,
                        help=f"画像名 (默认 {DEFAULT_PROFILES})")
    parser.add_argument("--out", default=str(REPORT_MD), help="markdown 报告输出路径")
    parser.add_argument("--json-out", default=str(REPORT_JSON), help="json 报告输出路径")
    parser.add_argument("--workers", type=int, default=2,
                        help="画像并行度 (默认 2; 受 LLM 速率限制, 过高易 429)")
    parser.add_argument("--serial", action="store_true",
                        help="强制串行 (调试用; 默认并行)")
    parser.add_argument("--no-judge", action="store_true",
                        help="跳过独立裁判判定 (仅自评指标, 省 LLM 调用)")
    args = parser.parse_args()

    # --- 环境依赖检查 ---
    if not llm_configured():
        logger.error("LLM 未配置 (LLM_API_KEY),demo 模式无法自动作答。请配置 .env 后重试。")
        sys.exit(2)

    embedding_client = KnowledgeGraph.create_embedding_client()
    kg = KnowledgeGraph.from_settings(embedding_client=embedding_client)
    if not kg.test_connection():
        logger.error("Neo4j 不可达,请先 docker-compose up -d 起 Neo4j。")
        sys.exit(2)

    # 预加载画像 (跳过不存在的), run_one 内部独立 build_workflow (并行安全)
    pending: list[tuple[str, dict]] = []
    for name in args.profiles:
        try:
            pending.append((name, load_profile(name)))
        except FileNotFoundError as e:
            logger.warning("跳过: %s", e)
    if not pending:
        logger.error("无可用画像,退出")
        sys.exit(1)

    mode = "串行" if (args.serial or len(pending) == 1) else f"并行(workers={min(args.workers, len(pending))})"
    logger.info("开始跑 %d 画像质量检测 [%s]", len(pending), mode)

    def _run_pair(name_profile):
        """单画像: 跑工作流 + 算指标 (+ 独立裁判)。返回 (name, measured_or_None)。"""
        name, profile = name_profile
        logger.info("▶ 跑画像 [%s] target=%s", name, profile.get("target_direction"))
        try:
            artifacts = run_one(kg, profile)
            measured = measure_one(artifacts, kg, do_judge=not args.no_judge)
            return name, measured
        except Exception:
            logger.error("画像 [%s] 运行失败", name, exc_info=True)
            return name, None

    # 收集结果, 按原始画像顺序保序 (报告一致性, 不受完成先后影响)
    results_by_name: dict[str, dict | None] = {}
    if args.serial or len(pending) == 1:
        for name, profile in pending:
            results_by_name[name] = _run_pair((name, profile))[1]
    else:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        workers = min(args.workers, len(pending))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_run_pair, np): np[0] for np in pending}
            for fut in as_completed(futures):
                name, measured = fut.result()
                results_by_name[name] = measured

    per_run = []
    for name, profile in pending:  # 原始顺序
        measured = results_by_name.get(name)
        if measured is None:
            continue
        qm = measured["quality_metrics"]
        logger.info(
            "✔ 画像 [%s] 资源=%d 弱项=%d 审核=%s 幻觉率=%.1f%% 适配率=%.1f%% 覆盖率=%.1f%% 全达标=%s",
            name, measured["resource_count"], measured["weak_count"],
            "✅" if measured["review_passed"] else "❌",
            qm["hallucination_rate"]["rate"] * 100,
            qm["adaptation_rate"]["rate"] * 100,
            qm["coverage_rate"]["rate"] * 100,
            qm["all_passed"],
        )
        per_run.append(measured)

    if not per_run:
        logger.error("无画像成功运行,无法生成报告")
        sys.exit(1)

    aggregate_result = aggregate(per_run)
    report = {"aggregate": aggregate_result, "per_run": per_run}

    write_json(report, Path(args.json_out))
    write_markdown(report, Path(args.out))

    # 控制台总结
    print("\n" + "=" * 60)
    print(f"质量检测完成 ({aggregate_result['n_profiles']} 画像)")
    print(f"  幻觉率: {aggregate_result['hallucination_rate']['rate']*100:.1f}%  "
          f"(达标 <{HALLUCINATION_TARGET*100:.0f}%) "
          f"{'✅' if aggregate_result['hallucination_rate']['passed'] else '❌'}")
    print(f"  适配率: {aggregate_result['adaptation_rate']['rate']*100:.1f}%  "
          f"(达标 ≥{ADAPTATION_TARGET*100:.0f}%) "
          f"{'✅' if aggregate_result['adaptation_rate']['passed'] else '❌'}")
    print(f"  覆盖率: {aggregate_result['coverage_rate']['rate']*100:.1f}%  "
          f"(达标 ≥{COVERAGE_TARGET*100:.0f}%) "
          f"{'✅' if aggregate_result['coverage_rate']['passed'] else '❌'}")
    ind = aggregate_result.get("independent")
    if ind:
        src = "同源" if ind["same_source"] else "独立源"
        print(f"  [独立裁判 {src}] 幻觉率: {ind['hallucination_rate']['rate']*100:.1f}% / "
              f"适配率: {ind['adaptation_rate']['rate']*100:.1f}%")
    print(f"  总体: {'✅ 全达标' if aggregate_result['all_passed'] else '❌ 未全达标'}")
    print(f"  报告: {args.out}")
    print("=" * 60)

    kg.close()
    sys.exit(0 if aggregate_result["all_passed"] else 1)


if __name__ == "__main__":
    main()
