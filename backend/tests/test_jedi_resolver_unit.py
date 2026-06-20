"""jedi_resolver 语义调用解析单测 — 用真实 Jedi，免 Neo4j。

覆盖:
  - CALLS 关系产出: self.fetch_page / crawler.crawl 等解析到项目内实体
  - 外部调用 (requests/urljoin/print) 不建 CALLS 边，保留在 external_calls
  - Jedi 失败回退语法名匹配 (resolved=False) 仍产出 CALLS

注: 回退匹配 (_match_by_name) 用简单名，对 simple_crawler 内唯一名方法总能匹配，
    故即使 Jedi 在某调用点未解析到，CALLS 关系仍正确产出 (resolved=False)。
"""

import pytest

from app.code_parser import loader as loader_mod
from app.code_parser.loader import load_example_project, parse_project


@pytest.fixture(scope="module")
def crawler_parsed():
    """simple_crawler 端到端解析 (ast + jedi)。"""
    sources = load_example_project("simple_crawler")
    return parse_project("simple_crawler", sources)


def _calls(parsed):
    """提取 CALLS 关系 {(source_qname, target_qname): resolved}。"""
    eid_to_qname = {e.entity_id: e.qualified_name for e in parsed.entities}
    result = {}
    for r in parsed.relations:
        if r.type == "CALLS":
            src = eid_to_qname.get(r.source, r.source)
            tgt = eid_to_qname.get(r.target, r.target)
            result[(src, tgt)] = r.resolved
    return result


# ============================================================
# CALLS 关系产出
# ============================================================

def test_self_method_call_resolved(crawler_parsed):
    """crawl 内 self.fetch_page → SimpleCrawler.fetch_page。"""
    calls = _calls(crawler_parsed)
    assert ("SimpleCrawler.crawl", "SimpleCrawler.fetch_page") in calls
    assert ("SimpleCrawler.crawl", "SimpleCrawler.parse_page") in calls


def test_self_call_in_sitemap(crawler_parsed):
    """crawl_sitemap 内 self.crawl → SimpleCrawler.crawl。"""
    calls = _calls(crawler_parsed)
    assert ("SimpleCrawler.crawl_sitemap", "SimpleCrawler.crawl") in calls


def test_local_var_call_resolved(crawler_parsed):
    """main 内 crawler.crawl(url) → SimpleCrawler.crawl (局部变量，Jedi 价值场景)。"""
    calls = _calls(crawler_parsed)
    assert ("main", "SimpleCrawler.crawl") in calls
    assert ("main", "SimpleCrawler.crawl_sitemap") in calls


def test_constructor_call_resolved(crawler_parsed):
    """main 内 SimpleCrawler() → SimpleCrawler 类。"""
    calls = _calls(crawler_parsed)
    assert ("main", "SimpleCrawler") in calls


# ============================================================
# 外部调用不建边
# ============================================================

def test_external_calls_not_linked(crawler_parsed):
    """外部调用 (requests/urljoin/time.sleep/print) 不产 CALLS 边，保留在 external_calls。"""
    calls = _calls(crawler_parsed)
    # 所有 CALLS target 都应是项目内实体 (qualified_name 在实体集里)
    qnames = {e.qualified_name for e in crawler_parsed.entities}
    for (_src, tgt) in calls:
        assert tgt in qnames, f"CALLS 指向非项目实体: {tgt}"

    # 至少有一个实体保留了外部调用
    has_external = any(e.external_calls for e in crawler_parsed.entities)
    assert has_external, "应保留未解析的外部调用"

    # fetch_page 的 external_calls 含外部库调用 (print/raise_for_status 等)
    fetch = next(e for e in crawler_parsed.entities if e.name == "fetch_page")
    ext_names = {ec["name"] for ec in fetch.external_calls}
    assert "print" in ext_names  # print 是外部，不被解析为 CALLS


def test_internal_calls_removed_from_external(crawler_parsed):
    """被解析为 CALLS 的内部调用应从 external_calls 移除。"""
    crawl = next(e for e in crawler_parsed.entities if e.name == "crawl")
    ext_names = {ec["name"] for ec in crawl.external_calls}
    # self.fetch_page / self.parse_page 已解析为 CALLS，应从 external_calls 移除
    assert "self.fetch_page" not in ext_names
    assert "self.parse_page" not in ext_names


# ============================================================
# Jedi 失败回退
# ============================================================

def test_falls_back_on_jedi_failure(monkeypatch):
    """Jedi Script 初始化失败 → 全部回退语法名匹配，CALLS 仍产出 (resolved=False)。"""
    import jedi

    def _boom(*args, **kwargs):
        raise RuntimeError("jedi disabled for test")

    # 直接 patch jedi.Script 构造抛异常 (jedi_resolver 全局引用 jedi.Script)
    monkeypatch.setattr(jedi, "Script", _boom)

    sources = load_example_project("simple_crawler")
    parsed = parse_project("simple_crawler", sources)
    calls = _calls(parsed)

    # 回退匹配仍产出关键 CALLS
    assert ("SimpleCrawler.crawl", "SimpleCrawler.fetch_page") in calls
    assert ("main", "SimpleCrawler.crawl") in calls
    # 回退路径 resolved=False
    assert calls[("SimpleCrawler.crawl", "SimpleCrawler.fetch_page")] is False


# ============================================================
# B10 回归: 字节列偏移 → 字符列偏移 (中文行 Jedi 定位)
# ============================================================

from app.code_parser.jedi_resolver import _byte_col_to_char_col


def test_byte_col_to_char_col_chinese_line():
    """中文行: '中 = foo()' 中 '中'占3字节1字符, foo 的 f 字节偏移6 → 字符偏移4。"""
    lines = ["中 = foo()"]
    assert _byte_col_to_char_col(lines, 1, 6) == 4


def test_byte_col_to_char_col_ascii_unchanged():
    """纯 ASCII: 字节偏移 = 字符偏移。"""
    assert _byte_col_to_char_col(["x = foo()"], 1, 4) == 4


def test_byte_col_to_char_col_boundary():
    assert _byte_col_to_char_col(["中 = foo()"], None, 6) == 6  # line=None 原样
    assert _byte_col_to_char_col(["中 = foo()"], 1, 0) == 0     # col=0
    assert _byte_col_to_char_col([], 1, 6) == 6                 # 无源码原样
    assert _byte_col_to_char_col(["x"], 99, 6) == 6             # 行越界原样
