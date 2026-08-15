"""项目图谱 LLM 深度分析单测 - mock LLM + search_web, 免真实 Neo4j/LLM/Tavily。

覆盖:
  - 正常分析: LLM 返回合法 JSON + 联网搜到资源
  - 图谱不存在 -> ValueError
  - LLM 未配置 -> ValueError
  - LLM 返回非 JSON -> 降级纯文本 summary
  - 无 Tavily key -> web_resources 为空但不报错
  - 路由层: POST /analyze 正常 / 404 / 503
"""

import json
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import project as project_api
from app.agents import project_analyzer


# ============================================================
# 测试数据
# ============================================================

_FAKE_GRAPH = {
    "project_id": "demo_proj",
    "nodes": [
        {"id": "e1", "label": "crawl", "group": "function",
         "properties": {"name": "crawl", "kind": "function",
                        "docstring": "主入口: 爬取页面",
                        "external_calls": ["requests.get", "bs4.BeautifulSoup"]}},
        {"id": "e2", "label": "parse_html", "group": "function",
         "properties": {"name": "parse_html", "kind": "function",
                        "external_calls": ["bs4.BeautifulSoup"]}},
    ],
    "edges": [
        {"source": "e1", "target": "e2", "label": "CALLS"},
    ],
}

_FAKE_LLM_JSON = json.dumps({
    "summary": "一个简单的网页爬虫项目",
    "architecture": {
        "pattern": "单体脚本",
        "entry_points": ["crawl"],
        "key_modules": ["crawl: 爬取入口", "parse_html: HTML 解析"],
    },
    "complexity": {"level": "低", "note": "仅两个函数"},
    "recommendations": ["学习 requests 库", "学习 BeautifulSoup 解析"],
}, ensure_ascii=False)


class _FakeKG:
    def __init__(self, graph=None):
        self._graph = graph

    def get_project_graph(self, project_id):
        return self._graph


class _FakeLLM:
    """模拟 ChatOpenAI.invoke 返回。"""
    def __init__(self, content):
        self._content = content

    def invoke(self, messages):
        class _Resp:
            content = self._content
        return _Resp()


# ============================================================
# 单元测试: analyze_project
# ============================================================

def test_analyze_project_success(monkeypatch):
    """正常分析: LLM 返回合法 JSON + 联网搜到资源。"""
    monkeypatch.setattr("app.agents.project_analyzer.llm_configured", lambda: True)
    monkeypatch.setattr("app.agents.project_analyzer.get_default_chat_model",
                        lambda: _FakeLLM(_FAKE_LLM_JSON))
    monkeypatch.setattr("app.agents.project_analyzer.search_web",
                        lambda q, k, max_results=2: [{"title": f"教程-{q}", "url": "https://example.com", "snippet": "示例"}])

    kg = _FakeKG(_FAKE_GRAPH)
    result = project_analyzer.analyze_project(kg, "demo_proj", tavily_key="fake_key")

    assert result["summary"] == "一个简单的网页爬虫项目"
    assert result["architecture"]["pattern"] == "单体脚本"
    assert result["architecture"]["entry_points"] == ["crawl"]
    assert len(result["recommendations"]) == 2
    # tech_stack 从 external_calls 提取
    assert "requests" in result["tech_stack"]
    assert "bs4" in result["tech_stack"]
    # 联网搜到资源
    assert len(result["web_resources"]) > 0
    assert result["web_resources"][0]["url"] == "https://example.com"


def test_analyze_project_graph_not_found():
    """图谱不存在 -> ValueError。"""
    kg = _FakeKG(None)
    with pytest.raises(ValueError, match="不存在"):
        project_analyzer.analyze_project(kg, "missing_proj")


def test_analyze_project_llm_not_configured(monkeypatch):
    """LLM 未配置 -> ValueError。"""
    monkeypatch.setattr("app.agents.project_analyzer.llm_configured", lambda: False)
    kg = _FakeKG(_FAKE_GRAPH)
    with pytest.raises(ValueError, match="LLM 未配置"):
        project_analyzer.analyze_project(kg, "demo_proj")


