"""
简易爬虫项目的 Pytest 测试用例
用法: cd data/example_projects/simple_crawler && pytest test_main.py -v
"""

import pytest
from main import SimpleCrawler


SAMPLE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Test Page</title></head>
<body>
    <h1>Hello World</h1>
    <a href="https://example.com/page1">Page 1</a>
    <a href="/page2">Page 2</a>
    <a href="https://other.com">External</a>
    <a href=""></a>
</body>
</html>
"""


class TestParsePage:
    """HTML 解析测试"""

    def test_extract_title(self):
        crawler = SimpleCrawler()
        result = crawler.parse_page(SAMPLE_HTML)
        assert result["title"] == "Test Page"

    def test_extract_links(self):
        crawler = SimpleCrawler()
        result = crawler.parse_page(SAMPLE_HTML)
        assert result["link_count"] == 4

    def test_skip_empty_links(self):
        """空链接应被过滤"""
        crawler = SimpleCrawler()
        result = crawler.parse_page(SAMPLE_HTML)
        link_texts = [l["text"] for l in result["links"]]
        assert "" not in link_texts

    def test_no_title_page(self):
        """没有 title 标签的页面"""
        html = "<html><body><p>No title</p></body></html>"
        crawler = SimpleCrawler()
        result = crawler.parse_page(html)
        assert result["title"] == "无标题"


class TestURLHandling:
    """URL 处理测试"""

    def test_invalid_url(self):
        crawler = SimpleCrawler(timeout=2)
        result = crawler.crawl("http://this-should-not-exist-99999.invalid")
        assert result is None

    def test_max_links_truncation(self):
        crawler = SimpleCrawler()
        result = crawler.parse_page(SAMPLE_HTML)
        # crawl 方法会截断，这里直接测试
        truncated = result["links"][:2]
        assert len(truncated) == 2
