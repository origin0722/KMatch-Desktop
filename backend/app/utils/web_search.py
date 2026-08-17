"""Tavily 联网搜索封装: 搜薄弱知识点相关网站, 返回 web_link 资源。

为学情反馈阶段补充实时联网资源: 对画像薄弱知识点调 Tavily 搜索相关教程/文档网站,
作为 generated_content.resources 的 web_link 类型返回, 每条可溯源至图谱节点 (target_node_id)。

无 API key 时静默降级 (返回空列表), 不影响主流程。
"""
import httpx

from app.utils.logging import get_logger

logger = get_logger(__name__)

TAVILY_URL = "https://api.tavily.com/search"


def search_web(query: str, api_key: str, max_results: int = 2,
               search_depth: str = "advanced") -> list[dict]:
    """调 Tavily 搜索, 返回 [{title, url, snippet}]。失败/无 key 返回 []。

    search_depth: basic=快但摘要短 / advanced=摘要更充实 (默认 advanced,
    让学习资源里的每条内容更有信息量)。
    """
    if not api_key or not query:
        return []
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.post(TAVILY_URL, json={
                "api_key": api_key,
                "query": query,
                "max_results": max_results,
                "search_depth": search_depth,
            })
            resp.raise_for_status()
            data = resp.json()
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": (r.get("content", "") or "")[:400],
                }
                for r in data.get("results", [])
                if r.get("url")
            ]
    except Exception as e:
        logger.warning("Tavily 搜索失败 query=%s: %s", query, e)
        return []


def search_weak_topics(profile: dict, api_key: str, nodes: list[dict] | None = None,
                       direction: str | None = None) -> list[dict]:
    """对画像薄弱知识点调 Tavily 搜索相关网站, 返回 web_link 资源列表。

    每条资源: {content_type: 'web_link', title, url, content(snippet), target_node_id}
    最多搜 3 个薄弱点, 每点 2 条结果。无 key/无薄弱点返回 []。
    direction: 学习目标方向, 拼进搜索词保证领域相关 (此前硬编码 "Python" 前缀,
    学 CSS/agent 等领域时搜索结果全偏)。

    兜底: 无薄弱点 (如全答对) 时, 若给了 direction, 按方向搜一轮"学习路线/教程/入门",
    保证"针对性反馈"后学习资源四 tab 都有内容 (联网资源 tab 不空)。
    """
    if not api_key:
        return []
    weak = profile.get("weak_topics", []) if isinstance(profile, dict) else []
    node_map = {n.get("node_id"): n for n in (nodes or []) if isinstance(n, dict)}

    # 兜底: 无薄弱点时按学习方向搜
    if not weak:
        if not direction:
            return []
        results = search_web(f"{direction} 学习路线 入门 教程", api_key, max_results=4)
        return [
            {
                "content_type": "web_link",
                "title": r["title"],
                "url": r["url"],
                "content": r["snippet"],
                "target_node_id": None,
            }
            for r in results
        ]

    resources = []
    for t in weak[:3]:
        if not isinstance(t, dict):
            continue
        node_id = t.get("node_id", "")
        node = node_map.get(node_id, {})
        # 搜索词用节点可读名 (name/title), 退回 node_id; 方向前缀锚定领域
        name = node.get("name") or node.get("title") or node_id
        query = f"{direction} {name} 教程 讲解 示例" if direction else f"{name} 教程 讲解 示例"
        results = search_web(query, api_key, max_results=2)
        for r in results:
            resources.append({
                "content_type": "web_link",
                "title": r["title"],
                "url": r["url"],
                "content": r["snippet"],
                "target_node_id": node_id,
            })
    logger.info("Tavily 联网搜索: %d 条 web_link 资源 (薄弱点 %d)", len(resources), len(weak[:3]))
    return resources
