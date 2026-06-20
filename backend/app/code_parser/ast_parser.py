"""
Python AST 代码解析器 (纯函数，无副作用)

用 ast 模块提取项目代码的结构信息: 模块、类、函数、方法、参数注解、返回类型、
docstring、装饰器、继承关系、调用关系 (语法级)。

安全性: ast.parse 只解析语法树不执行代码，解析阶段零风险。
        (code_tester 的 AST 安全检查将复用本模块，见 06_code_tester_agent.txt)

调用关系 (CALLS) 这里只提取语法级原始调用 (raw_calls):
  - ast.Call.func 为 Attribute → "{value}.{attr}" (如 self.fetch_page、storage.get_all)
  - ast.Call.func 为 Name → id (如 urljoin、SimpleCrawler)
语义级精化 (解析 self.x / 局部变量.x 到具体定义) 由 jedi_resolver 完成。
"""

import ast
from typing import Optional

from app.code_parser.models import (
    CodeEntity,
    CodeRelation,
    EntityType,
    LAYER_ENTITY,
    LAYER_FRAMEWORK,
)


def make_entity_id(project_id: str, kind: EntityType, qualified_name: str) -> str:
    """构造项目内唯一 entity_id: PROJ-{pid}-{TYPE}-{qualified_name}。"""
    type_tag = kind.upper()  # MODULE/CLASS/FUNCTION/METHOD
    return f"PROJ-{project_id}-{type_tag}-{qualified_name}"


def parse_module_source(
    source: str,
    module_name: str,
    project_id: str,
) -> tuple[list[CodeEntity], list[CodeRelation]]:
    """解析单个模块源码，返回 (实体列表, 关系列表)。

    产出:
      - Module 实体 (layer=2)
      - 顶层 Class/Function 实体 + Class 内方法 (layer=2/3)
      - CONTAINS 关系 (Module→顶层, Class→方法)
      - INHERITS 关系 (Class→项目内基类，按简单名匹配)
      - raw_calls (语法级调用，未解析语义) 存入调用方实体 external_calls，
        语义精化由 jedi_resolver 后续处理 (本函数不产出 CALLS 关系)

    Args:
        source: 模块源码字符串
        module_name: 模块名 (文件 stem)
        project_id: 项目 ID (构造 entity_id 命名空间)

    Raises:
        SyntaxError: 源码语法错误 (由 API 层转 422)
    """
    tree = ast.parse(source)  # 不执行代码，安全

    entities: list[CodeEntity] = []
    relations: list[CodeRelation] = []

    # Module 实体
    module_qname = module_name
    module_entity = CodeEntity(
        entity_id=make_entity_id(project_id, "module", module_qname),
        project_id=project_id,
        kind="module",
        name=module_name,
        qualified_name=module_qname,
        module_name=module_name,
        layer=LAYER_FRAMEWORK,
        line_start=1,
        line_end=len(source.splitlines()) or 1,
        docstring=ast.get_docstring(tree),
        source_code=None,  # 模块整体源码不存 (体积大)，前端按 line 范围取
    )
    entities.append(module_entity)

    # 收集所有 raw_calls (供 jedi_resolver 精化)
    # raw_call: {caller_entity_id, callee_name, line, col}
    raw_calls: list[dict] = []

    # 第一遍: 提取顶层 Class/Function，记录 CONTAINS
    # 类内方法在 _extract_class 内处理 (含 Class→Method CONTAINS)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func = _extract_function(node, project_id, module_name, qualified_prefix="", parent_class_id=None)
            entities.append(func)
            relations.append(CodeRelation(source=module_entity.entity_id, target=func.entity_id, type="CONTAINS"))
            _collect_calls(node, func.entity_id, raw_calls)
        elif isinstance(node, ast.ClassDef):
            cls_entity, methods, class_rels = _extract_class(node, project_id, module_name, qualified_prefix="")
            entities.append(cls_entity)
            entities.extend(methods)
            relations.extend(class_rels)
            relations.append(CodeRelation(source=module_entity.entity_id, target=cls_entity.entity_id, type="CONTAINS"))
            # 类是容器，调用发生在方法体内 —— 只对各方法收集，不对 ClassDef 整体 walk
            # (否则 ast.walk 会遍历所有方法体，把方法调用错误归到类实体并与方法重复)
            for m in methods:
                _collect_calls(_find_func_node(node, m.name), m.entity_id, raw_calls)

    # 第二遍: INHERITS — Class bases 匹配项目内同简单名实体
    class_by_name: dict[str, str] = {}
    for e in entities:
        if e.kind == "class":
            class_by_name[e.name] = e.entity_id
    for e in entities:
        if e.kind == "class":
            for base_name in _simple_names(e.bases):
                target = class_by_name.get(base_name)
                if target and target != e.entity_id:
                    relations.append(CodeRelation(source=e.entity_id, target=target, type="INHERITS"))

    # 把 raw_calls 暂存到调用方实体的 external_calls (jedi_resolver 会移除可解析项并产出 CALLS)
    # 保留 col: Jedi infer 需要准确列号定位调用表达式
    entity_by_id = {e.entity_id: e for e in entities}
    for rc in raw_calls:
        caller = entity_by_id.get(rc["caller_entity_id"])
        if caller is not None:
            caller.external_calls.append({
                "name": rc["callee_name"],
                "line": rc["line"],
                "col": rc["col"],
            })

    return entities, relations


