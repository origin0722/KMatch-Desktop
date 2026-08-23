"""web_search 单测 — Tavily 联网搜索封装 + /api/search/web + /weak-topics 路由。

覆盖:
  - search_web: 无 key/空 query 静默降级, 成功解析 (snippet 400 截断, advanced depth), 异常不抛
  - search_weak_topics: 薄弱点 -> web_link 资源 (target_node_id 溯源, 最多 3 点 x 2 条)
  - /api/search/web: 无 key 503, 空 query 422, 正常 200
  - /api/search/weak-topics: 无 key 503, 空 topics 422, 正常批量 200
"""

from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from app.utils.web_search import search_web, search_weak_topics


# ============================================================
# search_web
# ============================================================

def test_search_web_no_key_returns_empty():
    """无 API key 时静默返回 [] (不抛异常)。"""
    assert search_web("python 循环", None) == []
    assert search_web("python 循环", "") == []


def test_search_web_empty_query_returns_empty():
    """空 query 返回 []。"""
    assert search_web("", "sk-test") == []


def test_search_web_success_parses_results(monkeypatch):
    """Tavily 返回解析为 {title, url, snippet}, snippet 截 400 字, 默认 advanced depth。"""
    class _FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"results": [
                {"title": "t1", "url": "https://a.com", "content": "x" * 500},
                {"title": "t2", "url": "https://b.com", "content": "short"},
                {"url": "", "content": "no-url 丢弃"},
            ]}

    class _FakeClient:
        def __init__(self, *a, **k):
            self._resp = _FakeResp()
            self._posted = {}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            self._posted = k.get("json", {})
            return self._resp

    monkeypatch.setattr("app.utils.web_search.httpx.Client", _FakeClient)
    fake = _FakeClient()
    monkeypatch.setattr("app.utils.web_search.httpx.Client", lambda *a, **k: fake)
    results = search_web("query", "sk-test", max_results=3)
    assert fake._posted["search_depth"] == "advanced"   # 默认 advanced (摘要更充实)
    assert len(results) == 2
    assert results[0]["title"] == "t1"
    assert results[0]["url"] == "https://a.com"
    assert len(results[0]["snippet"]) == 400  # 长内容截断
    assert results[1]["snippet"] == "short"


def test_search_web_exception_returns_empty(monkeypatch):
    """Tavily 调用抛异常时返回 [] 且不抛。"""
    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            raise RuntimeError("tavily down")

    monkeypatch.setattr("app.utils.web_search.httpx.Client", _FakeClient)
    assert search_web("query", "sk-test") == []


# ============================================================
# search_weak_topics
# ============================================================

def test_search_weak_topics_no_key_returns_empty():
    """无 key 直接返回 [], 不调搜索。"""
    assert search_weak_topics({"weak_topics": [{"node_id": "PY-001"}]}, None) == []
    assert search_weak_topics({"weak_topics": [{"node_id": "PY-001"}]}, "") == []


def test_search_weak_topics_no_weak_topics_returns_empty():
    """画像无薄弱点 (或非 dict) 且无 direction 返回 []。"""
    assert search_weak_topics({}, "sk-test") == []
    assert search_weak_topics({"weak_topics": []}, "sk-test") == []
    assert search_weak_topics(None, "sk-test") == []


def test_search_weak_topics_no_weak_topics_fallback_to_direction(monkeypatch):
    """无薄弱点时按 direction 兜底搜一轮 (保证反馈后联网资源 tab 不空, target_node_id 置空)。"""
    captured = []

    def _fake_search_web(query, key, max_results):
        captured.append((query, key, max_results))
        return [{"title": f"{query} #1", "url": "https://d.com", "snippet": "s"}]

    monkeypatch.setattr("app.utils.web_search.search_web", _fake_search_web)
    results = search_weak_topics({"weak_topics": []}, "sk-test", direction="Python 数据分析")
    assert len(results) == 1
    assert captured[0][0] == "Python 数据分析 学习路线 入门 教程"
    assert captured[0][2] == 4
    assert results[0]["content_type"] == "web_link"
    assert results[0]["target_node_id"] is None


