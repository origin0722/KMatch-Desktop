"""
Jedi 语义级调用解析器

将 ast_parser 产出的语法级 raw_calls 精化为 CALLS 关系:
  - jedi.Script(...).infer(line, col) 解析调用目标定义
  - 解析到项目内实体 → 产出 CALLS 关系 (resolved=True)，并从调用方 external_calls 移除该项
  - 解析到外部库/内建/失败 → 保留在 external_calls，不建边
  - Jedi 异常或返回空 → 回退语法名匹配 (entity_map 按 callee_name 查)，匹配到则 CALLS(resolved=False)

Jedi 的价值 (纯 AST 做不到):
  - self.fetch_page(url)    → AST 只知 "self.fetch_page"，Jedi 类型推断解析到 SimpleCrawler.fetch_page
  - crawler.crawl(url)      → 局部变量 crawler，Jedi 解析到 SimpleCrawler.crawl
  - storage.get_all()       → 解析到 TodoStorage.get_all

最佳努力 + 降级: Jedi 在 Windows/不同 Python 版本行为有差异，任何异常都不影响主流程。
"""

import logging
from typing import Optional

import jedi

from app.code_parser.models import CodeEntity, CodeRelation

logger = logging.getLogger(__name__)

# 单模块 Jedi infer 调用上限 (v1.3.3 提速: 每个 raw_call 一次 infer, 大文件数千调用时
# Jedi 解析占解析耗时大头; 超限部分直接走语法名回退, 语义边损失有界且可接受)
MAX_JEDI_INFER_CALLS = 300


def resolve_calls(
    raw_calls: list[dict],
    source: str,
    filename: str,
    entities: list[CodeEntity],
    project_path: Optional[str] = None,
) -> list[CodeRelation]:
    """精化 raw_calls 为 CALLS 关系。

    Args:
        raw_calls: ast_parser 产出的 [{caller_entity_id, callee_name, line, col}]
        source: 该模块源码 (Jedi 需要)
        filename: 该模块文件名 (Jedi path 参数，影响跨文件解析)
        entities: 该模块解析出的全部实体 (构建 entity_map)
        project_path: 项目根路径 (Jedi 跨文件解析用，None 则仅单文件内解析)

    Returns:
        CALLS 关系列表。同时会从调用方实体的 external_calls 中移除已解析项 (就地修改)。
    """
    if not raw_calls:
        return []

    # qualified_name → entity_id; 同时建 简单名 → entity_id 兜底映射
    entity_by_qname: dict[str, str] = {}
    entity_by_simple: dict[str, list[str]] = {}  # 简单名可能重名 (不同类同名方法)
    for e in entities:
        entity_by_qname[e.qualified_name] = e.entity_id
        entity_by_simple.setdefault(e.name, []).append(e.entity_id)

    entity_by_id = {e.entity_id: e for e in entities}

    # 构建 Jedi Script (失败则全量回退语法名匹配)
    script: Optional[jedi.Script] = None
    # 源码行列表: 用于字节偏移→字符偏移转换 (BUG B10)
    source_lines = source.splitlines() if source else []
    try:
        script = jedi.Script(source, path=filename if project_path is None else (project_path + "/" + filename))
    except Exception:
        logger.warning("Jedi Script 初始化失败，全部回退语法名匹配", exc_info=True)
        script = None

    relations: list[CodeRelation] = []
    resolved_call_keys: set[tuple[str, str, int]] = set()  # (caller_id, callee_name, line) 已解析

    # infer 结果缓存 (v1.3.3): 同一 (line, col) 只 infer 一次 — 循环/重复调用点常见,
    # 命中直接复用; 超过上限的调用跳过 Jedi 直接走语法名回退。
    infer_cache: dict[tuple[int, int], Optional[str]] = {}
    infer_budget = MAX_JEDI_INFER_CALLS

    for rc in raw_calls:
        caller_id = rc["caller_entity_id"]
        callee_name = rc["callee_name"]
        line = rc.get("line")
        col = rc.get("col", 0)
        # BUG B10: ast col_offset/end_col_offset 是 UTF-8 字节偏移, Jedi infer 的 column
        # 期望字符偏移。中文注释/字符串会让字节偏移 > 字符偏移 → Jedi 定位错位 → infer 失败
        # → 回退语法名匹配 (resolved=False)。转成字符偏移。
        col = _byte_col_to_char_col(source_lines, line, col)

        # 阶段1: Jedi 语义解析 (带缓存与调用数上限)
        target_id = None
        if infer_budget > 0:
            cache_key = (line, col)
            if cache_key in infer_cache:
                target_id = infer_cache[cache_key]
            else:
                infer_budget -= 1
                target_id = _resolve_with_jedi(script, line, col, entity_by_qname, entity_by_simple)
                infer_cache[cache_key] = target_id
        resolved = target_id is not None  # Jedi 成功解析

        # 阶段2: Jedi 不可用或未解析到 → 回退语法名匹配 (resolved=False)
        if target_id is None:
            target_id = _match_by_name(callee_name, entity_by_qname, entity_by_simple)

        if target_id is not None and target_id != caller_id:
            relations.append(CodeRelation(
                source=caller_id,
                target=target_id,
                type="CALLS",
                line=line,
                resolved=resolved,
            ))
            resolved_call_keys.add((caller_id, callee_name, line))

    # 从调用方 external_calls 移除已解析为 CALLS 的项
    for caller_id, callee_name, line in resolved_call_keys:
        caller = entity_by_id.get(caller_id)
        if caller is None:
            continue
        caller.external_calls = [
            ec for ec in caller.external_calls
            if not (ec.get("name") == callee_name and ec.get("line") == line)
        ]

    return relations


