"""
项目图谱 LLM 深度分析 Agent

从 Neo4j 取已落库的项目图谱 -> LLM 分析架构模式/入口点/关键模块/复杂度/学习建议
-> 对检测到的技术栈逐个 search_web 搜教程文档。

纯按需触发 (前端"深度分析"按钮), 不影响 AST 自动解析速度。
复用 app/agents/llm.py 的 LLM 基础设施 + app/utils/web_search.py 的 search_web。
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from langchain_core.messages import HumanMessage

from app.agents.llm import get_default_chat_model, llm_configured
from app.config import settings
from app.utils.json_utils import parse_llm_json
from app.utils.logging import get_logger
from app.utils.web_search import search_web

logger = get_logger(__name__)

# 输入控量: 实体摘要上限 (超出的截断标注, 控 LLM token 预算)
MAX_ENTITIES_IN_SUMMARY = 60
# 关系摘要只取 CALLS (最有信息量), 上限同理
MAX_CALLS_IN_SUMMARY = 30
# 联网搜索: 技术栈逐个搜, 每项 max_results 条; 上限控延迟 (并行后 wall-clock ≈ 单项)
MAX_TECHS_TO_SEARCH = 8
WEB_RESULTS_PER_TECH = 2

ANALYSIS_PROMPT = """你是一位资深 Python 架构师。请分析以下项目代码图谱, 输出结构化分析结果。

## 项目实体清单
{entity_summary}

## 检测到的技术栈
{tech_stack}

## 要求
请分析这个项目的架构, 输出严格 JSON (不要 markdown 代码块包裹), 格式如下:
{{
  "summary": "一段 2-3 句话的项目概要描述",
  "architecture": {{
    "pattern": "架构模式 (如 MVC / 分层 / 微服务 / 单体脚本 等)",
    "entry_points": ["主要入口点函数/模块名"],
    "key_modules": ["关键模块/类名及其职责简述"]
  }},
  "complexity": {{
    "level": "低/中/高",
    "note": "复杂度评估依据"
  }},
  "recommendations": [
    "针对该项目的学习建议 1",
    "针对该项目的学习建议 2",
    "针对该项目的学习建议 3"
  ]
}}

