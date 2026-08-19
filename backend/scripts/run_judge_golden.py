"""裁判 golden 真模型回归 (⑥ 附) — 配置 LLM 时对全量 golden 案例跑真实独立裁判。

用法:
  python scripts/run_judge_golden.py                 # 全部案例
  python scripts/run_judge_golden.py --only hallucination
  python scripts/run_judge_golden.py --only difficulty --fail-fast

自包含: 以 golden 内 facts 作为图谱事实 (无需 Neo4j); 用 JUDGE_LLM_* 或主 LLM 判定。
任一案例判定与期望不符 → 非零退出 (提示词/模型口径漂移即红)。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 将 backend 加入路径 (脚本独立运行)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents import quality_judge  # noqa: E402
from app.utils.logging import get_logger  # noqa: E402

logger = get_logger(__name__)

GOLD_PATH = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "judge_goldens.json"


class _FakeKG:
    def __init__(self, nodes: dict):
        self.nodes = nodes

    def get_node(self, node_id):
        return self.nodes.get(node_id)


def _run_hallucination(golden: dict, judge, stop_on_fail: bool) -> int:
    fails = 0
    for case in golden["hallucination"]:
        res = {
            "content": case["content"],
            "target_node_id": next(iter(case["facts"]), ""),
            "source_nodes": list(case["facts"]),
            "content_type": "lecture",
        }
        out = quality_judge.judge_hallucination([res], _FakeKG(case["facts"]), judge_llm=judge)
        actual = out["verdicts"][0]["verdict"]
        ok = actual == case["expected_verdict"]
        fails += 0 if ok else 1
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] hallucination/{case['id']}: expected={case['expected_verdict']} actual={actual}")
        if stop_on_fail and not ok:
            return fails
    return fails


def _run_difficulty(golden: dict, judge, stop_on_fail: bool) -> int:
    fails = 0
    for case in golden["difficulty"]:
        res = {"content": case["content"], "content_type": "lecture"}
        out = quality_judge.judge_adaptation([res], {"theory_level": case["theory_level"]}, judge_llm=judge)
        judged = out["judged"][0]
        actual = judged.get("difficulty")
        expected = case["expected_difficulty"]
        ok = (actual is None and expected == "oops") or actual == expected
        fails += 0 if ok else 1
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] difficulty/{case['id']}: expected={expected} actual={actual} matched={judged['matched']}")
        if stop_on_fail and not ok:
            return fails
    return fails


def main() -> int:
    ap = argparse.ArgumentParser(description="裁判 golden 真模型回归")
    ap.add_argument("--only", choices=("hallucination", "difficulty"), default=None)
    ap.add_argument("--fail-fast", action="store_true")
    args = ap.parse_args()

    golden = json.loads(GOLD_PATH.read_text(encoding="utf-8"))
    judge, _ = quality_judge.get_judge_llm()
    fails = 0
    if args.only in (None, "hallucination"):
        fails += _run_hallucination(golden, judge, args.fail_fast)
    if args.only in (None, "difficulty"):
        fails += _run_difficulty(golden, judge, args.fail_fast)

    print(f"\ngolden 回归完成: 失败 {fails} 条")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
