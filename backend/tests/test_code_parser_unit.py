"""code_parser AST 解析纯函数单测 — 用 simple_crawler 真实源码做 fixture，免 Neo4j。

覆盖:
  - parse_module_source: 实体提取 (Module/Class/Function/Method)
  - 参数注解/默认值/返回类型/docstring/装饰器提取
  - CONTAINS 关系 (Module→Class/Function, Class→Method)
  - INHERITS 关系 (单独 fixture)
  - 语法级调用收集到 external_calls (CALLS 由 jedi_resolver 测试覆盖)
  - attach_source_code 回填
  - SyntaxError
"""

import pytest

from app.code_parser.ast_parser import (
    attach_source_code,
    make_entity_id,
    parse_module_source,
)
from app.code_parser.loader import load_example_project


@pytest.fixture(scope="module")
def crawler_source():
    """simple_crawler/main.py 真实源码。"""
    return load_example_project("simple_crawler")["main"]


@pytest.fixture(scope="module")
def crawler_parsed(crawler_source):
    """simple_crawler 解析结果 (entities, relations)。"""
    return parse_module_source(crawler_source, "main", "simple_crawler")


@pytest.fixture(scope="module")
def crawler_entities(crawler_parsed):
    return crawler_parsed[0]


@pytest.fixture(scope="module")
def crawler_relations(crawler_parsed):
    return crawler_parsed[1]


# ============================================================
# 实体提取
# ============================================================

def test_module_entity_present(crawler_entities):
    """含 1 个 Module 实体 main。"""
    modules = [e for e in crawler_entities if e.kind == "module"]
    assert len(modules) == 1
    assert modules[0].name == "main"
    assert modules[0].layer == 2
    assert modules[0].entity_id == "PROJ-simple_crawler-MODULE-main"


def test_class_entity_present(crawler_entities):
    """含 SimpleCrawler 类。"""
    classes = [e for e in crawler_entities if e.kind == "class"]
    assert len(classes) == 1
    cls = classes[0]
    assert cls.name == "SimpleCrawler"
    assert cls.layer == 2
    assert cls.qualified_name == "SimpleCrawler"
    assert cls.docstring == "简易网页爬虫 — 爬取页面标题和所有链接"


def test_methods_extracted(crawler_entities):
    """SimpleCrawler 含 5 个方法。"""
    methods = [e for e in crawler_entities if e.kind == "method"]
    method_names = sorted(m.name for m in methods)
    assert method_names == ["__init__", "crawl", "crawl_sitemap", "fetch_page", "parse_page"]
    for m in methods:
        assert m.layer == 3
        assert m.is_method is True
        assert m.parent_class_id == "PROJ-simple_crawler-CLASS-SimpleCrawler"
        assert m.qualified_name.startswith("SimpleCrawler.")


def test_module_level_function_extracted(crawler_entities):
    """模块级 main 函数 (非方法)。"""
    funcs = [e for e in crawler_entities if e.kind == "function"]
    assert len(funcs) == 1
    assert funcs[0].name == "main"
    assert funcs[0].is_method is False
    assert funcs[0].parent_class_id is None
    assert funcs[0].layer == 2  # 顶层函数属框架层


# ============================================================
# 参数 / 返回类型 / docstring
# ============================================================

def test_params_with_annotation_and_default(crawler_entities):
    """__init__(self, timeout: int = 10, user_agent: Optional[str] = None)。"""
    init = next(e for e in crawler_entities if e.name == "__init__")
    params = init.params
    assert params[0]["name"] == "self"
    assert params[1]["name"] == "timeout"
    assert params[1]["annotation"] == "int"
    assert params[1]["default"] == "10"
    assert params[2]["name"] == "user_agent"
    assert params[2]["default"] == "None"


def test_return_type_annotation(crawler_entities):
    """fetch_page → Optional[str]。"""
    fetch = next(e for e in crawler_entities if e.name == "fetch_page")
    assert fetch.return_type == "Optional[str]"


def test_crawl_params(crawler_entities):
    """crawl(self, url, max_links=50)。"""
    crawl = next(e for e in crawler_entities if e.name == "crawl")
    names = [p["name"] for p in crawl.params]
    assert names == ["self", "url", "max_links"]
    assert crawl.params[2]["default"] == "50"
    assert crawl.return_type == "Optional[Dict]"


def test_docstring_extraction(crawler_entities):
    """方法 docstring 提取。"""
    fetch = next(e for e in crawler_entities if e.name == "fetch_page")
    assert fetch.docstring == "获取页面 HTML 内容"


# ============================================================
# CONTAINS 关系
# ============================================================

