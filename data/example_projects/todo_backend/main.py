"""
KMatch 示例项目 — Todo 后端 (Flask)
用于「有项目二次开发」场景的教学演示。
功能: 最简 REST API，支持待办事项的增删改查。
Python 3.10+, Flask 2.x
"""

from flask import Flask, request, jsonify
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime

app = Flask(__name__)


@dataclass
class TodoItem:
    """待办事项数据模型"""
    id: int
    title: str
    completed: bool = False
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


class TodoStorage:
    """内存存储（生产环境应替换为数据库）"""
    def __init__(self):
        self._items: List[TodoItem] = []
        self._next_id: int = 1

    def get_all(self) -> List[TodoItem]:
        return self._items

    def get_by_id(self, item_id: int) -> Optional[TodoItem]:
        for item in self._items:
            if item.id == item_id:
                return item
        return None

    def create(self, title: str) -> TodoItem:
        item = TodoItem(id=self._next_id, title=title)
        self._next_id += 1
        self._items.append(item)
        return item

    def update(self, item_id: int, title: Optional[str] = None,
               completed: Optional[bool] = None) -> Optional[TodoItem]:
        item = self.get_by_id(item_id)
        if item is None:
            return None
        if title is not None:
            item.title = title
        if completed is not None:
            item.completed = completed
        return item

    def delete(self, item_id: int) -> bool:
        item = self.get_by_id(item_id)
        if item is None:
            return False
        self._items.remove(item)
        return True


storage = TodoStorage()


# --- REST API 路由 ---

@app.route("/todos", methods=["GET"])
def list_todos():
    """获取所有待办事项"""
    items = storage.get_all()
    return jsonify([
        {"id": i.id, "title": i.title, "completed": i.completed, "created_at": i.created_at}
        for i in items
    ])


@app.route("/todos/<int:item_id>", methods=["GET"])
def get_todo(item_id: int):
    """获取单个待办事项"""
    item = storage.get_by_id(item_id)
    if item is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify({
        "id": item.id, "title": item.title,
        "completed": item.completed, "created_at": item.created_at
    })


@app.route("/todos", methods=["POST"])
def create_todo():
    """创建新的待办事项"""
    data = request.get_json()
    if not data or "title" not in data:
        return jsonify({"error": "title is required"}), 400
    item = storage.create(data["title"])
    return jsonify({
        "id": item.id, "title": item.title,
        "completed": item.completed, "created_at": item.created_at
    }), 201


@app.route("/todos/<int:item_id>", methods=["PUT"])
def update_todo(item_id: int):
    """更新待办事项"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "request body is required"}), 400
    item = storage.update(
        item_id,
        title=data.get("title"),
        completed=data.get("completed"),
    )
    if item is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify({
        "id": item.id, "title": item.title,
        "completed": item.completed, "created_at": item.created_at
    })


@app.route("/todos/<int:item_id>", methods=["DELETE"])
def delete_todo(item_id: int):
    """删除待办事项"""
    success = storage.delete(item_id)
    if not success:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"deleted": True})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
