"""题库完整性防回归测试 (issue-67)。

复用 scripts/audit_question_bank.py 的加载逻辑 (题库文件走 read 得到的事实),
断言关键指标防退化: 题量/覆盖节点/答案与解析完备率/题型多样性/qid 唯一。
"""
import importlib.util
from collections import Counter
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "audit_question_bank.py"
spec = importlib.util.spec_from_file_location("audit_question_bank", SCRIPT)
audit = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(audit)

BASE_DOMAINS = ("PY", "DA", "DB", "EN", "WD", "ML")


def _load():
    return list(audit.iter_questions(audit.QUESTIONS_DIR))


def test_bank_nonempty_and_covers_core_nodes():
    questions = _load()
    assert len(questions) >= 600, f"题库总量退化: {len(questions)}"
    node_ids = {(q.get("node_id") or q.get("source_node_id") or "") for q in questions}
    node_ids.discard("")
    assert len(node_ids) >= 200, f"覆盖节点退化: {len(node_ids)}"


def test_base_domain_coverage():
    """基座 6 域 (PY/DA/DB/EN/WD/ML) 每域题量 >= 20。"""
    questions = _load()
    domains = Counter()
    for q in questions:
        nid = q.get("node_id") or q.get("source_node_id") or ""
        m = audit.NODE_RE.match(nid or "")
        if m:
            domains[m.group(1)] += 1
    for d in BASE_DOMAINS:
        assert domains.get(d, 0) >= 20, f"域 {d} 题量不足: {domains.get(d, 0)}"


def test_answers_and_explanations_complete():
    """每题必须带 answer + explanation (解析完备性)。"""
    questions = _load()
    no_ans = [q.get("qid") for q in questions if not (q.get("answer") or "").strip()]
    no_exp = [q.get("qid") for q in questions if not (q.get("explanation") or "").strip()]
    assert not no_ans, f"缺答案的题: {no_ans[:10]}"
    assert not no_exp, f"缺解析的题: {no_exp[:10]}"


def test_question_types_diverse():
    """题型多样性: choice/fill/code 均存在 (难度梯度依赖多题型)。"""
    questions = _load()
    types = Counter(q.get("type") for q in questions)
    for t in ("choice", "fill", "code"):
        assert types.get(t, 0) > 0, f"题型 {t} 缺失, 分布: {dict(types)}"


def test_qid_unique():
    questions = _load()
    qids = [q.get("qid") for q in questions if q.get("qid")]
    dup = [q for q, c in Counter(qids).items() if c > 1]
    assert not dup, f"重复 qid: {dup[:10]}"
