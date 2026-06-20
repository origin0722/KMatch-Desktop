"""知识库 JSON 文件读写与定位 (CRUD 的 JSON 真相源层)。

设计: JSON 为源, Neo4j 为派生缓存。本模块只管 JSON 文件的定位/读写/ID 生成,
不碰 Neo4j (由 engine 同步)。代码对节点目录结构无感 (glob 递归),
节点 JSON 现扁平化到 data/knowledge_base/nodes/ (原 member_a/b/c 已合并)。

并发安全: per-file threading.Lock, 同文件读写串行, 跨文件并发 (参考
generate_common_mistakes B2 修复模式)。
"""

from __future__ import annotations

import json
import re
import threading
from collections import defaultdict
from pathlib import Path
from typing import Optional

from app.utils.logging import get_logger

logger = get_logger(__name__)

# 节点 ID 正则 (与 schema.json 一致): 2 大写字母 + 3 位数字, 如 PY-092 / ML-001
NODE_ID_RE = re.compile(r"^([A-Z]{2})-(\d{3})$")
# 题目 qid 正则: Q-{节点ID无连字符}-{3位序号}, 如 Q-PY001-003
QID_RE = re.compile(r"^Q-([A-Z]{2})(\d{3})-(\d{3})$")

# 临时/手动新增节点落地文件 (追加到 nodes/, 避免散落)
_MANUAL_NODE_FILE = "nodes/_manual_nodes.json"

# per-file 锁 (进程内; 多 worker 部署需换文件锁, 当前单进程足够)
_file_locks: dict[Path, threading.Lock] = defaultdict(threading.Lock)


def _lock_for(path: Path) -> threading.Lock:
    return _file_locks[path]


# ============================================================
# 目录/文件排除
# ============================================================

def _is_node_json(path: Path, base: Path) -> bool:
    """是否为知识节点 JSON (排除 schema.json 和 questions/ 目录)。"""
    if path.name == "schema.json":
        return False
    questions_dir = base / "questions"
    if questions_dir in path.parents:
        return False
    return True


def _iter_node_files(base: Path):
    """递归遍历知识节点 JSON 文件 (排除 questions/ 与 schema.json)。"""
    for path in base.glob("**/*.json"):
        if _is_node_json(path, base):
            yield path


