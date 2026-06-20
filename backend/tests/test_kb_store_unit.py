"""kb_store 单测 — JSON 定位/读写/ID 生成/并发, 用 tmp_path 不碰真实数据。"""

import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.data import kb_store


def _make_base(tmp_path):
    """构造知识库根目录 (含 nodes 节点文件 + questions/ 目录)。"""
    base = tmp_path / "knowledge_base"
    (base / "nodes").mkdir(parents=True)
    (base / "questions").mkdir()
    # schema.json (应被排除)
    (base / "schema.json").write_text('{"required": []}', encoding="utf-8")
    (base / "questions" / "schema.json").write_text('{"title": "题目规范"}', encoding="utf-8")
    return base


def _node(nid="PY-001", name="变量", **kw):
    n = {
        "id": nid, "name": name, "difficulty": 1, "category": "基础语法",
        "summary": "x" * 30, "prerequisites": [], "key_points": ["a", "b", "c"],
        "practice_questions": [{"type": "choice", "question": "q", "answer": "A"}],
        "common_mistakes": ["m1"], "tags": ["t"], "estimated_minutes": 20,
    }
    n.update(kw)
    return n


def _q(qid="Q-PY001-001", source="PY-001", **kw):
    q = {"qid": qid, "source_node_id": source, "type": "choice",
         "question": "题干xxxxx", "options": ["A", "B"], "answer": "A", "difficulty": 2}
    q.update(kw)
    return q


# ============================================================
# 节点定位/读写
# ============================================================

def test_find_node_locates_existing(tmp_path):
    base = _make_base(tmp_path)
    (base / "nodes" / "PY-001_005.json").write_text(
        json.dumps([_node("PY-001"), _node("PY-002", "函数")], ensure_ascii=False),
        encoding="utf-8")
    found = kb_store.find_node_file(base, "PY-002")
    assert found is not None
    path, idx = found
    assert idx == 1


def test_find_node_missing_returns_none(tmp_path):
    base = _make_base(tmp_path)
    assert kb_store.find_node_file(base, "PY-999") is None


def test_find_node_skips_questions_dir_and_schema(tmp_path):
    """questions/ 和 schema.json 不被当节点文件。"""
    base = _make_base(tmp_path)
    (base / "questions" / "PY-001.json").write_text(
        json.dumps([_q()], ensure_ascii=False), encoding="utf-8")
    # 没有节点文件, 只有问题文件 → 找节点应返回 None
    assert kb_store.find_node_file(base, "PY-001") is None


def test_load_node_reads_existing(tmp_path):
    base = _make_base(tmp_path)
    (base / "nodes" / "PY-001.json").write_text(
        json.dumps([_node("PY-001", name="变量与类型")], ensure_ascii=False), encoding="utf-8")
    n = kb_store.load_node(base, "PY-001")
    assert n is not None
    assert n["name"] == "变量与类型"


