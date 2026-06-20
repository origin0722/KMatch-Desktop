"""
代码解析数据模型

定义项目代码 AST 解析产出的实体、关系与聚合结构。纯 dataclass，便于单元测试断言字段。

对齐 Neo4j 四层图谱:
  - 第2层 项目框架层: Module / Class 实体 (layer=2)
  - 第3层 代码实体层: Function / Method 实体 (layer=3)

命名空间隔离: 项目实体统一打 :ProjectEntity 基标签，绝不与领域元知识 :KnowledgeNode (PY-xxx) 混淆。
entity_id 形如 PROJ-{project_id}-{TYPE}-{qualified_name}，项目内唯一、跨项目不撞。
"""

from dataclasses import dataclass, field
from typing import Literal, Optional


# 实体类型
EntityType = Literal["module", "class", "function", "method"]

# 关系类型
RelationType = Literal["CONTAINS", "CALLS", "INHERITS"]

# 图谱层: 2=项目框架(Module/Class), 3=代码实体(Function/Method)
LAYER_FRAMEWORK = 2
LAYER_ENTITY = 3


@dataclass
class CodeEntity:
    """代码实体: 模块 / 类 / 函数 / 方法。

    所有实体落 Neo4j 时统一打 :ProjectEntity 基标签 + kind 对应的子标签
    (Module/Class/Function)。方法用 :Function + is_method=True 区分。
    """

    entity_id: str                       # PROJ-{pid}-{TYPE}-{qualified_name}
    project_id: str
    kind: EntityType                     # module|class|function|method
    name: str                            # 简单名 (如 fetch_page)
    qualified_name: str                  # 点分路径 (如 SimpleCrawler.fetch_page)
    module_name: str                     # 所属模块文件名 (stem, 如 main)
    layer: int                           # 2=框架层, 3=实体层
    line_start: int
    line_end: int

    docstring: Optional[str] = None
    # 参数列表: [{name, annotation, default, kind(positional|vararg|kwonly|...)}]
    params: list[dict] = field(default_factory=list)
    return_type: Optional[str] = None    # 返回类型注解 (ast.unparse)
    bases: list[str] = field(default_factory=list)            # 类基类名 (ast.unparse)
    decorators: list[str] = field(default_factory=list)       # 装饰器 (ast.unparse)
    source_code: Optional[str] = None    # ast.get_source_segment (前端点击查看源码/code_tester 用)
    is_method: bool = False              # kind=function 且属于某类 → True
    parent_class_id: Optional[str] = None  # 方法所属类的 entity_id
    # 未解析到项目内实体的外部调用: [{name, line}]，不建 CALLS 边，信息不丢失
    external_calls: list[dict] = field(default_factory=list)
    # --- 下一批 (code_tester) 写入的风险标注字段 (本批查询时读取返回前端) ---
    risk_level: Optional[str] = None     # high|medium|low|None
    risk_reason: Optional[str] = None

    def to_neo4j_props(self) -> dict:
        """转 Neo4j 节点属性 dict (剔除 None/内部辅助字段)。"""
        props = {
            "entity_id": self.entity_id,
            "project_id": self.project_id,
            "kind": self.kind,
            "name": self.name,
            "qualified_name": self.qualified_name,
            "module_name": self.module_name,
            "layer": self.layer,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "docstring": self.docstring,
            "params": self.params,
            "return_type": self.return_type,
            "bases": self.bases,
            "decorators": self.decorators,
            "source_code": self.source_code,
            "is_method": self.is_method,
            "parent_class_id": self.parent_class_id,
            "external_calls": self.external_calls,
            "risk_level": self.risk_level,
            "risk_reason": self.risk_reason,
        }
        return props


@dataclass
class CodeRelation:
    """代码实体间关系。"""

    source: str            # 调用方/容器 entity_id
    target: str            # 被调用方/被包含 entity_id
    type: RelationType     # CONTAINS|CALLS|INHERITS
    line: Optional[int] = None
    resolved: bool = True  # CALLS: Jedi 是否解析成功 (False=语法名匹配兜底)


@dataclass
class ParsedProject:
    """单次项目解析的聚合产出。"""

    project_id: str
    modules: list[str]                    # module_name 列表
    entities: list[CodeEntity]
    relations: list[CodeRelation]
    parsed_at: str                        # ISO8601 + Z
