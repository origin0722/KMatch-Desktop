#!/usr/bin/env python3
"""
KMatch 数据验证脚本 v3
用法:
  python validate_data.py <knowledge_base_dir> [user_profiles_dir]
功能:
  1. 检查所有 JSON 文件是否为合法 JSON
  2. 逐项对照 schema.json 校验知识节点字段完整性
  3. 检查 id 唯一性
  4. 检查 prerequisites 引用有效性
  5. 检查循环依赖
  6. 校验用户画像格式（v3 画像 Schema）
  7. 输出验证报告
"""

import json
import sys
import re
from pathlib import Path
from collections import Counter, defaultdict


def load_schema(schema_path: Path) -> dict:
    with open(schema_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_knowledge_nodes(base_dir: Path) -> dict[str, dict]:
    """加载所有知识节点，返回 {id: node} 映射"""
    nodes = {}
    schema_file = base_dir / "schema.json"
    json_files = list(base_dir.glob("**/*.json"))

    for file_path in json_files:
        if file_path == schema_file:
            continue
        # 跳过 questions/ 目录 (题目独立文件, 非知识节点; 与 import 脚本一致)
        questions_dir = base_dir / "questions"
        if questions_dir in file_path.parents:
            continue
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                for item in data:
                    if "id" in item:
                        nodes[item["id"]] = item
            elif isinstance(data, dict) and "id" in data:
                nodes[data["id"]] = data
        except json.JSONDecodeError as e:
            print(f"❌ JSON 解析错误: {file_path}: {e}")

    return nodes


def validate_node(node: dict, schema: dict, all_ids: set) -> list[str]:
    """校验单个知识节点"""
    errors = []
    required_fields = schema.get("required", [])

    # 必填字段
    for field in required_fields:
        if field not in node:
            errors.append(f"缺失必填字段: {field}")

    # id 格式
    nid = node.get("id", "")
    if nid:
        id_pattern = schema["properties"]["id"]["pattern"]
        if not re.match(id_pattern, nid):
            errors.append(f"id 格式错误: {nid} (期望: {id_pattern})")

    # category
    category = node.get("category", "")
    if category:
        valid_categories = schema["properties"]["category"]["enum"]
        if category not in valid_categories:
            errors.append(f"无效 category: {category} (有效: {valid_categories})")

    # difficulty 范围
    diff = node.get("difficulty")
    if diff is not None:
        if not isinstance(diff, int) or not (1 <= diff <= 5):
            errors.append(f"difficulty 超出范围: {diff} (期望: 1-5)")

    # tags
    tags = node.get("tags", [])
    if not isinstance(tags, list) or len(tags) == 0:
        errors.append("tags 必须是非空数组")

    # summary (top-level) — 对齐 schema minLength:30 (空串也违规, 旧 `if summary` 因空串假值漏报)
    summary = node.get("summary", "")
    if not isinstance(summary, str) or len(summary) < 30:
        errors.append(f"summary 太短或缺失: {len(summary) if isinstance(summary, str) else '非字符串'} 字符 (最少 30)")

    # name (top-level) — 对齐 schema minLength:2
    name = node.get("name", "")
    if not isinstance(name, str) or len(name) < 2:
        errors.append(f"name 太短或缺失 (最少 2 字符): {name!r}")

    # key_points (top-level) — 对齐 schema.json minItems:3
    key_points = node.get("key_points", [])
    if not isinstance(key_points, list) or len(key_points) < 3:
        errors.append("key_points 至少需要 3 条 (对齐 schema minItems:3)")

    # practice_questions
    questions = node.get("practice_questions", [])
    if not isinstance(questions, list) or len(questions) == 0:
        errors.append("practice_questions 至少需要 1 道题")
    else:
        valid_types = {"choice", "fill", "code"}
        for i, q in enumerate(questions):
            if not isinstance(q, dict):
                errors.append(f"practice_questions[{i}] 必须是对象")
                continue
            if "type" not in q:
                errors.append(f"practice_questions[{i}]: 缺少 type")
            elif q["type"] not in valid_types:
                errors.append(f"practice_questions[{i}]: 无效 type '{q['type']}'")
            if "question" not in q:
                errors.append(f"practice_questions[{i}]: 缺少 question")
            if "answer" not in q:
                errors.append(f"practice_questions[{i}]: 缺少 answer")
            if q.get("type") == "choice" and "options" not in q:
                errors.append(f"practice_questions[{i}]: choice 类型缺少 options")
            # per-question difficulty 校验
            qd = q.get("difficulty")
            if qd is not None and (not isinstance(qd, int) or not (1 <= qd <= 5)):
                errors.append(f"practice_questions[{i}]: difficulty 超出 1-5: {qd}")

    # common_mistakes (5处运行时Agent消费:content_generator/diagnostics/code_tester/code_reviewer/reviewer)
    mistakes = node.get("common_mistakes")
    if mistakes is None:
        errors.append("缺失 common_mistakes (建议补全: test题干扰项/error_patterns/code审查依赖此字段)")
    elif not isinstance(mistakes, list) or len(mistakes) == 0:
        errors.append("common_mistakes 必须是非空数组")
    elif not all(isinstance(m, str) for m in mistakes):
        errors.append("common_mistakes 元素必须为字符串")

    # estimated_minutes
    est = node.get("estimated_minutes")
    if est is not None and (not isinstance(est, int) or est < 5 or est > 240):
        errors.append(f"estimated_minutes 不合理: {est}")

    return errors


def validate_question(q: dict, qid: str, known_node_ids: set | None = None) -> list[str]:
    """校验单个 :Question 题目对象 (questions/<node_id>.json 中的元素)。

    题目独立成节点后的结构契约: qid/source_node_id/type/question/answer/difficulty 必填,
    choice 必有 options, answer 格式按题型 (choice=字母/fill=文本/code=代码)。
    known_node_ids: 知识节点 id 集合, 传入则校验 source_node_id 引用完整性 (BUG B7),
    防止孤儿题 (源节点不存在) 静默入库、无 :HAS_QUESTION 边。
    """
    errors = []
    valid_types = {"choice", "fill", "code"}
    if "qid" not in q or not q["qid"]:
        errors.append(f"{qid}: 缺少 qid")
    if "source_node_id" not in q or not q["source_node_id"]:
        errors.append(f"{qid}: 缺少 source_node_id (出题后注入为 node_id, 不可缺)")
    elif known_node_ids is not None and q["source_node_id"] not in known_node_ids:
        errors.append(f"{qid}: source_node_id '{q['source_node_id']}' 不存在于知识节点 (孤儿题)")
    if "type" not in q:
        errors.append(f"{qid}: 缺少 type")
    elif q["type"] not in valid_types:
        errors.append(f"{qid}: 无效 type '{q['type']}' (有效: {valid_types})")
    if "question" not in q or not q["question"]:
        errors.append(f"{qid}: 缺少 question")
    if "answer" not in q:
        errors.append(f"{qid}: 缺少 answer")
    if q.get("type") == "choice" and "options" not in q:
        errors.append(f"{qid}: choice 类型缺少 options")
    qd = q.get("difficulty")
    if qd is not None and (not isinstance(qd, int) or not (1 <= qd <= 5)):
        errors.append(f"{qid}: difficulty 超出 1-5: {qd}")
    return errors


def validate_questions_dir(questions_dir: str, known_node_ids: set | None = None) -> tuple[int, dict]:
    """校验 questions/ 目录下所有题目文件。返回 (题目总数, {文件名: 错误列表})。

    known_node_ids: 知识节点 id 集合, 传入则校验每题 source_node_id 引用完整性 (BUG B7)。
    """
    qpath = Path(questions_dir)
    if not qpath.is_dir():
        return 0, {}
    all_errors = {}
    total = 0
    for f in sorted(qpath.glob("*.json")):
        # 跳过 questions/schema.json (题目结构规范文档, 非题目数据)
        if f.name == "schema.json":
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            all_errors[f.name] = [f"JSON 解析失败: {e}"]
            continue
        if not isinstance(data, list):
            all_errors[f.name] = ["题目文件必须是数组"]
            continue
        total += len(data)
        errs = []
        for i, q in enumerate(data):
            if not isinstance(q, dict):
                errs.append(f"[{i}] 必须是对象")
                continue
            qid = q.get("qid", f"{f.name}[{i}]")
            errs.extend(validate_question(q, qid, known_node_ids))
        if errs:
            all_errors[f.name] = errs
    return total, all_errors


def check_references(nodes: dict[str, dict]) -> list[str]:
    """检查 prerequisite 引用有效性"""
    errors = []
    all_ids = set(nodes.keys())

    for nid, node in nodes.items():
        prerequisites = node.get("prerequisites", [])
        for prereq in prerequisites:
            if prereq not in all_ids:
                errors.append(f"{nid}: 引用了不存在的前置节点 {prereq}")
            if prereq == nid:
                errors.append(f"{nid}: 不能将自己设为前置依赖")

    return errors


def check_circular_dependencies(nodes: dict[str, dict]) -> list[str]:
    """检查循环依赖 (DFS 三色法, 后向边 = 环)。

    BUG B4 修复: 旧实现检出环时 return True 早退, 未置 BLACK 也未 path.pop(),
    导致环上节点残留 GRAY; 之后从另一根出发若 prereq 指向这些残留 GRAY 节点,
    path.index(prereq) 找不到 → ValueError 崩溃 (有环+入边场景反而炸)。
    改用 "prereq in path" 判后向边 (path 成员即当前递归栈, 标准做法),
    且无论是否发现环都正常 pop/置 BLACK, 保证状态一致。
    """
    errors = []
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {nid: WHITE for nid in nodes}

    def dfs(nid: str, path: list[str]) -> bool:
        color[nid] = GRAY
        path.append(nid)
        found_cycle = False
        for prereq in nodes.get(nid, {}).get("prerequisites", []):
            if prereq not in color:
                continue
            # 后向边: prereq 在当前递归栈 (path) 中 → 环
            if prereq in path:
                cycle = " → ".join(path[path.index(prereq):] + [prereq])
                errors.append(f"检测到循环依赖: {cycle}")
                found_cycle = True
                continue  # 继续找其它环, 不早退 (避免残留 GRAY)
            if color[prereq] == WHITE:
                if dfs(prereq, path):
                    found_cycle = True
        color[nid] = BLACK
        path.pop()
        return found_cycle

    for nid in nodes:
        if color[nid] == WHITE:
            dfs(nid, [])

    return errors


# ============================================================
# 用户画像校验
# ============================================================

def load_user_profiles(profiles_dir: Path) -> dict[str, dict]:
    """加载所有用户画像 JSON 文件，返回 {filename: profile} 映射"""
    profiles = {}
    if not profiles_dir.exists():
        return profiles
    for file_path in profiles_dir.glob("*.json"):
        if file_path.name == "profile_schema.json":
            continue
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            profiles[file_path.name] = data
        except json.JSONDecodeError as e:
            print(f"❌ JSON 解析错误: {file_path}: {e}")
    return profiles


def validate_user_profile(profile: dict, fname: str) -> list[str]:
    """校验单个用户画像（v3 格式）"""
    errors = []

    # --- 必填字段 ---
    required = [
        "profile_id", "name", "theory_level", "practical_level",
        "learning_style", "target_direction", "preferred_pace",
        "time_per_week", "known_topics", "weak_topics", "weakness_areas",
    ]
    for field in required:
        if field not in profile:
            errors.append(f"{fname}: 缺少必填字段 '{field}'")

    # --- profile_id 格式 ---
    pid = profile.get("profile_id", "")
    if pid and not re.match(r"^UP-[A-Z]{3}-[0-9a-f]{3,8}$", pid):
        errors.append(f"{fname}: profile_id 格式错误 '{pid}' (期望: UP-XXX-{{3~8位hex}})")

    # --- theory_level / practical_level 范围 ---
    for f in ["theory_level", "practical_level"]:
        val = profile.get(f)
        if val is not None and (not isinstance(val, int) or not (1 <= val <= 5)):
            errors.append(f"{fname}: {f} 超出范围 1-5 (当前: {val})")

    # --- learning_style 取值 ---
    valid_styles = {"visual", "auditory", "read_write", "kinesthetic"}
    ls = profile.get("learning_style")
    if ls is not None and ls not in valid_styles:
        errors.append(f"{fname}: learning_style 无效 '{ls}' (有效: {valid_styles})")

    # --- preferred_pace 取值 ---
    valid_paces = {"slow", "normal", "fast"}
    pp = profile.get("preferred_pace")
    if pp is not None and pp not in valid_paces:
        errors.append(f"{fname}: preferred_pace 无效 '{pp}' (有效: {valid_paces})")

    # --- time_per_week 范围 ---
    tpw = profile.get("time_per_week")
    if tpw is not None and (not isinstance(tpw, int) or tpw < 1 or tpw > 60):
        errors.append(f"{fname}: time_per_week 不合理: {tpw}")

    # --- known_topics / weak_topics 结构 ---
    for arr_field in ["known_topics", "weak_topics"]:
        arr = profile.get(arr_field, [])
        if not isinstance(arr, list):
            errors.append(f"{fname}: {arr_field} 必须是数组")
        else:
            for i, item in enumerate(arr):
                if not isinstance(item, dict):
                    errors.append(f"{fname}: {arr_field}[{i}] 必须是对象")
                elif "node_id" not in item:
                    errors.append(f"{fname}: {arr_field}[{i}] 缺少 'node_id'")
                elif not re.match(r"^[A-Z]{2}-\d{3}$", item.get("node_id", "")):
                    errors.append(f"{fname}: {arr_field}[{i}].node_id 格式错误 '{item.get('node_id')}'")
                if "mastery" not in item:
                    errors.append(f"{fname}: {arr_field}[{i}] 缺少 'mastery'")
                elif not isinstance(item["mastery"], (int, float)) or isinstance(item["mastery"], bool):
                    errors.append(f"{fname}: {arr_field}[{i}].mastery 非数值: {item['mastery']!r}")
                elif not (0 <= item["mastery"] <= 1):
                    errors.append(f"{fname}: {arr_field}[{i}].mastery 超出 0-1 (当前: {item['mastery']})")

    # --- weakness_areas 非空 ---
    wa = profile.get("weakness_areas", [])
    if not isinstance(wa, list) or len(wa) == 0:
        errors.append(f"{fname}: weakness_areas 必须是非空数组")

    # --- 交叉检查：weak_topics 中的 node_id 不应出现在 known_topics 中 ---
    known_ids = {item["node_id"] for item in profile.get("known_topics", []) if isinstance(item, dict) and "node_id" in item}
    for item in profile.get("weak_topics", []):
        if isinstance(item, dict) and item.get("node_id") in known_ids:
            errors.append(f"{fname}: {item['node_id']} 同时出现在 known_topics 和 weak_topics 中")

    # --- recommended_path 结构校验（对齐 profile_schema.json，BUG-023 字段统一） ---
    # 兼容历史字段 recommended_start_node(string)：若存在则提示废弃
    if "recommended_start_node" in profile:
        errors.append(
            f"{fname}: 字段 'recommended_start_node' 已废弃，应改用 'recommended_path' 对象"
            "(含 current_node/next_nodes/estimated_completion_weeks)"
        )
    rp = profile.get("recommended_path")
    if rp is not None:
        if not isinstance(rp, dict):
            errors.append(f"{fname}: recommended_path 必须是对象")
        else:
            cn = rp.get("current_node")
            if not isinstance(cn, str) or not re.match(r"^[A-Z]{2}-\d{3}$", cn or ""):
                errors.append(f"{fname}: recommended_path.current_node 格式错误 '{cn}' (期望: XX-000)")
            nn = rp.get("next_nodes")
            if not isinstance(nn, list):
                errors.append(f"{fname}: recommended_path.next_nodes 必须是数组")
            else:
                for i, nid in enumerate(nn):
                    if not isinstance(nid, str) or not re.match(r"^[A-Z]{2}-\d{3}$", nid):
                        errors.append(f"{fname}: recommended_path.next_nodes[{i}] 格式错误 '{nid}'")
            ecw = rp.get("estimated_completion_weeks")
            if ecw is not None and (not isinstance(ecw, int) or ecw < 1):
                errors.append(f"{fname}: recommended_path.estimated_completion_weeks 不合理: {ecw}")

    return errors


def main():
    if len(sys.argv) < 2:
        print("用法: python validate_data.py <knowledge_base_dir> [user_profiles_dir]")
        print("示例: python validate_data.py ../data/knowledge_base/ ../data/user_profiles/")
        sys.exit(1)

    base_dir = Path(sys.argv[1])
    if not base_dir.exists():
        print(f"❌ 目录不存在: {base_dir}")
        sys.exit(1)

    # 画像目录：第二参数 > 默认 data/user_profiles/
    if len(sys.argv) >= 3:
        profiles_dir = Path(sys.argv[2])
    else:
        profiles_dir = base_dir.parent / "user_profiles"

    schema_path = base_dir / "schema.json"
    if not schema_path.exists():
        print(f"❌ Schema 文件不存在: {schema_path}")
        sys.exit(1)

    print("=" * 60)
    print("  KMatch 数据验证 v3")
    print("=" * 60)

    # ================================================================
    # 阶段 1: 知识节点校验
    # ================================================================
    schema = load_schema(schema_path)
    print(f"\n📋 Schema: {schema.get('title', 'Unknown')}")

    nodes = load_knowledge_nodes(base_dir)
    print(f"📂 已加载 {len(nodes)} 个知识节点")

    if len(nodes) == 0:
        print("⚠️  未找到任何知识节点 JSON 文件！")
        kb_total_errors = 0
        node_errors = {}
        ref_errors = []
        cycle_errors = []
    else:
        # 统计
        categories = Counter(n.get("category", "未分类") for n in nodes.values())
        difficulties = Counter(str(n.get("difficulty", "?")) for n in nodes.values())
        questions_count = sum(len(n.get("practice_questions", [])) for n in nodes.values())
        print(f"   分类分布: {dict(categories)}")
        print(f"   难度分布: {dict(difficulties)}")
        print(f"   练习题总数: {questions_count}")

        # 逐节点校验
        print(f"\n🔍 逐节点校验...")
        node_errors = defaultdict(list)
        all_ids = set(nodes.keys())
        for nid, node in nodes.items():
            errors = validate_node(node, schema, all_ids)
            if errors:
                node_errors[nid].extend(errors)

        # 引用检查
        ref_errors = check_references(nodes)
        cycle_errors = check_circular_dependencies(nodes)

        kb_field_errors = sum(len(v) for v in node_errors.values())
        kb_total_errors = kb_field_errors + len(ref_errors) + len(cycle_errors)

        if kb_total_errors == 0:
            print(f"   ✅ 知识节点: {len(nodes)} 个，0 错误")
        else:
            print(f"   ❌ 知识节点: {kb_field_errors} 字段 + {len(ref_errors)} 引用 + {len(cycle_errors)} 循环 = {kb_total_errors} 错误")
            for nid, errs in node_errors.items():
                print(f"     [{nid}]:")
                for e in errs:
                    print(f"       - {e}")
            for e in ref_errors:
                print(f"     [引用] {e}")
            for e in cycle_errors:
                print(f"     [循环] {e}")

    # ================================================================
    # 阶段 1.5: 题目库校验 (questions/ 独立 :Question 节点数据源)
    # ================================================================
    questions_dir = str(base_dir / "questions")
    q_total, q_errors = validate_questions_dir(questions_dir, known_node_ids=set(nodes.keys()))
    q_total_errors = sum(len(v) for v in q_errors.values())

    if q_total == 0:
        print(f"\n📂 题目库: 未找到 ({questions_dir} 为空或不存在，可后续生成)")
    else:
        print(f"\n📂 题目库: {q_total} 道题 ({questions_dir})")
        if q_total_errors == 0:
            print(f"   ✅ 题目结构: {q_total} 道，0 错误")
        else:
            print(f"   ❌ 题目结构: {q_total_errors} 错误")
            for fname, errs in q_errors.items():
                print(f"     [{fname}]:")
                for e in errs:
                    print(f"       - {e}")

    # ================================================================
    # 阶段 2: 用户画像校验
    # ================================================================
    profiles = load_user_profiles(profiles_dir)

    if not profiles:
        print(f"\n📂 用户画像: 未找到 ({profiles_dir} 为空或不存在)")
        profile_errors = {}
        profile_total_errors = 0
    else:
        print(f"\n📂 已加载 {len(profiles)} 个用户画像 ({profiles_dir})")

        # 统计
        p_levels = Counter(str(p.get("theory_level", "?")) for p in profiles.values())
        p_styles = Counter(p.get("learning_style", "?") for p in profiles.values())
        print(f"   能力分布: {dict(p_levels)}")
        print(f"   学习风格: {dict(p_styles)}")

        print(f"\n🔍 逐画像校验...")
        profile_errors = {}
        for fname, profile in profiles.items():
            errors = validate_user_profile(profile, fname)
            if errors:
                profile_errors[fname] = errors

        profile_total_errors = sum(len(v) for v in profile_errors.values())

        if profile_total_errors == 0:
            print(f"   ✅ 用户画像: {len(profiles)} 个，0 错误")
        else:
            print(f"   ❌ 用户画像: {profile_total_errors} 错误")
            for fname, errs in profile_errors.items():
                print(f"     [{fname}]:")
                for e in errs:
                    print(f"       - {e}")

    # ================================================================
    # 汇总
    # ================================================================
    total_errors = kb_total_errors + q_total_errors + profile_total_errors
    kb_nodes = len(nodes)
    kb_field = kb_total_errors - len(ref_errors) - len(cycle_errors) if kb_nodes > 0 else 0

    print(f"\n{'=' * 60}")
    if total_errors == 0:
        print(f"  ✅ 全部通过！知识节点 {kb_nodes} + 题目 {q_total} + 画像 {len(profiles)}，0 错误")
    else:
        print(f"  ❌ 未通过！知识节点: {kb_total_errors} | 题目: {q_total_errors} | 画像: {profile_total_errors} 错误")
    print(f"{'=' * 60}")

    return 0 if total_errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