def _find_func_node(class_node: ast.ClassDef, func_name: str) -> Optional[ast.AST]:
    """在 ClassDef.body 中按名查找函数节点 (供 _collect_calls 用)。"""
    for n in class_node.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == func_name:
            return n
    return None


def _extract_class(
    node: ast.ClassDef,
    project_id: str,
    module_name: str,
    qualified_prefix: str,
) -> tuple[CodeEntity, list[CodeEntity], list[CodeRelation]]:
    """提取 Class 实体 + 其方法 + Class→Method CONTAINS 关系。"""
    qname = _qualified_name(qualified_prefix, node.name)
    cls_entity = CodeEntity(
        entity_id=make_entity_id(project_id, "class", qname),
        project_id=project_id,
        kind="class",
        name=node.name,
        qualified_name=qname,
        module_name=module_name,
        layer=LAYER_FRAMEWORK,
        line_start=node.lineno,
        line_end=_end_line(node),
        docstring=ast.get_docstring(node),
        bases=[_unparse_safe(b) for b in node.bases],
        decorators=[_unparse_safe(d) for d in node.decorator_list],
        source_code=None,  # 类源码较大，按需由前端取 line 范围; 方法单独存
    )

    methods: list[CodeEntity] = []
    relations: list[CodeRelation] = []
    for sub in node.body:
        if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
            method = _extract_function(
                sub, project_id, module_name,
                qualified_prefix=qname, parent_class_id=cls_entity.entity_id,
            )
            methods.append(method)
            relations.append(CodeRelation(source=cls_entity.entity_id, target=method.entity_id, type="CONTAINS"))

    return cls_entity, methods, relations


def _extract_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    project_id: str,
    module_name: str,
    qualified_prefix: str,
    parent_class_id: Optional[str],
) -> CodeEntity:
    """提取 Function/Method 实体。"""
    qname = _qualified_name(qualified_prefix, node.name)
    is_method = parent_class_id is not None
    kind: EntityType = "method" if is_method else "function"
    # 方法属于代码实体层 (layer=3)；模块级函数属于项目框架层 (layer=2)
    layer = LAYER_ENTITY if is_method else LAYER_FRAMEWORK

    return CodeEntity(
        entity_id=make_entity_id(project_id, kind, qname),
        project_id=project_id,
        kind=kind,
        name=node.name,
        qualified_name=qname,
        module_name=module_name,
        layer=layer,
        line_start=node.lineno,
        line_end=_end_line(node),
        docstring=ast.get_docstring(node),
        params=_extract_params(node.args),
        return_type=_unparse_safe(node.returns) if node.returns is not None else None,
        decorators=[_unparse_safe(d) for d in node.decorator_list],
        source_code=None,  # attach_source_code 回填 (需原始 source)
        is_method=is_method,
        parent_class_id=parent_class_id,
    )