def test_search_weak_topics_no_weak_no_direction_still_empty():
    """无薄弱点且无 direction -> 仍返回 [] (不硬造无意义搜索)。"""
    assert search_weak_topics({}, "sk-test", direction=None) == []


def test_search_weak_topics_produces_web_links(monkeypatch):
    """薄弱点 -> web_link 资源: 最多 3 点 x 2 条, 带 target_node_id 溯源。

    direction 拼进搜索词锚定领域 (此前硬编码 Python 前缀, 学其他领域全偏)。"""
    captured = []

    def _fake_search_web(query, key, max_results):
        captured.append((query, key, max_results))
        return [{"title": f"{query} #1", "url": f"https://e.com/{len(captured)}", "snippet": "s"}]

    monkeypatch.setattr("app.utils.web_search.search_web", _fake_search_web)
    profile = {"weak_topics": [
        {"node_id": "PY-001", "mastery": 0.3},
        {"node_id": "PY-010", "mastery": 0.4},
        {"node_id": "PY-020", "mastery": 0.5},
        {"node_id": "PY-030", "mastery": 0.6},  # 第 4 个薄弱点不搜 (最多 3 个)
    ]}
    nodes = [{"node_id": "PY-001", "name": "变量"}, {"node_id": "PY-010", "name": "列表"}]
    results = search_weak_topics(profile, "sk-test", nodes=nodes, direction="Python 入门")
    assert len(results) == 3  # 3 点 x 每点 1 条 (mock 返回 1 条)
    assert len(captured) == 3
    # 搜索词 = 方向前缀 + 节点可读名
    assert captured[0][0] == "Python 入门 变量 教程 讲解 示例"
    assert captured[0][2] == 2
    # 资源带溯源
    assert all(r["content_type"] == "web_link" for r in results)
    assert {r["target_node_id"] for r in results} == {"PY-001", "PY-010", "PY-020"}
    # 无节点可读名的退回 node_id 作搜索词
    assert captured[2][0] == "Python 入门 PY-020 教程 讲解 示例"

    # 无 direction 时不再硬编码 Python 前缀
    captured.clear()
    search_weak_topics(profile, "sk-test", nodes=nodes)
    assert captured[0][0] == "变量 教程 讲解 示例"


def test_search_weak_topics_fallback_to_node_id(monkeypatch):
    """节点不在 node_map 时退回 node_id 作搜索词。"""
    monkeypatch.setattr("app.utils.web_search.search_web",
                        lambda q, k, max_results: [{"title": q, "url": "https://x.com", "snippet": "s"}])
    results = search_weak_topics({"weak_topics": [{"node_id": "PY-999"}]}, "sk-test")
    assert len(results) == 1  # mock 每点返回 1 条
    assert results[0]["target_node_id"] == "PY-999"
    assert results[0]["url"] == "https://x.com"


# ============================================================
# /api/search/web 路由
# ============================================================

def _client_with(monkeypatch, settings_key, search_hits):
    import app.api.search as search_api
    from app.main import app
    monkeypatch.setattr(search_api.settings, "TAVILY_API_KEY", settings_key)
    monkeypatch.setattr(search_api, "search_web",
                        lambda q, k, max_results: search_hits)
    return TestClient(app)


def test_search_web_api_no_key_503(monkeypatch):
    """前端与 .env 均无 key -> 503 带指引。"""
    client = _client_with(monkeypatch, "", [])
    r = client.post("/api/search/web", json={"query": "python"})
    assert r.status_code == 503
    assert "Tavily" in r.json()["detail"]


def test_search_web_api_empty_query_422(monkeypatch):
    """query 必填, 空串 -> 422。"""
    client = _client_with(monkeypatch, "sk-env", [])
    r = client.post("/api/search/web", json={"query": "  "})
    assert r.status_code == 422