分析要点:
- 从实体名和调用关系推断项目用途和架构
- 入口点通常是被调用最多但不调用别人的函数 (或 main/__init__)
- 关键模块是连接枢纽 (高入度+高出度)
- 学习建议要具体到本项目的技术栈和架构特点"""


class ProjectGraphNotFoundError(Exception):
    """项目图谱不存在 (未解析或已删除) — API 层映射 404。"""


def _build_entity_summary(graph: dict) -> str:
    """把项目图谱实体 + 关系摘要成 LLM 可读的文本 (控制在 token 预算内)。"""
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    # 实体摘要: name (kind) [调用 N 个 / 被 N 个调用]
    out_deg = {}
    in_deg = {}
    for e in edges:
        out_deg[e.get("source")] = out_deg.get(e.get("source"), 0) + 1
        in_deg[e.get("target")] = in_deg.get(e.get("target"), 0) + 1

    lines = []
    for n in nodes[:MAX_ENTITIES_IN_SUMMARY]:
        props = n.get("properties") or {}
        nid = n.get("id", "")
        name = props.get("name") or n.get("label", "")
        kind = props.get("kind") or n.get("group", "")
        doc = (props.get("docstring") or "").strip()
        doc_short = doc[:80] + "…" if len(doc) > 80 else doc
        ext = props.get("external_calls") or []
        ext_str = f", deps={ext[:5]}" if ext else ""
        calls = out_deg.get(nid, 0)
        called = in_deg.get(nid, 0)
        line = f"- {name} ({kind}) [调用 {calls}, 被调 {called}{ext_str}]"
        if doc_short:
            line += f"  # {doc_short}"
        lines.append(line)

    if len(nodes) > MAX_ENTITIES_IN_SUMMARY:
        lines.append(f"... (共 {len(nodes)} 个实体, 已省略 {len(nodes) - MAX_ENTITIES_IN_SUMMARY})")

    # 关系摘要: 只列 CALLS (最有信息量)
    calls = [e for e in edges if e.get("label") == "CALLS"][:MAX_CALLS_IN_SUMMARY]
    if calls:
        lines.append("\n调用关系:")
        for e in calls:
            lines.append(f"  {e.get('source')} -> {e.get('target')}")

    return "\n".join(lines)


def _extract_tech_stack(graph: dict) -> list[str]:
    """从图谱实体的 external_calls 提取去重 top-level 模块名。"""
    nodes = graph.get("nodes", [])
    mods = set()
    for n in nodes:
        props = n.get("properties") or {}
        for c in (props.get("external_calls") or []):
            name = c if isinstance(c, str) else (c.get("name") if isinstance(c, dict) else None)
            if name and isinstance(name, str):
                top = name.split(".")[0].strip()
                if top:
                    mods.add(top)
    return sorted(mods)


def _search_tech_resources(tech_stack: list[str], tavily_key: str) -> list[dict]:
    """对技术栈逐个联网搜学习资源 (并行, wall-clock ≈ 单项搜索)。"""
    techs = tech_stack[:MAX_TECHS_TO_SEARCH]
    if not techs:
        return []

    def _one(tech: str) -> list[dict]:
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("snippet", ""),
                "tech": tech,
            }
            for r in search_web(f"{tech} Python 教程 入门 文档", tavily_key,
                                max_results=WEB_RESULTS_PER_TECH)
        ]

    with ThreadPoolExecutor(max_workers=max(1, len(techs))) as pool:
        nested = list(pool.map(_one, techs))
    resources = [r for chunk in nested for r in chunk]
    logger.info("项目深度分析: 搜到 %d 条技术栈学习资源 (技术 %d)", len(resources), len(techs))
    return resources


def analyze_project(kg, project_id: str, tavily_key: Optional[str] = None) -> dict:
    """LLM 深度分析项目图谱 + 联网搜技术栈学习资源。

    Args:
        kg: KnowledgeGraph 引擎实例
        project_id: 项目 ID
        tavily_key: Tavily API Key (None 时用 settings.TAVILY_API_KEY)

    Returns:
        {
            summary, architecture, complexity, recommendations,
            tech_stack: [str],
            web_resources: [{title, url, snippet, tech}]
        }

    Raises:
        ProjectGraphNotFoundError: 项目图谱不存在
        ValueError: LLM 未配置
    """
    graph = kg.get_project_graph(project_id)
    if graph is None:
        raise ProjectGraphNotFoundError(f"项目图谱不存在: {project_id}")

    if not llm_configured():
        raise ValueError("LLM 未配置 (LLM_API_KEY 为占位符), 无法执行深度分析")

    tavily_key = tavily_key or settings.TAVILY_API_KEY

    # 1. 构建 LLM 输入
    entity_summary = _build_entity_summary(graph)
    tech_stack = _extract_tech_stack(graph)
    tech_str = ", ".join(tech_stack) if tech_stack else "未检测到明显外部依赖"

    prompt = ANALYSIS_PROMPT.format(
        entity_summary=entity_summary,
        tech_stack=tech_str,
    )

    # 2. LLM 分析
    llm = get_default_chat_model()
    resp = llm.invoke([HumanMessage(content=prompt)])
    raw = resp.content if hasattr(resp, "content") else str(resp)

    # 3. 解析 LLM JSON 输出 (parse_llm_json 容错 markdown 包裹/尾随文本, 与其他 Agent 一致;
    #    失败返回 {} → 一并降级为纯文本 summary)
    analysis = parse_llm_json(raw)
    if not isinstance(analysis, dict) or not analysis:
        logger.warning("LLM 分析结果 JSON 解析失败, 降级为纯文本 summary")
        analysis = {
            "summary": str(raw)[:500],
            "architecture": {"pattern": "未知", "entry_points": [], "key_modules": []},
            "complexity": {"level": "未知", "note": "LLM 输出格式异常"},
            "recommendations": [],
        }

    # 4. 联网搜索技术栈学习资源 (并行)
    web_resources = _search_tech_resources(tech_stack, tavily_key) if tavily_key else []

    return {
        "summary": analysis.get("summary", ""),
        "architecture": analysis.get("architecture", {}),
        "complexity": analysis.get("complexity", {}),
        "recommendations": analysis.get("recommendations", []),
        "tech_stack": tech_stack,
        "web_resources": web_resources,
    }
