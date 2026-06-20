"""
代码审查 Agent (Code Reviewer)

场景二 Step 6①: 用户提交修改后的代码 → 内容审核 Agent 做代码审查
（对照领域规范检查逻辑错误、代码规范、安全隐患）。

计划书 W6 A 端 ③："实现内容审核Agent的代码审查逻辑（对照领域规范检查逻辑错误/安全隐患）"。

属内容审核 Agent (reviewer) 的代码审查能力，独立成模块避免 reviewer.py 膨胀。
场景二 with_project workflow 编排时由 reviewer 节点调用本模块（编排属后续步骤）。

两阶段审查:
  1. 硬规则 AST 安全检查 (复用 code_parser ast.parse，不执行代码):
     - 危险调用 (os.system/eval/exec/compile/subprocess/socket/pickle.load 等)
     - 无限循环风险 (while True 无 break)
     对齐 06_code_tester_agent.txt "所有代码先经过 AST 安全检查"
  2. LLM 语义审查 (对照领域元知识 key_points/common_mistakes + 开发目标):
     - 逻辑错误 / 安全隐患 / 代码规范 / 领域规范符合度

代码审查四维度 (与内容审核四维度不同，但同为 {dim:{score,issues}} 结构，B 端 .score 访问安全):
  - logic_correctness   逻辑正确性 (权重 0.4)
  - security            安全性 (权重 0.3)
  - code_quality        代码规范质量 (权重 0.2)
  - domain_compliance   领域规范符合度 (权重 0.1)
"""

import ast
import json
from datetime import datetime
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.llm import get_default_chat_model, llm_configured
from app.config import settings
from app.graph.engine import KnowledgeGraph
from app.utils.json_utils import parse_llm_json
from app.utils.logging import get_logger

logger = get_logger(__name__)


# ============================================================
# 代码审查维度 (与内容审核四维度不同)
# ============================================================

CODE_REVIEW_DIMENSIONS = ("logic_correctness", "security", "code_quality", "domain_compliance")

CODE_REVIEW_WEIGHTS = {
    "logic_correctness": 0.4,
    "security": 0.3,
    "code_quality": 0.2,
    "domain_compliance": 0.1,
}


# ============================================================
# 硬规则: AST 安全检查 (不执行代码)
# ============================================================

# 危险调用模式: (模块, 属性/函数名) 或 (None, 内建名)
# 命中即标记 high severity security 问题
_DANGEROUS_CALLS = {
    # 系统命令执行
    ("os", "system"), ("os", "popen"), ("os", "exec"), ("os", "execv"), ("os", "spawn"),
    # 动态执行
    (None, "eval"), (None, "exec"), (None, "compile"),
    ("builtins", "eval"), ("builtins", "exec"),
    # 子进程
    ("subprocess", "run"), ("subprocess", "Popen"), ("subprocess", "call"),
    ("subprocess", "check_call"), ("subprocess", "check_output"),
    # 网络 (场景二教学代码通常不应直接裸 socket)
    ("socket", "socket"),
    # 反序列化 (pickle 远程加载 = RCE 风险)
    ("pickle", "load"), ("pickle", "loads"),
    ("yaml", "load"),  # yaml.load 不加 Loader 不安全
    # shell
    ("shlex", "split"),  # 仅在与 shell 组合时危险，这里降级提示
    # 文件系统危险 (教学场景提醒)
    ("shutil", "rmtree"),
}

# 危险内建名 (ast.Name 直接调用)
_DANGEROUS_BUILTINS = {"eval", "exec", "compile", "__import__", "globals", "locals"}


def _call_identifier(node: ast.Call) -> tuple[Optional[str], str]:
    """提取 ast.Call 的 (模块名或 None, 调用名)。

    os.system(...) → ("os", "system"); eval(...) → (None, "eval")
    返回 (None, "") 表示无法识别。
    """
    func = node.func
    if isinstance(func, ast.Name):
        return None, func.id
    if isinstance(func, ast.Attribute):
        # func.value 是模块名 (ast.Name) → 取 id；否则 (如 self.x) 不判
        if isinstance(func.value, ast.Name):
            return func.value.id, func.attr
        return None, func.attr
    return None, ""


