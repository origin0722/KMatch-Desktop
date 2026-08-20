"""路径穿越 / 输入校验 安全回归 (2026-08-19 三轴深度检查)。

覆盖: 嵌入式 project_id 白名单 / API parse 请求体 pattern / GET graph 路径参数校验 /
      load_example_project 多段路径拒绝。
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import project as project_api
from app.code_parser.loader import load_example_project
from app.graph.embedded import EmbeddedGraphStore


def _app():
    a = FastAPI()
    a.include_router(project_api.router, prefix="/api/project")

    class _KG:  # 仅需非 None (parse 的 write 分支; 本测试不发真实写入)
        pass

    a.state.kg = _KG()
    return a


def test_parse_rejects_traversal_project_id():
    """POST /parse 的 project_id 含路径分隔符 → Pydantic pattern 422 (不落盘)。"""
    c = TestClient(_app())
    r = c.post("/api/project/parse", json={
        "source_type": "text", "code": "x = 1", "project_id": "a/../../evil",
    })
    assert r.status_code == 422


def test_get_graph_rejects_invalid_project_id():
    """GET /graph/{id} 路径参数校验:
    - 编码斜杠 %2F 路由层解码后含 '/' → 不匹配单段路由 → 404 (到不了 handler, 天然安全)
    - 反斜杠 %5C 命中路由 → handler 显式 400
    """
    c = TestClient(_app())
    assert c.get("/api/project/graph/a%2F..%2Fevil").status_code == 404
    assert c.get("/api/project/graph/..%5C..%5Cevil").status_code == 400


@pytest.mark.parametrize("name", ["../README.md", "..\\..\\Windows", "/etc/passwd", "a/b"])
def test_load_example_rejects_multi_segment(name):
    """示例项目名多段/绝对路径 → FileNotFoundError (防读任意目录 .py)。"""
    with pytest.raises(FileNotFoundError):
        load_example_project(name)


def test_embedded_project_path_rejects_traversal(tmp_path):
    """嵌入式项目图落盘路径白名单 — 防写入任意路径。"""
    s = EmbeddedGraphStore(kb_dir=tmp_path, local_dir=tmp_path / "local")
    with pytest.raises(ValueError):
        s.write_project_graph("../../evil", [], [])
    with pytest.raises(ValueError):
        s.get_project_graph("../x")