"""
项目加载与解析编排

职责:
  - load_example_project(name): 扫 data/example_projects/{name}/*.py → {module_name: source}
  - load_text_source(code, filename): {stem: code} (前端直接传代码文本)
  - parse_project(project_id, sources): 编排 ast_parser + jedi_resolver，产出 ParsedProject

多文件支持: sources 是 {module_name: source}，逐模块解析后合并实体/关系，
Jedi 在单文件内解析 (跨文件解析需 project_path 磁盘上下文，本批示例单文件，列为已知限制)。
"""

from datetime import datetime, timezone
from pathlib import Path

from app.code_parser.ast_parser import attach_source_code, parse_module_source
from app.code_parser.jedi_resolver import resolve_calls
from app.code_parser.models import ParsedProject
from app.config import settings


EXAMPLE_PROJECTS_DIR = settings.DATA_DIR / "example_projects"


def load_example_project(name: str) -> dict[str, str]:
    """扫示例项目目录下所有 .py → {module_name(stem): source}。

    跳过 test_*.py (测试文件非项目本体) 和 __pycache__。
    路径安全: 拒绝多段/绝对路径 (防路径穿越 — name 为 API 输入)。
    """
    if not name or "/" in name or "\\" in name or name in (".", "..") or Path(name).is_absolute():
        raise FileNotFoundError(f"示例项目不存在: {name}")
    base = EXAMPLE_PROJECTS_DIR.resolve()
    project_dir = (base / name).resolve()
    if not project_dir.is_relative_to(base):
        raise FileNotFoundError(f"示例项目不存在: {name}")
    if not project_dir.is_dir():
        raise FileNotFoundError(f"示例项目不存在: {name}")

    sources: dict[str, str] = {}
    for py_file in sorted(project_dir.glob("*.py")):
        if py_file.name.startswith("test_"):
            continue
        sources[py_file.stem] = py_file.read_text(encoding="utf-8")
    if not sources:
        raise FileNotFoundError(f"示例项目 {name} 无可解析的 .py 文件")
    return sources


def load_text_source(code: str, filename: str = "main.py") -> dict[str, str]:
    """前端直接传代码文本 → {stem: code}。"""
    stem = Path(filename).stem or "main"
    return {stem: code}


def parse_project(project_id: str, sources: dict[str, str]) -> ParsedProject:
    """编排: 逐模块 ast 解析 → 回填 source_code → 合并 → jedi 精化 CALLS。

    Args:
        project_id: 项目 ID (构造 entity_id 命名空间)
        sources: {module_name: source}

    Returns:
        ParsedProject (含全部实体、CONTAINS/INHERITS/CALLS 关系)

    已知限制 (本批示例为单文件，多文件为下批):
      - entity_id = PROJ-{pid}-{TYPE}-{qualified_name}，不含 module_name。
        多文件项目若有同名 qualified_name (如两模块均有 main 函数)，entity_id 会撞，
        Neo4j 写入时产生重复节点。多文件需改为含 module 前缀的 entity_id。
      - Jedi 跨模块调用解析受限 (entity_map 仅含当前模块实体)，跨文件调用回退语法名匹配。
    """
    all_entities = []
    all_relations = []
    modules = list(sources.keys())

    for module_name, source in sources.items():
        # return_tree=True: 复用已解析 AST 回填 source_code, 免第二次 ast.parse (v1.3.3 提速)
        entities, relations, tree = parse_module_source(source, module_name, project_id, return_tree=True)
        attach_source_code(entities, source, tree=tree)

        # ast_parser 已把语法级 raw_calls 存入调用方 external_calls (无 col)。
        # 重建 raw_calls 列表补 col=0 供 Jedi；resolve_calls 会就地从 external_calls
        # 移除已解析为 CALLS 的项，剩余即真正未解析的外部调用。
        raw_calls: list[dict] = []
        for e in entities:
            for ec in e.external_calls:
                raw_calls.append({
                    "caller_entity_id": e.entity_id,
                    "callee_name": ec["name"],
                    "line": ec.get("line"),
                    "col": ec.get("col", 0),
                })

        call_relations = resolve_calls(
            raw_calls, source, f"{module_name}.py", entities, project_path=None,
        )
        all_entities.extend(entities)
        all_relations.extend(relations)
        all_relations.extend(call_relations)

    # 多文件撞名检测 (BUG B11 已知限制的防御):
    # entity_id 不含 module_name, 多模块同名 qualified_name (如各有一个 main 函数) 会撞,
    # Neo4j 写入产生重复节点、边可能连错。单文件不触发; 多文件撞名时去重保留首个并警告,
    # 避免静默重复。彻底修复需 entity_id 纳入 module 前缀 (破坏性, 演示后做)。
    if len(modules) > 1:
        seen: dict[str, str] = {}  # entity_id → module_name (首次出现)
        deduped = []
        collisions = []
        for e in all_entities:
            if e.entity_id in seen:
                collisions.append((e.entity_id, seen[e.entity_id], e.module_name))
                continue  # 丢弃撞名实体 (保留首个), 避免重复节点
            seen[e.entity_id] = e.module_name
            deduped.append(e)
        if collisions:
            import logging
            logging.getLogger(__name__).warning(
                "多文件 entity_id 撞名 %d 处 (entity_id 不含 module), 已去重保留首个: %s",
                len(collisions), collisions[:3],
            )
            all_entities = deduped

    return ParsedProject(
        project_id=project_id,
        modules=modules,
        entities=all_entities,
        relations=all_relations,
        parsed_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )


def list_example_projects() -> list[dict]:
    """列出可用示例项目 → [{name, file_count, description}]。

    description 取项目主文件 (main.py) 首行模块 docstring。
    """
    if not EXAMPLE_PROJECTS_DIR.is_dir():
        return []

    result = []
    for d in sorted(EXAMPLE_PROJECTS_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith(".") or d.name.startswith("_"):
            continue
        py_files = [f for f in d.glob("*.py") if not f.name.startswith("test_")]
        if not py_files:
            continue
        description = _extract_description(d)
        result.append({
            "name": d.name,
            "file_count": len(py_files),
            "description": description,
        })
    return result


def _extract_description(project_dir: Path) -> str:
    """取项目主文件 (main.py 优先) 的模块 docstring 首段作为描述。"""
    main_file = project_dir / "main.py"
    if not main_file.exists():
        py_files = list(project_dir.glob("*.py"))
        if not py_files:
            return ""
        main_file = py_files[0]
    try:
        import ast
        tree = ast.parse(main_file.read_text(encoding="utf-8"))
        doc = ast.get_docstring(tree)
        return (doc or "").strip().split("\n")[0]
    except Exception:
        return ""
