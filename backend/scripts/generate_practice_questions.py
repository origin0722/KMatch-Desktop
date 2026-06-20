#!/usr/bin/env python3
"""
KMatch 题目生成脚本 (题库驱动出题的数据源)

用法: python generate_practice_questions.py <knowledge_base_dir> [--force] [--validate-code]
功能:
  为每个知识节点 LLM 生成题目,输出到 <base_dir>/questions/<node_id>.json。
  - 每节点按 difficulty 补到≥3题: diff1-2=2choice+1fill, diff3+=1choice+1fill+1code
  - choice 干扰项必须来自 common_mistakes (对齐 content_generator test 题要求,减幻觉)
  - 严格基于 key_points/common_mistakes/summary 生成,严禁编造图谱外事实
  - code 题 answer 跑 ast.parse 轻量校验 (--validate-code 统计通过率)
  - 题带 qid/source_node_id/type/question/options/answer/difficulty/hint/explanation
  - 已有题目文件默认跳过 (--force 覆盖)
  并发生成,单节点失败不中断。
"""

import argparse
import ast
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.llm import get_default_chat_model, llm_configured
from app.utils.json_utils import parse_llm_json
from app.utils.logging import get_logger

logger = get_logger(__name__)

# 题型配比 (按节点 difficulty)
def _target_types(difficulty: int) -> list[str]:
    """节点难度 → 生成题型配比。"""
    if difficulty <= 2:
        return ["choice", "choice", "fill"]
    return ["choice", "fill", "code"]


def _build_questions_prompt(node: dict, target_types: list[str]) -> list:
    """单节点题目生成 prompt。choice 干扰项来自 common_mistakes,严格基于图谱事实。"""
    kps = node.get("key_points", [])
    mistakes = node.get("common_mistakes", [])
    type_spec = {
        "choice": "选择题: 4选项含'A. xxx'前缀, answer=正确选项字母(A/B/C/D), "
                  "干扰项必须来自下方 common_mistakes (描述典型错误认知)",
        "fill": "填空题: 题干留空(用_____标注), answer=填空内容(代码/函数名/关键词)",
        "code": "代码题: 题干描述任务与输入输出, answer=完整可运行Python代码(含import), "
                "难度挑战级(综合多个 key_points)",
    }
    specs = "\n".join(f"- {t}: {type_spec[t]}" for t in target_types if t in type_spec)
    system = SystemMessage(content=(
        "你是 KMatch 出题专家。为 Python 知识点生成结构化题目。"
        "【高保真约束——消除幻觉】只能依据本节点 summary/key_points/common_mistakes "
        "出题,严禁编造图谱外的实现细节/内部表示/具体数值/版本号。题目考察的事实须在节点信息中有据可查。"
        f"\n本节点需生成 {len(target_types)} 道题,题型与要求:\n{specs}\n"
        "严格输出 JSON 数组,每元素: "
        '{"type":"choice|fill|code","question":"题干","options":["A.."](仅choice),'
        '"answer":"答案","difficulty":1-5,"hint":"提示(可选)","explanation":"解析"}。'
        "不要输出 JSON 以外文字。"
    ))
    user = HumanMessage(content=(
        f"知识点 {node.get('id','')}《{node.get('name','')}》(难度{node.get('difficulty',1)}):\n"
        f"summary: {node.get('summary','')}\n"
        f"key_points: {json.dumps(kps, ensure_ascii=False)}\n"
        f"common_mistakes(用于choice干扰项): {json.dumps(mistakes, ensure_ascii=False)}\n\n"
        f"请生成 {len(target_types)} 道题。"
    ))
    return [system, user]


def _validate_code_answer(answer: str) -> bool:
    """code 题 answer 跑 ast.parse 校验语法。"""
    try:
        ast.parse(answer)
        return True
    except SyntaxError:
        return False


def _normalize_question(q: dict, node_id: str, qid: str) -> dict | None:
    """规范化单题:补 qid/source_node_id,转 node_id 供 diagnostics 用,校验必填。

    返回规范化的题 dict 或 None(无效题丢弃)。
    """
    if not isinstance(q, dict):
        return None
    valid_types = {"choice", "fill", "code"}
    if q.get("type") not in valid_types:
        return None
    if not q.get("question") or "answer" not in q:
        return None
    if q["type"] == "choice" and not isinstance(q.get("options"), list):
        return None
    # 补全字段
    q["qid"] = qid
    q["source_node_id"] = node_id
    q["node_id"] = node_id  # diagnostics _grade/_build_profile 按 node_id 分组
    q.setdefault("difficulty", 1)
    q.setdefault("hint", "")
    q.setdefault("explanation", "")
    # options 规范: choice 确保是 list[str]
    if q["type"] == "choice":
        q["options"] = [str(o) for o in q.get("options", [])]
    return q