def test_search_web_api_ok(monkeypatch):
    """有 key (前端传入优先于 .env) -> 200 返回 results。"""
    seen = {}

    def _fake_search(q, k, max_results):
        seen["key"] = k
        return [{"title": "t", "url": "https://e.com", "snippet": "s"}]

    import app.api.search as search_api
    from app.main import app
    monkeypatch.setattr(search_api.settings, "TAVILY_API_KEY", "sk-env")
    monkeypatch.setattr(search_api, "search_web", _fake_search)
    client = TestClient(app)
    r = client.post("/api/search/web",
                    json={"query": "python 循环", "tavily_key": "sk-ui", "max_results": 5})
    assert r.status_code == 200
    assert seen["key"] == "sk-ui"  # 前端传入 key 优先
    body = r.json()
    assert body["query"] == "python 循环"
    assert body["results"][0]["snippet"] == "s"


def test_search_web_api_max_results_bounds(monkeypatch):
    """max_results 越界 -> 422 (pydantic 约束 1-8)。"""
    client = _client_with(monkeypatch, "sk-env", [])
    r = client.post("/api/search/web", json={"query": "q", "max_results": 99})
    assert r.status_code == 422


# ============================================================
# /api/search/weak-topics 路由 (资源页一键丰富)
# ============================================================

def test_weak_topics_api_no_key_503(monkeypatch):
    """无 key -> 503 带指引。"""
    client = _client_with(monkeypatch, "", [])
    r = client.post("/api/search/weak-topics",
                    json={"topics": [{"node_id": "PY-001", "name": "变量"}], "max_per_topic": 3})
    assert r.status_code == 503
    assert "Tavily" in r.json()["detail"]


def test_weak_topics_api_empty_topics_422(monkeypatch):
    """topics 空 / 无 node_id -> 422。"""
    client = _client_with(monkeypatch, "sk-env", [])
    assert client.post("/api/search/weak-topics", json={"topics": []}).status_code == 422
    assert client.post("/api/search/weak-topics",
                       json={"topics": [{"name": "无 id"}]}).status_code == 422


def test_weak_topics_api_ok(monkeypatch):
    """正常批量: 每点搜索结果带 target_node_id, direction 拼进搜索词。"""
    seen = {}

    def _fake_search(q, k, max_results):
        seen["query"] = q
        seen["max"] = max_results
        return [{"title": q, "url": "https://e.com", "snippet": "s"}]

    import app.api.search as search_api
    from app.main import app
    monkeypatch.setattr(search_api.settings, "TAVILY_API_KEY", "sk-env")
    monkeypatch.setattr(search_api, "search_web", _fake_search)
    client = TestClient(app)
    r = client.post("/api/search/weak-topics", json={
        "topics": [{"node_id": "PY-001", "name": "变量"}],
        "max_per_topic": 3,
        "direction": "Python",
    })
    assert r.status_code == 200
    assert seen["query"] == "Python 变量 教程 讲解 示例"
    assert seen["max"] == 3
    body = r.json()
    assert body["topics"] == 1
    assert body["results"][0]["target_node_id"] == "PY-001"
    assert body["results"][0]["content_type"] == "web_link"


def test_weak_topics_api_max_per_topic_bounds(monkeypatch):
    """max_per_topic 越界 -> 422 (约束 1-5)。"""
    client = _client_with(monkeypatch, "sk-env", [])
    r = client.post("/api/search/weak-topics",
                    json={"topics": [{"node_id": "PY-001", "name": "x"}], "max_per_topic": 9})
    assert r.status_code == 422


def test_verify_api_no_key_503(monkeypatch):
    """Tavily 测试连接: 无 key -> 503 带指引。"""
    client = _client_with(monkeypatch, "", [])
    r = client.post("/api/search/verify", json={})
    assert r.status_code == 503
    assert "Tavily" in r.json()["detail"]
