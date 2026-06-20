"""
Todo 后端项目的 Pytest 测试用例
用法: cd data/example_projects/todo_backend && pytest test_main.py -v
"""

import pytest
import json
from main import app, TodoItem, TodoStorage


@pytest.fixture
def client():
    """Flask 测试客户端"""
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def storage():
    """独立 TodoStorage 实例用于单元测试"""
    return TodoStorage()


class TestTodoItem:
    """TodoItem 数据模型测试"""

    def test_create_item(self):
        item = TodoItem(id=1, title="Test")
        assert item.id == 1
        assert item.title == "Test"
        assert item.completed is False

    def test_item_with_completed(self):
        item = TodoItem(id=2, title="Done", completed=True)
        assert item.completed is True


class TestTodoStorage:
    """TodoStorage 存储逻辑测试"""

    def test_create_and_get(self, storage):
        item = storage.create("第一个任务")
        assert item.id == 1
        assert storage.get_by_id(1) is not None

    def test_get_not_found(self, storage):
        assert storage.get_by_id(999) is None

    def test_update_title(self, storage):
        storage.create("原始标题")
        updated = storage.update(1, title="新标题")
        assert updated.title == "新标题"

    def test_update_not_found(self, storage):
        assert storage.update(999, title="X") is None

    def test_delete(self, storage):
        storage.create("待删除")
        assert storage.delete(1) is True
        assert storage.get_by_id(1) is None

    def test_delete_not_found(self, storage):
        assert storage.delete(999) is False


class TestAPI:
    """Flask REST API 集成测试"""

    def test_list_empty(self, client):
        resp = client.get("/todos")
        assert resp.status_code == 200
        assert json.loads(resp.data) == []

    def test_create_todo(self, client):
        resp = client.post("/todos", json={"title": "学习 Python"})
        assert resp.status_code == 201
        data = json.loads(resp.data)
        assert data["title"] == "学习 Python"
        assert data["completed"] is False

    def test_create_without_title(self, client):
        resp = client.post("/todos", json={})
        assert resp.status_code == 400

    def test_full_crud_flow(self, client):
        # Create
        resp = client.post("/todos", json={"title": "写测试"})
        assert resp.status_code == 201
        item_id = json.loads(resp.data)["id"]

        # Read
        resp = client.get(f"/todos/{item_id}")
        assert resp.status_code == 200

        # Update
        resp = client.put(f"/todos/{item_id}", json={"completed": True})
        assert resp.status_code == 200
        assert json.loads(resp.data)["completed"] is True

        # Delete
        resp = client.delete(f"/todos/{item_id}")
        assert resp.status_code == 200

        # Verify deleted
        resp = client.get(f"/todos/{item_id}")
        assert resp.status_code == 404