def test_analyze_project_llm_bad_json_degrades(monkeypatch):
    """LLM 返回非 JSON -> 降级纯文本 summary, 不抛异常。"""
    monkeypatch.setattr("app.agents.project_analyzer.llm_configured", lambda: True)
    monkeypatch.setattr("app.agents.project_analyzer.get_default_chat_model",
                        lambda: _FakeLLM("这不是 JSON, 只是一段文本描述"))
    monkeypatch.setattr("app.agents.project_analyzer.search_web",
                        lambda q, k, max_results=2: [])

    kg = _FakeKG(_FAKE_GRAPH)
    result = project_analyzer.analyze_project(kg, "demo_proj", tavily_key="fake_key")

    # 降级: summary 用原始文本
    assert "文本描述" in result["summary"]
    assert result["architecture"]["pattern"] == "未知"
    assert result["web_resources"] == []


def test_analyze_project_no_tavily_key(monkeypatch):
    """无 Tavily key -> web_resources 为空, 分析仍正常。"""
    monkeypatch.setattr("app.agents.project_analyzer.llm_configured", lambda: True)
    monkeypatch.setattr("app.agents.project_analyzer.get_default_chat_model",
                        lambda: _FakeLLM(_FAKE_LLM_JSON))
    monkeypatch.setattr("app.agents.project_analyzer.settings.TAVILY_API_KEY", "")

    kg = _FakeKG(_FAKE_GRAPH)
    result = project_analyzer.analyze_project(kg, "demo_proj", tavily_key=None)

    assert result["summary"] == "一个简单的网页爬虫项目"
    assert result["web_resources"] == []


def test_analyze_project_llm_markdown_wrapped_json(monkeypatch):
    """LLM 返回 ```json ... ``` 包裹的 JSON -> 能正确解析。"""
    wrapped = f"```json\n{_FAKE_LLM_JSON}\n```"
    monkeypatch.setattr("app.agents.project_analyzer.llm_configured", lambda: True)
    monkeypatch.setattr("app.agents.project_analyzer.get_default_chat_model",
                        lambda: _FakeLLM(wrapped))
    monkeypatch.setattr("app.agents.project_analyzer.search_web",
                        lambda q, k, max_results=2: [])

    kg = _FakeKG(_FAKE_GRAPH)
    result = project_analyzer.analyze_project(kg, "demo_proj", tavily_key="k")

    assert result["summary"] == "一个简单的网页爬虫项目"
    assert result["architecture"]["pattern"] == "单体脚本"


# ============================================================
# API 路由测试: POST /api/project/analyze
# ============================================================

def _build_app(kg=None):
    app = FastAPI()
    app.state.kg = kg
    app.include_router(project_api.router, prefix="/api/project")
    return app


def test_analyze_api_success(monkeypatch):
    monkeypatch.setattr("app.agents.project_analyzer.llm_configured", lambda: True)
    monkeypatch.setattr("app.agents.project_analyzer.get_default_chat_model",
                        lambda: _FakeLLM(_FAKE_LLM_JSON))
    monkeypatch.setattr("app.agents.project_analyzer.search_web",
                        lambda q, k, max_results=2: [])

    kg = _FakeKG(_FAKE_GRAPH)
    client = TestClient(_build_app(kg))
    resp = client.post("/api/project/analyze", json={"project_id": "demo_proj", "tavily_key": "k"})

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["summary"] == "一个简单的网页爬虫项目"
    assert "tech_stack" in data


def test_analyze_api_graph_not_found_404(monkeypatch):
    monkeypatch.setattr("app.agents.project_analyzer.llm_configured", lambda: True)
    kg = _FakeKG(None)
    client = TestClient(_build_app(kg))
    resp = client.post("/api/project/analyze", json={"project_id": "missing"})
    assert resp.status_code == 404


def test_analyze_api_llm_not_configured_503(monkeypatch):
    monkeypatch.setattr("app.agents.project_analyzer.llm_configured", lambda: False)
    kg = _FakeKG(_FAKE_GRAPH)
    client = TestClient(_build_app(kg))
    resp = client.post("/api/project/analyze", json={"project_id": "demo_proj"})
    assert resp.status_code == 503


def test_analyze_api_missing_project_id_422():
    client = TestClient(_build_app(_FakeKG(_FAKE_GRAPH)))
    resp = client.post("/api/project/analyze", json={})
    assert resp.status_code == 422


def test_analyze_api_kg_not_ready_503():
    """kg 未就绪 -> 503。"""
    client = TestClient(_build_app(kg=None))
    resp = client.post("/api/project/analyze", json={"project_id": "demo"})
    assert resp.status_code == 503