def _resolve_with_jedi(
    script: Optional[jedi.Script],
    line: Optional[int],
    col: Optional[int],
    entity_by_qname: dict[str, str],
    entity_by_simple: dict[str, list[str]],
) -> Optional[str]:
    """用 Jedi infer 解析调用目标，返回项目内 entity_id 或 None。"""
    if script is None or line is None:
        return None
    try:
        names = script.infer(line=line, column=col or 0)
    except Exception:
        return None

    for name in names:
        # name.full_name 形如 "main.SimpleCrawler.fetch_page" 或 "SimpleCrawler.fetch_page"
        full = getattr(name, "full_name", None) or getattr(name, "name", None)
        if not full:
            continue
        # 尝试多种匹配: 全路径后缀匹配 qualified_name
        target_id = _match_jedi_name(full, entity_by_qname, entity_by_simple)
        if target_id:
            return target_id
    return None


def _byte_col_to_char_col(source_lines: list[str], line: Optional[int], byte_col: int) -> int:
    """把 AST 字节列偏移转成 Jedi 期望的字符列偏移 (BUG B10)。

    Python AST 的 col_offset/end_col_offset 是 UTF-8 字节偏移; Jedi infer(line, column)
    的 column 是字符偏移。纯 ASCII 两者相等; 行内有中文 (注释/字符串/标识符) 时字节偏移
    > 字符偏移, 不转换则 Jedi 定位错位 → infer 失败。
    取该行源码, 按字节切片解码得字符数。越界/无源码时原样返回 (best-effort, 不影响主流程)。
    """
    if not byte_col or not line or not source_lines:
        return byte_col or 0
    try:
        line_str = source_lines[line - 1]  # AST lineno 从 1 开始
    except IndexError:
        return byte_col or 0
    # 该行前 byte_col 字节解码为字符, 字符数即字符列偏移
    try:
        char_prefix = line_str.encode("utf-8")[:byte_col].decode("utf-8", errors="ignore")
        return len(char_prefix)
    except Exception:
        return byte_col or 0


def _match_jedi_name(
    full: str,
    entity_by_qname: dict[str, str],
    entity_by_simple: dict[str, list[str]],
) -> Optional[str]:
    """将 Jedi full_name 匹配到项目内 entity_id。

    Jedi full_name 可能是 "module.Class.method" / "Class.method" / "method"。
    尝试: 1) 精确 qualified_name 2) 以 qualified_name 结尾 3) 简单名 (仅当唯一)
    """
    # 1. 精确
    if full in entity_by_qname:
        return entity_by_qname[full]

    # 2. 后缀匹配 qualified_name (main.SimpleCrawler.fetch_page → SimpleCrawler.fetch_page)
    for qname, eid in entity_by_qname.items():
        if full.endswith("." + qname) or full == qname:
            return eid

    # 3. 简单名 (取最后一段)，仅当唯一时
    simple = full.split(".")[-1]
    candidates = entity_by_simple.get(simple, [])
    if len(candidates) == 1:
        return candidates[0]

    return None


def _match_by_name(
    callee_name: str,
    entity_by_qname: dict[str, str],
    entity_by_simple: dict[str, list[str]],
) -> Optional[str]:
    """语法名回退匹配 (Jedi 不可用时)。

    callee_name 形如 "self.fetch_page" / "storage.get_all" / "urljoin" / "SimpleCrawler"。
    取最后一段作简单名，唯一时匹配。
    """
    # 取末段简单名
    simple = callee_name.split(".")[-1]
    candidates = entity_by_simple.get(simple, [])
    if len(candidates) == 1:
        return candidates[0]

    # 也有可能是 qualified_name 直接匹配 (如 "SimpleCrawler.fetch_page")
    if callee_name in entity_by_qname:
        return entity_by_qname[callee_name]

    return None
