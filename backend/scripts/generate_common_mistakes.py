#!/usr/bin/env python3
"""
KMatch common_mistakes 生成脚本

用法: python generate_common_mistakes.py <knowledge_base_dir> [--force] [--dry-run]
功能:
  为每个知识节点 LLM 生成 common_mistakes (常见误区 list[str]),写回节点 JSON。
  - common_mistakes 是 5 处运行时 Agent 消费的字段 (content_generator test 干扰项/
    diagnostics error_patterns/code_tester/code_reviewer/reviewer 事实边界)
  - 严格基于 summary/key_points 生成,严禁编造图谱外事实 (对齐层次1减幻觉)
  - 已有 common_mistakes 的节点默认跳过 (--force 覆盖)
  - 并发生成 (8 路),单节点失败不中断
"""

import argparse
import json
import sys
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# 确保 backend/ 在 sys.path (脚本直接运行时导入 app 模块)
sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.llm import get_default_chat_model, llm_configured
from app.utils.json_utils import parse_llm_json
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _build_mistakes_prompt(node: dict) -> list:
    """单节点 common_mistakes 生成 prompt。严格基于节点事实,输出 JSON 数组。"""
    kps = node.get("key_points", [])
    system = SystemMessage(content=(
        "你是 KMatch 知识库编辑。为 Python 知识点生成「常见误区」列表。"
        "【高保真约束——消除幻觉】只能依据本节点 summary/key_points 生成,严禁补充"
        "图谱外的实现细节/内部表示/具体数值/版本号/性能数据 (训练记忆非图谱事实)。"
        "每条误区描述一个典型错误认知或误用,一句话,具体可操作 (能作选择题干扰项)。"
        "生成 2-4 条。严格输出 JSON 数组: [\"误区1\", \"误区2\", ...]。"
        "不要输出 JSON 以外文字。"
    ))
    user = HumanMessage(content=(
        f"知识点 {node.get('id','')}《{node.get('name','')}》(难度{node.get('difficulty',1)}):\n"
        f"summary: {node.get('summary','')}\n"
        f"key_points: {json.dumps(kps, ensure_ascii=False)}\n\n"
        f"请生成该知识点的常见误区。"
    ))
    return [system, user]


def _gen_one(node: dict) -> list[str]:
    """调 LLM 生成单节点 common_mistakes,返回 list[str]。结构校验失败重试1次。"""
    model = get_default_chat_model()
    resp = model.invoke(_build_mistakes_prompt(node))
    data = parse_llm_json(resp.content)
    # 防御: LLM 偶发返回对象包装
    if isinstance(data, dict):
        # 取首个 list 值兜底
        for v in data.values():
            if isinstance(v, list):
                data = v
                break
    if not isinstance(data, list):
        raise ValueError(f"common_mistakes 响应非数组: {type(data)}")
    # 规范化: 全转 str,过滤空,去重保序,限 4 条
    mistakes = []
    seen = set()
    for m in data:
        s = str(m).strip()
        if s and s not in seen:
            seen.add(s)
            mistakes.append(s)
        if len(mistakes) >= 4:
            break
    if not mistakes:
        raise ValueError("生成的 common_mistakes 为空")
    return mistakes


def _find_node_in_file(data, node_id: str):
    """在加载的 JSON 数据中定位节点,返回 (节点dict, 所在容器list或None, 索引)。

    支持两种文件结构: 顶层 list 或 顶层 dict (单节点)。返回 container 与索引便于写回。
    """
    if isinstance(data, list):
        for i, n in enumerate(data):
            if isinstance(n, dict) and n.get("id") == node_id:
                return n, data, i
        return None, data, -1
    if isinstance(data, dict):
        if data.get("id") == node_id:
            return data, None, -1
        # dict 包 nodes 数组
        nodes = data.get("nodes")
        if isinstance(nodes, list):
            for i, n in enumerate(nodes):
                if isinstance(n, dict) and n.get("id") == node_id:
                    return n, nodes, i
    return None, None, -1