def _gen_one(node: dict, validate_code: bool) -> tuple[list[dict], int, int]:
    """生成单节点题目。返回 (题目列表, code题数, code通过数)。"""
    difficulty = node.get("difficulty", 1)
    target_types = _target_types(difficulty)
    node_id = node["id"]

    model = get_default_chat_model()
    resp = model.invoke(_build_questions_prompt(node, target_types))
    data = parse_llm_json(resp.content)
    # 防御: 偶发返回对象包装
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list):
                data = v
                break
    if not isinstance(data, list):
        raise ValueError(f"题目响应非数组: {type(data)}")

    questions = []
    code_total, code_pass = 0, 0
    for i, q in enumerate(data):
        qid = f"Q-{node_id.replace('-','')}-{i+1:03d}"
        normed = _normalize_question(q, node_id, qid)
        if normed is None:
            continue
        if normed["type"] == "code":
            code_total += 1
            if validate_code and _validate_code_answer(normed["answer"]):
                code_pass += 1
        questions.append(normed)
    if not questions:
        raise ValueError(f"节点 {node_id} 未生成有效题目")
    return questions, code_total, code_pass


def _write_questions_file(questions_dir: Path, node_id: str, questions: list[dict], force: bool, dry_run: bool) -> str:
    """写 questions/<node_id>.json。返回 'updated'/'skipped'/'error'。"""
    out_file = questions_dir / f"{node_id}.json"
    if out_file.exists() and not force:
        return "skipped"
    if dry_run:
        return "updated"
    try:
        out_file.write_text(
            json.dumps(questions, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return "updated"
    except Exception as e:
        logger.error("写题目文件失败 %s: %s", out_file, e)
        return "error"


def _load_nodes(base_dir: Path) -> list[dict]:
    """加载所有知识节点 (复用 generate_common_mistakes 的加载逻辑)。"""
    schema_file = base_dir / "schema.json"
    questions_dir = base_dir / "questions"
    result = []
    for fp in base_dir.glob("**/*.json"):
        if fp == schema_file:
            continue
        if questions_dir in fp.parents:
            continue
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, list):
            result.extend(n for n in data if isinstance(n, dict) and n.get("id"))
        elif isinstance(data, dict):
            if data.get("id"):
                result.append(data)
            for n in data.get("nodes", []) or []:
                if isinstance(n, dict) and n.get("id"):
                    result.append(n)
    return result


def main():
    parser = argparse.ArgumentParser(description="为知识节点生成题目 (独立 :Question 数据源)")
    parser.add_argument("base_dir", help="knowledge_base 目录")
    parser.add_argument("--force", action="store_true", help="覆盖已有题目文件")
    parser.add_argument("--dry-run", action="store_true", help="只打印不写文件")
    parser.add_argument("--validate-code", action="store_true", help="校验 code 题语法")
    parser.add_argument("--max-workers", type=int, default=8, help="并发数")
    args = parser.parse_args()

    if not llm_configured():
        print("❌ LLM 未配置 (LLM_API_KEY),无法生成。")
        sys.exit(1)

    base_dir = Path(args.base_dir)
    questions_dir = base_dir / "questions"
    if not args.dry_run:
        questions_dir.mkdir(parents=True, exist_ok=True)

    nodes = _load_nodes(base_dir)
    print(f"📂 加载 {len(nodes)} 个知识节点 → 输出到 {questions_dir}")

    success, skipped, failed = 0, 0, 0
    total_questions = 0
    code_total, code_pass = 0, 0
    failed_ids = []

    def _task(node):
        nid = node["id"]
        # B6: 先判 skip 再调 LLM — 题目文件已存在且非 --force 时直接跳过,
        # 避免重跑先烧 92 次 LLM 再全部 skip。
        out_file = questions_dir / f"{nid}.json"
        if out_file.exists() and not args.force:
            return nid, "skipped", 0, 0, 0
        try:
            qs, ct, cp = _gen_one(node, args.validate_code)
            status = _write_questions_file(questions_dir, nid, qs, args.force, args.dry_run)
            return nid, status, len(qs), ct, cp
        except Exception as e:
            logger.error("生成失败 %s: %s", nid, e)
            return nid, "error", 0, 0, 0

    with ThreadPoolExecutor(max_workers=args.max_workers) as ex:
        futures = {ex.submit(_task, n): n["id"] for n in nodes}
        for fut in as_completed(futures):
            nid, status, qcount, ct, cp = fut.result()
            if status == "updated":
                success += 1
                total_questions += qcount
                code_total += ct
                code_pass += cp
                tag = f" (code校验 {cp}/{ct})" if args.validate_code and ct else ""
                print(f"  ✅ {nid}: {qcount} 题{tag}")
            elif status == "skipped":
                skipped += 1
            else:
                failed += 1
                failed_ids.append(nid)

    print(f"\n{'=' * 50}")
    print(f"  生成完成: ✅{success} 节点 / {total_questions} 题 / ⏭️{skipped} 跳过 / ❌{failed} 失败")
    if args.validate_code and code_total:
        print(f"  code 题语法校验: {code_pass}/{code_total} 通过 ({code_pass/code_total*100:.0f}%)")
    if failed_ids:
        print(f"  失败节点: {failed_ids}")
    if args.dry_run:
        print("  (dry-run 模式,未写文件)")
    print(f"{'=' * 50}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
