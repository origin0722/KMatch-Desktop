#!/usr/bin/env python
"""题库审计脚本 (issue-67): 每域/总览统计 + 完整性校验。

用法:
    python scripts/audit_question_bank.py            # 打印统计, 有完整性违规时 exit 1
    python scripts/audit_question_bank.py --json     # 输出 JSON 摘要

校验项:
  - 每题含 node_id / answer / explanation / type
  - qid 唯一
  - 题型多样性 (choice/fill/code 至少各存在)
  - 每域题量下限 (基座 6 域各 >= 20)
"""
import argparse
import collections
import json
import re
import sys
from pathlib import Path

KB = Path(__file__).resolve().parent.parent.parent / "data" / "knowledge_base"
QUESTIONS_DIR = KB / "questions"

TYPE_LABELS = {"choice": "选择题", "fill": "填空题", "code": "代码题", "judge": "判断题"}
BASE_DOMAINS = ("PY", "DA", "DB", "EN", "WD", "ML")
DOMAIN_LABELS = {
    "PY": "Python基础", "DA": "数据分析", "DB": "数据库", "EN": "工程化",
    "WD": "Web后端", "ML": "机器学习",
}
NODE_RE = re.compile(r"^([A-Z]{2})-\d{3}$")


def iter_questions(root: Path):
    for p in sorted(root.rglob("*.json")):
        if p.name == "schema.json":
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        items = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            if isinstance(data.get("questions"), list):
                items = data["questions"]
            elif data.get("question"):
                items = [data]
        for q in items:
            if isinstance(q, dict) and q.get("question"):
                yield q


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="输出 JSON 摘要")
    args = ap.parse_args()

    questions = list(iter_questions(QUESTIONS_DIR))
    types = collections.Counter(q.get("type", "?") for q in questions)
    domains = collections.Counter()
    node_counts = collections.Counter()
    difficulties = collections.Counter()
    qids = set()
    dup_qids = []
    missing = collections.defaultdict(list)
    unknown_types = []

    for q in questions:
        # 兼容两类题库文件: PY 根域用 node_id, DA/DB/EN/WD/ML 用 source_node_id
        nid = q.get("node_id") or q.get("source_node_id") or ""
        m = NODE_RE.match(nid or "")
        prefix = m.group(1) if m else ("?" if nid else "(无节点)")
        domains[prefix] += 1
        if nid:
            node_counts[nid] += 1
        for field in ("node_id", "answer", "explanation"):
            if field == "node_id":
                present = bool((q.get("node_id") or q.get("source_node_id") or "").strip())
            else:
                present = bool((q.get(field) or "").strip())
            if not present:
                missing[field].append(q.get("qid") or q.get("question", "")[:24])
        qid = q.get("qid")
        if qid:
            if qid in qids:
                dup_qids.append(qid)
            qids.add(qid)
        t = q.get("type")
        if t not in TYPE_LABELS:
            unknown_types.append(t)
        difficulties[q.get("difficulty")] += 1

    violations = []
    if missing["answer"]:
        violations.append(f"缺 answer {len(missing['answer'])} 题")
    if missing["explanation"]:
        violations.append(f"缺 explanation {len(missing['explanation'])} 题")
    if missing["node_id"]:
        violations.append(f"缺 node_id {len(missing['node_id'])} 题")
    if dup_qids:
        violations.append(f"重复 qid {len(dup_qids)} 个: {dup_qids[:5]}")
    if unknown_types:
        violations.append(f"未知题型 {sorted(set(map(str, unknown_types)))}")
    low_domains = [d for d in BASE_DOMAINS if domains.get(d, 0) < 20]
    if low_domains:
        violations.append(f"基座域题量不足 20: {low_domains}")
    if not (types.get("choice") and types.get("fill") and types.get("code")):
        violations.append("题型多样性不足 (choice/fill/code 需各存在)")

    summary = {
        "总题数": len(questions),
        "题型分布": {TYPE_LABELS.get(k, k): v for k, v in types.most_common()},
        "域分布": {DOMAIN_LABELS.get(k, k): v for k, v in domains.most_common()},
        "覆盖节点数": len(node_counts),
        "难度分布": {str(k): v for k, v in sorted(difficulties.items(), key=lambda kv: (kv[0] is None, kv[0] or 0))},
        "题量最少节点(前5)": node_counts.most_common()[-5:],
    }

    if args.json:
        print(json.dumps({"summary": summary, "violations": violations}, ensure_ascii=False, indent=2))
    else:
        print("=== KMatch 题库审计 ===")
        for k, v in summary.items():
            print(f"{k}: {v}")
        print(f"\n完整性校验: {'PASS' if not violations else 'FAIL'}")
        for v in violations:
            print(f"  - {v}")

    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
