"""
代码 AST 安全检查 (硬规则) — 纯 Python, 无重依赖。

从 code_reviewer.py 抽离, 供 chat 等轻量路径 (如 write_file 审批门) 复用,
避免 import code_reviewer 时连带拉入 langchain / neo4j。

职责:
  - hard_check_code_safety: ast.parse 不执行代码, 检测危险调用 + 无限循环风险
  - 返回 issues 列表 (severity/dimension/problem/line)

对齐 06_code_tester_agent.txt "所有代码先经过 AST 安全检查"。
"""

from __future__ import annotations

import ast
from typing import Optional


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