def hard_check_code_safety(code: str) -> list[dict]:
    """AST 安全检查硬规则: 检测危险调用 + 无限循环风险。

    ast.parse 不执行代码，安全。返回 issues 列表 (severity/dimension/problem/line)。
    SyntaxError → 单条 high 问题 (代码无法审查)。
    """
    issues: list[dict] = []
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        issues.append({
            "severity": "high",
            "dimension": "code_quality",
            "problem": f"代码语法错误，无法完成审查: {e.msg} (行 {e.lineno})",
            "line": e.lineno,
        })
        return issues

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            module, name = _call_identifier(node)
            # 内建危险调用
            if module is None and name in _DANGEROUS_BUILTINS:
                issues.append({
                    "severity": "high",
                    "dimension": "security",
                    "problem": f"调用危险内建 {name}() (行 {node.lineno})，存在代码注入/任意执行风险",
                    "line": node.lineno,
                })
                continue
            # 模块.属性 危险调用
            if (module, name) in _DANGEROUS_CALLS:
                issues.append({
                    "severity": "high",
                    "dimension": "security",
                    "problem": f"调用 {module}.{name}() (行 {node.lineno})，存在安全风险，请评估是否必要并做防护",
                    "line": node.lineno,
                })

    # 无限循环风险: while True 无 break
    for node in ast.walk(tree):
        if isinstance(node, ast.While):
            if _is_constant_true(node.test) and not _has_break(node):
                issues.append({
                    "severity": "medium",
                    "dimension": "logic_correctness",
                    "problem": f"while True 循环 (行 {node.lineno}) 未见 break，存在无限循环风险",
                    "line": node.lineno,
                })

    return issues


def _is_constant_true(test: ast.AST) -> bool:
    """判断 while 条件是否恒真 (True / 1 / 非零常量)。"""
    if isinstance(test, ast.Constant):
        return bool(test.value)
    return False


def _has_break(node: ast.AST) -> bool:
    """判断循环体 (while/for) 内是否有属于【本层】循环的 break。

    BUG B9: ast.walk 递归遍历所有后代, 会命中嵌套函数/类/内层循环里的 break,
    导致 while True 假阴性 —— 如:
        while True:           # 真无限循环
            for x in y:
                break         # 属于 for, 不 break while → 旧代码误判"有break"漏放
    正确: 仅统计本层 break; 遇嵌套 (Async)FunctionDef/ClassDef 不下钻 (作用域隔离),
    遇嵌套循环 (For/While) 不把其 break 算作本层的 (break 只跳出最近的循环)。
    """
    # 嵌套作用域: 进入这些节点后, 其内的 break 不属于外层循环
    _SCOPE_BARRIER = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    # 嵌套循环: 其 break 属于它自己, 不属于外层
    _LOOP = (ast.For, ast.AsyncFor, ast.While)

    def _scan(n):
        for child in ast.iter_child_nodes(n):
            if isinstance(child, ast.Break):
                return True
            # 跨越作用域屏障/嵌套循环: 不下钻找 break (它们的 break 不属于本层)
            if isinstance(child, _SCOPE_BARRIER) or isinstance(child, _LOOP):
                continue
            if _scan(child):
                return True
        return False

    return _scan(node)


# ============================================================
# LLM 语义审查 (对照领域规范)
# ============================================================

def _build_knowledge_context(knowledge_nodes: list[dict]) -> str:
    """把相关领域知识点 (key_points/common_mistakes) 组织成 LLM 上下文。"""
    if not knowledge_nodes:
        return "(未检索到相关领域知识点，仅按通用 Python 规范审查)"
    lines = []
    for n in knowledge_nodes:
        nid = n.get("node_id") or n.get("id", "")
        name = n.get("name", "")
        kps = n.get("key_points", [])
        mistakes = n.get("common_mistakes", [])
        lines.append(f"- [{nid}] {name}")
        if kps:
            lines.append(f"  key_points: {json.dumps(kps, ensure_ascii=False)}")
        if mistakes:
            lines.append(f"  common_mistakes: {json.dumps(mistakes, ensure_ascii=False)}")
    return "\n".join(lines)