def attach_source_code(entities: list[CodeEntity], source: str) -> None:
    """用 ast.get_source_segment 为函数/方法实体回填 source_code。

    单独成函数: parse_module_source 已 ast.parse 一次，这里需重 parse 以拿到节点行号映射。
    为控制体积，仅函数/方法存 source (类/模块不存)。
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return

    # 建立 qualified_name → source_segment 映射
    seg_map: dict[str, str] = {}

    def walk(node: ast.AST, prefix: str) -> None:
        for sub in ast.iter_child_nodes(node):
            if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qname = _qualified_name(prefix, sub.name)
                seg = ast.get_source_segment(source, sub)
                if seg is not None:
                    seg_map[qname] = seg
                walk(sub, qname)  # 支持嵌套
            elif isinstance(sub, ast.ClassDef):
                walk(sub, _qualified_name(prefix, sub.name))

    walk(tree, "")

    for e in entities:
        if e.kind in ("function", "method") and e.qualified_name in seg_map:
            e.source_code = seg_map[e.qualified_name]


def _extract_params(args: ast.arguments) -> list[dict]:
    """提取参数列表: [{name, annotation, default, kind}]。

    kind: positional | vararg | kwonly | kwarg
    """
    params: list[dict] = []

    # 位置参数 (含 posonlyargs)
    pos_defaults = list(args.defaults)
    # defaults 对齐最后 n 个 pos/posonly 参数
    posonly = list(args.posonlyargs)
    normal = list(args.args)
    all_pos = posonly + normal
    n_with_default = len(pos_defaults)
    for i, arg in enumerate(all_pos):
        # 是否有默认值: 最后 n_with_default 个位置参数
        has_default = i >= len(all_pos) - n_with_default
        default = None
        if has_default:
            default_idx = i - (len(all_pos) - n_with_default)
            default = _unparse_safe(pos_defaults[default_idx]) if 0 <= default_idx < len(pos_defaults) else None
        params.append({
            "name": arg.arg,
            "annotation": _unparse_safe(arg.annotation) if arg.annotation is not None else None,
            "default": default,
            "kind": "posonly" if arg in posonly else "positional",
        })

    if args.vararg is not None:
        params.append({
            "name": args.vararg.arg,
            "annotation": _unparse_safe(args.vararg.annotation) if args.vararg.annotation is not None else None,
            "default": None,
            "kind": "vararg",
        })

    # kwonly 参数
    for i, arg in enumerate(args.kwonlyargs):
        default = None
        if i < len(args.kw_defaults) and args.kw_defaults[i] is not None:
            default = _unparse_safe(args.kw_defaults[i])
        params.append({
            "name": arg.arg,
            "annotation": _unparse_safe(arg.annotation) if arg.annotation is not None else None,
            "default": default,
            "kind": "kwonly",
        })

    if args.kwarg is not None:
        params.append({
            "name": args.kwarg.arg,
            "annotation": _unparse_safe(args.kwarg.annotation) if args.kwarg.annotation is not None else None,
            "default": None,
            "kind": "kwarg",
        })

    return params


def _collect_calls(node: ast.AST, caller_entity_id: str, raw_calls: list[dict]) -> None:
    """遍历节点子树收集语法级调用 (ast.Call)，产出 raw_call 记录。

    raw_call: {caller_entity_id, callee_name, line, col}
    callee_name:
      - Attribute 调用 (a.b()) → "{ast.unparse(value)}.{attr}" (如 self.fetch_page、storage.get_all)
      - Name 调用 (foo()) → id (如 urljoin、SimpleCrawler)
    col 精确指向被调用名标识符 (Name→name 起始; Attribute→attr 起始)，
    供 Jedi infer 准确定位。Attribute 的 attr 位置 = value.end_col_offset + 1 (跳过点号)。
    """
    if node is None:
        return
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            callee_name, line, col = _call_position(sub.func)
            if callee_name:
                raw_calls.append({
                    "caller_entity_id": caller_entity_id,
                    "callee_name": callee_name,
                    "line": line,
                    "col": col,
                })


def _call_position(func: ast.AST) -> tuple[Optional[str], Optional[int], Optional[int]]:
    """从 ast.Call.func 提取 (语法级被调用名, line, col)。

    返回被调用名标识符的准确位置，供 Jedi infer 定位:
      - Name 调用 (foo()) → ("foo", func.lineno, func.col_offset)
      - Attribute 调用 (a.b()) → ("a.b", func.lineno, attr 起始列)
        attr 起始列 = value.end_col_offset + 1 (跳过点号)
    """
    if isinstance(func, ast.Name):
        return func.id, func.lineno, func.col_offset
    if isinstance(func, ast.Attribute):
        base = _unparse_safe(func.value)
        name = f"{base}.{func.attr}" if base else func.attr
        # attr 标识符起始列: value 结束列 + 1 (点号占 1 列)
        value_end = getattr(func.value, "end_col_offset", None)
        col = (value_end + 1) if value_end is not None else func.col_offset
        return name, func.lineno, col
    # 其他形式 (如 foo()() 的内层、lambda 调用) 不处理
    return None, None, None


def _callee_name(func: ast.AST) -> Optional[str]:
    """从 ast.Call.func 提取语法级被调用名 (仅名，无位置)。"""
    name, _line, _col = _call_position(func)
    return name


def _qualified_name(prefix: str, name: str) -> str:
    """点分路径: prefix 为空返回 name，否则 prefix.name。"""
    return f"{prefix}.{name}" if prefix else name


def _simple_names(bases: list[str]) -> list[str]:
    """从 bases 的 unparse 字符串取最末简单名 (如 'module.Base' → 'Base')。"""
    result = []
    for b in bases:
        if not b:
            continue
        result.append(b.split(".")[-1])
    return result


def _end_line(node: ast.AST) -> int:
    """取节点结束行 (优先 end_lineno，回退 lineno)。"""
    return getattr(node, "end_lineno", None) or getattr(node, "lineno", 1)


def _unparse_safe(node: Optional[ast.AST]) -> Optional[str]:
    """ast.unparse 安全包装 (None → None，异常 → None)。"""
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:
        return None
