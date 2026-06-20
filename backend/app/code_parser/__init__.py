"""
KMatch 代码解析模块

Python AST + Jedi 语义解析，提取项目代码结构 (模块/类/函数/方法/调用/继承)，
构建项目框架层 (第2层) + 代码实体层 (第3层) 图谱。

公共 API:
  - 数据模型: CodeEntity, CodeRelation, ParsedProject, EntityType
  - 解析: parse_module_source (单模块 AST), parse_project (多模块编排)
  - 加载: load_example_project, load_text_source, list_example_projects

下批 (code_tester) 将复用 parse_module_source 做 AST 安全检查、据 CodeEntity 签名生成 Pytest。
"""

from app.code_parser.ast_parser import parse_module_source
from app.code_parser.loader import (
    list_example_projects,
    load_example_project,
    load_text_source,
    parse_project,
)
from app.code_parser.models import (
    CodeEntity,
    CodeRelation,
    EntityType,
    ParsedProject,
)

__all__ = [
    "CodeEntity",
    "CodeRelation",
    "EntityType",
    "ParsedProject",
    "parse_module_source",
    "parse_project",
    "load_example_project",
    "load_text_source",
    "list_example_projects",
]