def _load_json_list(path: Path) -> list:
    """读 JSON, 期望顶层 list (节点数组)。dict 单节点兼容返回 [dict]。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    return []


# ============================================================
# 知识节点定位/读写
# ============================================================

def find_node_file(base: Path, node_id: str) -> Optional[tuple[Path, int]]:
    """在知识库中定位含 node_id 的文件, 返回 (文件路径, 节点在数组中的下标)。

    无则返回 None (调用方据此决定新建)。glob 递归, 对 member 目录无感。
    """
    for path in _iter_node_files(base):
        try:
            nodes = _load_json_list(path)
        except Exception:
            logger.warning("节点文件解析失败, 跳过: %s", path, exc_info=True)
            continue
        for i, n in enumerate(nodes):
            if isinstance(n, dict) and n.get("id") == node_id:
                return path, i
    return None


def load_node(base: Path, node_id: str) -> Optional[dict]:
    """读单个知识节点 (按 id 定位)。无则 None。"""
    found = find_node_file(base, node_id)
    if found is None:
        return None
    path, idx = found
    with _lock_for(path):
        nodes = _load_json_list(path)
    if 0 <= idx < len(nodes) and isinstance(nodes[idx], dict):
        return nodes[idx]
    return None


def save_node(base: Path, node: dict) -> Path:
    """写入/更新知识节点到 JSON (真相源)。

    - 节点已存在: 定位文件, 原地替换数组元素
    - 节点不存在: 追加到 _MANUAL_NODE_FILE (不存在则创建)
    返回写入的文件路径。per-file 锁串行化同文件写。
    """
    nid = node.get("id")
    if not nid:
        raise ValueError("节点缺 id, 无法保存")

    found = find_node_file(base, nid)
    if found is not None:
        path, idx = found
        with _lock_for(path):
            nodes = _load_json_list(path)
            nodes[idx] = node
            path.write_text(
                json.dumps(nodes, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        return path

    # 新节点: 追加到 manual 文件
    path = base / _MANUAL_NODE_FILE
    with _lock_for(path):
        if path.exists():
            nodes = _load_json_list(path)
        else:
            nodes = []
        nodes.append(node)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(nodes, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return path


def delete_node(base: Path, node_id: str) -> bool:
    """从 JSON 删除知识节点。返回是否删除成功 (不存在返回 False)。"""
    found = find_node_file(base, node_id)
    if found is None:
        return False
    path, idx = found
    with _lock_for(path):
        nodes = _load_json_list(path)
        if 0 <= idx < len(nodes):
            nodes.pop(idx)
            path.write_text(
                json.dumps(nodes, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            return True
    return False


def list_all_node_ids(base: Path) -> list[str]:
    """列出全库所有知识节点 id (ID 生成用)。"""
    ids = []
    for path in _iter_node_files(base):
        try:
            for n in _load_json_list(path):
                if isinstance(n, dict) and n.get("id"):
                    ids.append(n["id"])
        except Exception:
            continue
    return ids


# ============================================================
# 题目定位/读写
# ============================================================

def _question_file(base: Path, source_node_id: str) -> Path:
    """题目文件路径: questions/<source_node_id>.json。"""
    return base / "questions" / f"{source_node_id}.json"


def load_questions_for_node(base: Path, source_node_id: str) -> list[dict]:
    """读某节点的全部题目 (数组)。无文件返回 []。"""
    path = _question_file(base, source_node_id)
    if not path.is_file():
        return []
    with _lock_for(path):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("题目文件解析失败: %s", path, exc_info=True)
            return []
    return data if isinstance(data, list) else []


def find_question(base: Path, qid: str) -> Optional[tuple[Path, int, dict]]:
    """全库定位题目, 返回 (文件路径, 下标, 题目dict)。无则 None。

    qid 含 source_node_id 信息 (Q-PY001-003), 但为稳健起见遍历 questions/ 查找。
    """
    qdir = base / "questions"
    if not qdir.is_dir():
        return None
    for path in sorted(qdir.glob("*.json")):
        if path.name == "schema.json":
            continue
        with _lock_for(path):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
        if not isinstance(data, list):
            continue
        for i, q in enumerate(data):
            if isinstance(q, dict) and q.get("qid") == qid:
                return path, i, q
    return None


def save_question(base: Path, question: dict) -> Path:
    """写入/更新题目到 questions/<source_node_id>.json。返回文件路径。"""
    qid = question.get("qid")
    source = question.get("source_node_id")
    if not qid or not source:
        raise ValueError("题目缺 qid 或 source_node_id, 无法保存")

    path = _question_file(base, source)
    with _lock_for(path):
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                data = []
        else:
            data = []
        # 按 qid upsert: 存在则替换, 不存在则追加
        replaced = False
        for i, q in enumerate(data):
            if isinstance(q, dict) and q.get("qid") == qid:
                data[i] = question
                replaced = True
                break
        if not replaced:
            data.append(question)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return path


def delete_question(base: Path, qid: str) -> bool:
    """从 JSON 删除题目。返回是否删除成功。"""
    found = find_question(base, qid)
    if found is None:
        return False
    path, idx, _ = found
    with _lock_for(path):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list) and 0 <= idx < len(data):
            data.pop(idx)
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            return True
    return False


def list_questions_for_node_ids(base: Path, node_ids: list[str]) -> list[dict]:
    """批量读多节点题目 (cascade 删除/查询用)。"""
    result = []
    for nid in node_ids:
        result.extend(load_questions_for_node(base, nid))
    return result


# ============================================================
# ID 自动生成
# ============================================================

def next_node_id(base: Path, prefix: str = "PY") -> str:
    """生成下一个节点 id: 扫该前缀现有最大数字 +1, 补零 3 位。

    PY-092 → PY-093; 新前缀 ML → ML-001。前缀须 2 大写字母。
    """
    if not re.match(r"^[A-Z]{2}$", prefix):
        raise ValueError(f"前缀须 2 大写字母: {prefix!r}")
    max_num = 0
    for nid in list_all_node_ids(base):
        m = NODE_ID_RE.match(nid)
        if m and m.group(1) == prefix:
            max_num = max(max_num, int(m.group(2)))
    return f"{prefix}-{max_num + 1:03d}"


def next_question_id(base: Path, node_id: str) -> str:
    """生成下一题目 qid: 读该节点题目文件最大序号 +1。

    node_id=PY-001, 现有 Q-PY001-003 → Q-PY001-004; 无题 → Q-PY001-001。
    qid 中缀用 node_id 去连字符 (PY-001 → PY001)。
    """
    m = NODE_ID_RE.match(node_id)
    if not m:
        raise ValueError(f"node_id 格式错误: {node_id!r}")
    infix = m.group(1) + m.group(2)  # PY + 001 = PY001
    max_seq = 0
    for q in load_questions_for_node(base, node_id):
        qid = q.get("qid", "")
        qm = QID_RE.match(qid)
        if qm and qm.group(1) + qm.group(2) == infix:
            max_seq = max(max_seq, int(qm.group(3)))
    return f"Q-{infix}-{max_seq + 1:03d}"


def node_id_exists(base: Path, node_id: str) -> bool:
    """节点 id 是否已存在 (创建题目时校验 source_node_id 用)。"""
    return find_node_file(base, node_id) is not None