def llm_review_code(code: str, target_direction: str, knowledge_nodes: list[dict]) -> dict:
    """LLM 对照领域规范审查代码，返回四维度评分。

    对照领域元知识 key_points/common_mistakes + 开发目标，检查:
      - logic_correctness: 逻辑错误、边界、类型、控制流
      - security: 安全隐患 (注入/敏感信息/危险操作)
      - code_quality: 命名/结构/可读性/重复
      - domain_compliance: 是否符合领域规范 (key_points/common_mistakes)
    """
    model = get_default_chat_model()
    system = SystemMessage(content=(
        "你是 KMatch 代码审查 Agent，审查用户提交的修改后 Python 代码。"
        "对照领域元知识规范 (key_points/common_mistakes) 与开发目标，"
        "从四个维度审查并打分(0-1)，指出问题与修改建议。"
        "严格输出 JSON: "
        '{"logic_correctness":{"score":0-1,"issues":[]},'
        '"security":{"score":0-1,"issues":[]},'
        '"code_quality":{"score":0-1,"issues":[]},'
        '"domain_compliance":{"score":0-1,"issues":[]}}。'
        "issues 元素: {severity(high|medium|low),problem,location,suggestion}。"
        "不输出 JSON 以外文字。"
    ))
    # 截断超长代码避免 token 爆炸
    code_payload = code if len(code) <= 6000 else code[:6000] + "\n# ...(截断)"
    user = HumanMessage(content=(
        f"开发目标: {target_direction}\n\n"
        f"相关领域知识规范:\n{_build_knowledge_context(knowledge_nodes)}\n\n"
        f"待审代码:\n```python\n{code_payload}\n```\n\n"
        "审查要点: 逻辑是否正确(边界/类型/控制流)；是否存在安全隐患(注入/危险操作/敏感信息)；"
        "代码规范(命名/结构/可读性)；是否符合领域规范(common_mistakes 提到的误区是否触犯)。"
    ))
    resp = model.invoke([system, user])
    return parse_llm_json(resp.content)


# ============================================================
# 维度归一化 / 加权 (复用 reviewer 模式，但维度集不同)
# ============================================================

def _default_code_dims() -> dict:
    """LLM 失败/未配置时四维度默认满分。"""
    return {dim: {"score": 1.0, "issues": []} for dim in CODE_REVIEW_DIMENSIONS}


def _normalize_code_dims(dims) -> dict:
    """归一化 LLM 代码审查输出为 {dim:{score,issues}}。非 conforming → 默认满分。"""
    if not isinstance(dims, dict) or not dims:
        return _default_code_dims()
    normalized = {}
    for dim in CODE_REVIEW_DIMENSIONS:
        val = dims.get(dim, {})
        if not isinstance(val, dict):
            val = {"score": val} if isinstance(val, (int, float)) else {}
        score = val.get("score", 1.0)
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            score = 1.0
        issues = val.get("issues", [])
        if not isinstance(issues, list):
            issues = []
        normalized[dim] = {"score": float(score), "issues": issues}
    return normalized


def _merge_code_issues(dims: dict, hard_issues: list[dict]) -> dict:
    """把硬规则问题并入对应维度，有问题的维度分数上限下调至 0.6。

    BUG B12: 仅对被 hard_issues 命中的维度封顶 (与 reviewer._merge_issues 一致),
    避免 LLM 已带 issues 的维度被二次封顶 = 双重惩罚误打回。
    """
    hard_hit_dims: set[str] = set()
    for issue in hard_issues:
        dim = issue.get("dimension", "security")
        dims.setdefault(dim, {"score": 1.0, "issues": []})
        dims[dim]["issues"].append(issue)
        hard_hit_dims.add(dim)
    for dim in hard_hit_dims:
        data = dims[dim]
        data["score"] = min(data.get("score", 1.0), 0.6)
    return dims


def _weighted_code_score(dims: dict) -> float:
    """代码审查四维度加权 (0.4/0.3/0.2/0.1)。"""
    total = 0.0
    for dim, w in CODE_REVIEW_WEIGHTS.items():
        total += w * dims.get(dim, {"score": 0.0}).get("score", 0.0)
    return round(total, 3)


def _build_code_review_hint(dims: dict) -> str:
    """从各维度问题生成可操作的打回提示。"""
    hints = []
    for dim in CODE_REVIEW_DIMENSIONS:
        for issue in dims.get(dim, {}).get("issues", [])[:2]:
            hints.append(issue.get("problem", ""))
    return "；".join(hints) if hints else "请修正审查标记的问题后重新提交"