def test_contains_relations(crawler_relations):
    """Module→Class, Module→main, Class→5方法 = 7 条 CONTAINS。"""
    contains = [r for r in crawler_relations if r.type == "CONTAINS"]
    assert len(contains) == 7

    module_id = "PROJ-simple_crawler-MODULE-main"
    class_id = "PROJ-simple_crawler-CLASS-SimpleCrawler"

    # Module → Class
    assert any(r.source == module_id and r.target == class_id for r in contains)
    # Module → main
    assert any(r.source == module_id and r.target == "PROJ-simple_crawler-FUNCTION-main" for r in contains)
    # Class → 各方法
    method_targets = {r.target for r in contains if r.source == class_id}
    assert len(method_targets) == 5
    assert "PROJ-simple_crawler-METHOD-SimpleCrawler.fetch_page" in method_targets


# ============================================================
# INHERITS 关系 (单独 fixture)
# ============================================================

def test_inheritance_relation():
    """class B(A) → INHERITS 边。simple_crawler 无继承，单独造。"""
    source = """
class A:
    pass

class B(A):
    def method(self):
        return self
"""
    entities, relations = parse_module_source(source, "inh", "test_inh")
    classes = {e.name: e.entity_id for e in entities if e.kind == "class"}
    inherits = [r for r in relations if r.type == "INHERITS"]
    assert len(inherits) == 1
    assert inherits[0].source == classes["B"]
    assert inherits[0].target == classes["A"]


# ============================================================
# 语法级调用收集 (external_calls)
# ============================================================

def test_external_calls_collected(crawler_entities):
    """外部调用 (requests/urljoin/print 等) 进 external_calls，不建 CALLS 边。"""
    fetch = next(e for e in crawler_entities if e.name == "fetch_page")
    names = {ec["name"] for ec in fetch.external_calls}
    # self.session.get 是内部属性链调用 (语法级)，会进 external_calls
    assert any("session.get" in n for n in names)
    # print 是外部调用
    assert "print" in names


def test_internal_calls_collected_as_raw(crawler_entities):
    """self.fetch_page / self.crawl 等语法级调用也被收集 (待 jedi 精化为 CALLS)。"""
    crawl = next(e for e in crawler_entities if e.name == "crawl")
    names = {ec["name"] for ec in crawl.external_calls}
    assert "self.fetch_page" in names
    assert "self.parse_page" in names


# ============================================================
# source_code 回填
# ============================================================

def test_attach_source_code(crawler_source, crawler_entities):
    """函数/方法 source_code 回填，含 def 行。"""
    entities, _ = parse_module_source(crawler_source, "main", "simple_crawler")
    attach_source_code(entities, crawler_source)
    fetch = next(e for e in entities if e.name == "fetch_page")
    assert fetch.source_code is not None
    assert "def fetch_page" in fetch.source_code
    assert "return resp.text" in fetch.source_code


# ============================================================
# 装饰器 (todo_backend)
# ============================================================

def test_decorators_captured():
    """todo_backend: TodoItem @dataclass, 路由函数 @app.route。"""
    source = load_example_project("todo_backend")["main"]
    entities, _ = parse_module_source(source, "main", "todo_backend")

    todo_item = next(e for e in entities if e.name == "TodoItem")
    assert "dataclass" in todo_item.decorators[0]


# ============================================================
# 错误处理
# ============================================================

def test_syntax_error_raises():
    """非法源码抛 SyntaxError (API 层转 422)。"""
    with pytest.raises(SyntaxError):
        parse_module_source("def broken(:\n    pass", "bad", "test")


def test_make_entity_id_format():
    """entity_id 格式 PROJ-{pid}-{TYPE}-{qname}。"""
    assert make_entity_id("p1", "class", "Foo") == "PROJ-p1-CLASS-Foo"
    assert make_entity_id("p1", "method", "Foo.bar") == "PROJ-p1-METHOD-Foo.bar"


# ============================================================
# B11 回归: 多文件 entity_id 撞名去重
# ============================================================

from app.code_parser.loader import parse_project


def test_multi_module_collision_dedup():
    """两模块各有同名 main 函数 → entity_id 撞, 去重保留首个, 不产生重复。"""
    src_a = "def main():\n    return 1\n"
    src_b = "def main():\n    return 2\n"
    parsed = parse_project("p", {"mod_a": src_a, "mod_b": src_b})
    main_entities = [e for e in parsed.entities if e.name == "main"]
    # 撞名去重: 只保留 1 个 main (而非 2 个同 entity_id 重复)
    assert len(main_entities) == 1, f"撞名应去重, 实际 {len(main_entities)} 个 main"
    # entity_id 唯一
    eids = [e.entity_id for e in parsed.entities]
    assert len(eids) == len(set(eids)), "entity_id 不应重复"


def test_single_module_no_dedup():
    """单文件不触发去重 (正常场景)。"""
    src = "def main():\n    return 1\n"
    parsed = parse_project("p", {"main": src})
    assert len(parsed.entities) == 2  # module + main