def test_save_node_new_appends_to_manual_file(tmp_path):
    base = _make_base(tmp_path)
    kb_store.save_node(base, _node("PY-093", name="新节点"))
    manual = base / "nodes" / "_manual_nodes.json"
    assert manual.is_file()
    data = json.loads(manual.read_text(encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["id"] == "PY-093"


def test_save_node_existing_replaces_in_place(tmp_path):
    base = _make_base(tmp_path)
    fpath = base / "nodes" / "PY-001.json"
    fpath.write_text(json.dumps([_node("PY-001", name="旧名")], ensure_ascii=False), encoding="utf-8")
    kb_store.save_node(base, _node("PY-001", name="新名"))
    data = json.loads(fpath.read_text(encoding="utf-8"))
    assert data[0]["name"] == "新名"
    assert len(data) == 1  # 不重复追加


def test_delete_node_removes_from_array(tmp_path):
    base = _make_base(tmp_path)
    fpath = base / "nodes" / "PY-001.json"
    fpath.write_text(json.dumps([_node("PY-001"), _node("PY-002", "函数")], ensure_ascii=False),
                     encoding="utf-8")
    assert kb_store.delete_node(base, "PY-001") is True
    data = json.loads(fpath.read_text(encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["id"] == "PY-002"


def test_delete_node_missing_returns_false(tmp_path):
    base = _make_base(tmp_path)
    assert kb_store.delete_node(base, "PY-999") is False


def test_list_all_node_ids(tmp_path):
    base = _make_base(tmp_path)
    (base / "nodes" / "a.json").write_text(
        json.dumps([_node("PY-001"), _node("PY-002", "x")], ensure_ascii=False), encoding="utf-8")
    (base / "member_b").mkdir()
    (base / "member_b" / "b.json").write_text(
        json.dumps([_node("PY-092", "x")], ensure_ascii=False), encoding="utf-8")
    ids = kb_store.list_all_node_ids(base)
    assert set(ids) == {"PY-001", "PY-002", "PY-092"}


# ============================================================
# 题目定位/读写
# ============================================================

def test_save_question_new_creates_file(tmp_path):
    base = _make_base(tmp_path)
    kb_store.save_question(base, _q("Q-PY001-001"))
    qf = base / "questions" / "PY-001.json"
    assert qf.is_file()
    data = json.loads(qf.read_text(encoding="utf-8"))
    assert len(data) == 1


def test_save_question_existing_replaces_by_qid(tmp_path):
    base = _make_base(tmp_path)
    qf = base / "questions" / "PY-001.json"
    qf.write_text(json.dumps([_q("Q-PY001-001", question="旧题"), _q("Q-PY001-002")], ensure_ascii=False),
                  encoding="utf-8")
    kb_store.save_question(base, _q("Q-PY001-001", question="新题"))
    data = json.loads(qf.read_text(encoding="utf-8"))
    assert len(data) == 2  # 不重复
    assert data[0]["question"] == "新题"


def test_find_question_locates(tmp_path):
    base = _make_base(tmp_path)
    kb_store.save_question(base, _q("Q-PY001-003"))
    found = kb_store.find_question(base, "Q-PY001-003")
    assert found is not None
    _, idx, q = found
    assert q["qid"] == "Q-PY001-003"


def test_find_question_skips_schema_json(tmp_path):
    base = _make_base(tmp_path)
    assert kb_store.find_question(base, "Q-PY001-001") is None


def test_delete_question_removes(tmp_path):
    base = _make_base(tmp_path)
    qf = base / "questions" / "PY-001.json"
    qf.write_text(json.dumps([_q("Q-PY001-001"), _q("Q-PY001-002")], ensure_ascii=False),
                  encoding="utf-8")
    assert kb_store.delete_question(base, "Q-PY001-001") is True
    data = json.loads(qf.read_text(encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["qid"] == "Q-PY001-002"


def test_load_questions_for_node_missing_returns_empty(tmp_path):
    base = _make_base(tmp_path)
    assert kb_store.load_questions_for_node(base, "PY-999") == []


# ============================================================
# ID 自动生成
# ============================================================

def test_next_node_id_increments(tmp_path):
    base = _make_base(tmp_path)
    (base / "nodes" / "a.json").write_text(
        json.dumps([_node("PY-001"), _node("PY-092", "x")], ensure_ascii=False), encoding="utf-8")
    assert kb_store.next_node_id(base, "PY") == "PY-093"


def test_next_node_id_new_prefix_starts_001(tmp_path):
    base = _make_base(tmp_path)
    (base / "nodes" / "a.json").write_text(
        json.dumps([_node("PY-001")], ensure_ascii=False), encoding="utf-8")
    assert kb_store.next_node_id(base, "ML") == "ML-001"


def test_next_node_id_empty_base(tmp_path):
    base = _make_base(tmp_path)
    assert kb_store.next_node_id(base, "PY") == "PY-001"


def test_next_node_id_invalid_prefix_raises(tmp_path):
    base = _make_base(tmp_path)
    with pytest.raises(ValueError):
        kb_store.next_node_id(base, "PYTHON")  # 非 2 字母


def test_next_question_id_increments(tmp_path):
    base = _make_base(tmp_path)
    qf = base / "questions" / "PY-001.json"
    qf.write_text(json.dumps([_q("Q-PY001-001"), _q("Q-PY001-003")], ensure_ascii=False),
                  encoding="utf-8")
    assert kb_store.next_question_id(base, "PY-001") == "Q-PY001-004"


def test_next_question_id_no_questions_starts_001(tmp_path):
    base = _make_base(tmp_path)
    assert kb_store.next_question_id(base, "PY-001") == "Q-PY001-001"


def test_node_id_exists(tmp_path):
    base = _make_base(tmp_path)
    (base / "nodes" / "a.json").write_text(
        json.dumps([_node("PY-001")], ensure_ascii=False), encoding="utf-8")
    assert kb_store.node_id_exists(base, "PY-001") is True
    assert kb_store.node_id_exists(base, "PY-999") is False


# ============================================================
# 并发安全 (per-file 锁)
# ============================================================

def test_concurrent_save_node_no_lost_update(tmp_path):
    """20 线程并发向 manual 文件追加不同节点 → 无丢失 (B2 同类)。"""
    base = _make_base(tmp_path)
    def task(i):
        kb_store.save_node(base, _node(f"PY-{i+100:03d}", name=f"n{i}"))
    with ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(task, range(20)))
    manual = base / "nodes" / "_manual_nodes.json"
    data = json.loads(manual.read_text(encoding="utf-8"))
    ids = [n["id"] for n in data]
    assert len(ids) == 20  # 无丢失
    assert len(set(ids)) == 20  # 无重复


def test_concurrent_next_node_id_no_collision(tmp_path):
    """并发生成 ID 应无撞号 (锁内串行扫+算, 但 next_node_id 本身读多写少;
    实际撞号防护在 API 层 save 时锁内重判。这里验证基础生成不崩)。"""
    base = _make_base(tmp_path)
    (base / "nodes" / "a.json").write_text(
        json.dumps([_node("PY-001")], ensure_ascii=False), encoding="utf-8")
    results = []
    def task():
        results.append(kb_store.next_node_id(base, "PY"))
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(task) for _ in range(4)]
        for f in futs:
            f.result()
    # next_node_id 是纯读算, 不写, 4 次都应得 PY-002 (无写入)
    assert all(r == "PY-002" for r in results)