# ============================================================
# 编排: review_code
# ============================================================

def _retrieve_knowledge(kg: KnowledgeGraph, target_direction: str,
                        knowledge_node_ids: Optional[list[str]] = None,
                        top_k: int = 5) -> list[dict]:
    """检索与开发目标相关的领域知识点作为审查规范。

    优先用用户指定的 node_ids；否则按 target_direction 语义检索 (embedding 可用)，
    不可用则空 (LLM 按通用规范审)。
    """
    if knowledge_node_ids:
        nodes = []
        for nid in knowledge_node_ids:
            n = kg.get_node(nid)
            if n:
                nodes.append(n)
        return nodes

    # 语义检索 (embedding 未配置时降级为空)
    try:
        return kg.semantic_search(query=target_direction, top_k=top_k)
    except Exception:
        logger.warning("领域知识语义检索失败，代码审查按通用规范", exc_info=True)
        return []


def review_code(
    kg: KnowledgeGraph,
    code: str,
    target_direction: str,
    knowledge_node_ids: Optional[list[str]] = None,
) -> dict:
    """代码审查编排: 硬规则 AST 安全检查 + LLM 对照领域规范审查。

    Args:
        kg: KnowledgeGraph (检索领域规范)
        code: 用户提交的修改后代码
        target_direction: 开发目标 (检索相关知识点 + LLM 上下文)
        knowledge_node_ids: 用户指定的相关知识点 (可选，否则按 target_direction 检索)

    Returns:
        review_results dict {passed, overall_score, threshold, dimensions, verdict,
        retry_hint, reviewed_at} — 与内容审核 review_results 同构，B 端契约一致。
    """
    # 1. 硬规则 AST 安全检查
    hard_issues = hard_check_code_safety(code)
    # 语法错误 → 直接判不通过 (无法审查)
    if any(i.get("dimension") == "code_quality" and "语法错误" in i.get("problem", "") for i in hard_issues):
        return {
            "passed": False,
            "overall_score": 0.0,
            "threshold": settings.REVIEW_PASS_THRESHOLD,
            "dimensions": _default_code_dims(),
            "verdict": "reject",
            "retry_hint": "代码存在语法错误，无法完成审查，请修正语法后重新提交",
            "reviewed_at": datetime.utcnow().isoformat() + "Z",
        }
    # 高危安全问题 → 一票否决 (eval/exec/os.system 等不应因其他维度高分而通过)
    high_security = [i for i in hard_issues
                     if i.get("dimension") == "security" and i.get("severity") == "high"]
    if high_security:
        dims = _default_code_dims()
        dims = _merge_code_issues(dims, hard_issues)
        problems = "；".join(i.get("problem", "") for i in high_security)
        return {
            "passed": False,
            "overall_score": _weighted_code_score(dims),
            "threshold": settings.REVIEW_PASS_THRESHOLD,
            "dimensions": dims,
            "verdict": "reject",
            "retry_hint": f"检测到高危安全问题，一票否决: {problems}",
            "reviewed_at": datetime.utcnow().isoformat() + "Z",
        }

    # 2. 检索相关领域知识点
    knowledge_nodes = _retrieve_knowledge(kg, target_direction, knowledge_node_ids)

    # 3. LLM 语义审查
    dims = {}
    if llm_configured():
        try:
            dims = llm_review_code(code, target_direction, knowledge_nodes)
        except Exception:
            logger.warning("LLM 代码审查调用失败，降级为仅硬规则评分", exc_info=True)
            dims = {}
    dims = _normalize_code_dims(dims) if dims else _default_code_dims()

    # 4. 硬规则问题并入维度
    dims = _merge_code_issues(dims, hard_issues)
    overall = _weighted_code_score(dims)
    passed = overall >= settings.REVIEW_PASS_THRESHOLD

    return {
        "passed": passed,
        "overall_score": overall,
        "threshold": settings.REVIEW_PASS_THRESHOLD,
        "dimensions": dims,
        "verdict": "pass" if passed else "reject",
        "retry_hint": "" if passed else _build_code_review_hint(dims),
        "reviewed_at": datetime.utcnow().isoformat() + "Z",
    }