def _update_file(file_path: Path, node_id: str, mistakes: list[str],
                 force: bool, dry_run: bool, file_lock: threading.Lock = None) -> str:
    """读 JSON → 定位节点 → 加/覆盖 common_mistakes → 写回。返回 'updated'/'skipped'/'error'。

    file_lock: per-file 锁。多节点同属一个文件时, 并发 read→改→write 整文件会丢更新
    (BUG B2): 线程A读v0改写, 线程B基于v0改写覆盖A → A的 common_mistakes 丢失。
    加锁串行化同文件的写, 不同文件仍并发。
    """
    # 锁粒度=文件: 同文件节点串行写, 跨文件并发不受影响
    def _do():
        try:
            raw = file_path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except Exception as e:
            logger.error("读取失败 %s: %s", file_path, e)
            return "error"

        node, container, idx = _find_node_in_file(data, node_id)
        if node is None:
            logger.error("节点 %s 未在 %s 中找到", node_id, file_path)
            return "error"

        if node.get("common_mistakes") and not force:
            return "skipped"

        node["common_mistakes"] = mistakes
        # container 是 list 时已原地改; dict 单节点也原地改。仅需写回 data。
        if dry_run:
            return "updated"

        try:
            # 保留原缩进格式 (2 空格, ensure_ascii=False)
            indent = 2
            file_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=indent) + "\n",
                encoding="utf-8",
            )
            return "updated"
        except Exception as e:
            logger.error("写回失败 %s: %s", file_path, e)
            return "error"

    if file_lock is not None:
        with file_lock:
            return _do()
    return _do()


def _load_nodes(base_dir: Path) -> list[tuple[dict, Path]]:
    """加载所有节点及其所在文件路径。返回 [(node, file_path), ...]。"""
    schema_file = base_dir / "schema.json"
    questions_dir = base_dir / "questions"
    result = []
    for fp in base_dir.glob("**/*.json"):
        if fp == schema_file:
            continue
        # 跳过 questions/ 目录 (题目独立文件,非知识节点)
        if questions_dir in fp.parents:
            continue
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, list):
            for n in data:
                if isinstance(n, dict) and n.get("id"):
                    result.append((n, fp))
        elif isinstance(data, dict):
            if data.get("id"):
                result.append((data, fp))
            for n in data.get("nodes", []) or []:
                if isinstance(n, dict) and n.get("id"):
                    result.append((n, fp))
    return result


def main():
    parser = argparse.ArgumentParser(description="为知识节点生成 common_mistakes")
    parser.add_argument("base_dir", help="knowledge_base 目录")
    parser.add_argument("--force", action="store_true", help="覆盖已有 common_mistakes")
    parser.add_argument("--dry-run", action="store_true", help="只打印不写文件")
    parser.add_argument("--max-workers", type=int, default=8, help="并发数")
    args = parser.parse_args()

    if not llm_configured():
        print("❌ LLM 未配置 (LLM_API_KEY),无法生成。请配置 .env 后重试。")
        sys.exit(1)

    base_dir = Path(args.base_dir)
    nodes_files = _load_nodes(base_dir)
    print(f"📂 加载 {len(nodes_files)} 个知识节点")

    success, skipped, failed = 0, 0, 0
    failed_ids = []

    # per-file 锁: 同文件节点串行写, 避免并发 read→改→write 丢更新 (BUG B2)
    file_locks: dict[Path, threading.Lock] = defaultdict(threading.Lock)

    def _task(nf):
        node, fp = nf
        nid = node.get("id", "?")
        # B6: 先判 skip 再调 LLM — 已有 common_mistakes 且非 --force 时直接跳过,
        # 避免重跑先烧 92 次 LLM 再全部 skip (锁内判 skip, 与 _update_file 一致)。
        if node.get("common_mistakes") and not args.force:
            return nid, "skipped", node["common_mistakes"]
        try:
            mistakes = _gen_one(node)
            status = _update_file(fp, nid, mistakes, args.force, args.dry_run,
                                  file_locks[fp])
            return nid, status, mistakes
        except Exception as e:
            logger.error("生成失败 %s: %s", nid, e)
            return nid, "error", []

    with ThreadPoolExecutor(max_workers=args.max_workers) as ex:
        futures = {ex.submit(_task, nf): nf[0].get("id") for nf in nodes_files}
        for fut in as_completed(futures):
            nid, status, mistakes = fut.result()
            if status == "updated":
                success += 1
                print(f"  ✅ {nid}: {mistakes}")
            elif status == "skipped":
                skipped += 1
            else:
                failed += 1
                failed_ids.append(nid)

    print(f"\n{'=' * 50}")
    print(f"  生成完成: ✅{success} 更新 / ⏭️{skipped} 跳过 / ❌{failed} 失败")
    if failed_ids:
        print(f"  失败节点: {failed_ids}")
        print(f"  可重跑: python generate_common_mistakes.py {args.base_dir}")
    if args.dry_run:
        print("  (dry-run 模式,未写文件)")
    print(f"{'=' * 50}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
