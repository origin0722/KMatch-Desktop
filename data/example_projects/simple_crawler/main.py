"""
KMatch 示例项目 — 简易网页爬虫
用于「有项目二次开发」场景的教学演示。
功能: 爬取指定网页的标题和链接，支持基本错误处理。
Python 3.10+, requests + BeautifulSoup4
"""

import sys
import time
from typing import List, Dict, Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


class SimpleCrawler:
    """简易网页爬虫 — 爬取页面标题和所有链接"""

    def __init__(self, timeout: int = 10, user_agent: Optional[str] = None):
        self.timeout = timeout
        self.user_agent = user_agent or (
            "Mozilla/5.0 (compatible; KMatch-Crawler/1.0; Educational Purpose)"
        )
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent})

    def fetch_page(self, url: str) -> Optional[str]:
        """获取页面 HTML 内容"""
        try:
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            print(f"❌ 请求失败 [{url}]: {e}", file=sys.stderr)
            return None

    def parse_page(self, html: str) -> Dict[str, any]:
        """解析 HTML，提取标题和链接"""
        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.string.strip() if soup.title else "无标题"

        links: List[Dict[str, str]] = []
        for a_tag in soup.find_all("a", href=True):
            text = a_tag.get_text(strip=True)
            href = a_tag["href"]
            if text and href:
                links.append({"text": text[:100], "href": href})

        return {"title": title, "link_count": len(links), "links": links}

    def crawl(self, url: str, max_links: int = 50) -> Optional[Dict]:
        """爬取单个页面，返回结构化结果"""
        print(f"🔍 正在爬取: {url}")
        html = self.fetch_page(url)
        if html is None:
            return None

        result = self.parse_page(html)
        result["url"] = url
        result["links"] = result["links"][:max_links]

        print(f"   ✅ 标题: {result['title']}")
        print(f"   📎 链接数: {result['link_count']} (显示前 {max_links} 条)")
        return result

    def crawl_sitemap(self, base_url: str, max_pages: int = 10, delay: float = 1.0) -> List[Dict]:
        """从首页开始递归爬取同域名页面（简单广度优先）"""
        base_domain = urlparse(base_url).netloc
        visited = set()
        results = []

        to_visit = [base_url]
        while to_visit and len(results) < max_pages:
            url = to_visit.pop(0)
            if url in visited:
                continue
            visited.add(url)

            result = self.crawl(url)
            if result is None:
                continue

            results.append(result)

            # 收集同域名的新链接
            for link in result.get("links", []):
                href = link["href"]
                full_url = urljoin(url, href)
                if (
                    urlparse(full_url).netloc == base_domain
                    and full_url not in visited
                    and len(results) + len(to_visit) < max_pages
                ):
                    to_visit.append(full_url)

            time.sleep(delay)  # 礼貌爬取

        return results


def main():
    """命令行入口"""
    if len(sys.argv) < 2:
        print("用法: python main.py <url> [max_pages]")
        print("示例: python main.py https://example.com 5")
        sys.exit(1)

    url = sys.argv[1]
    max_pages = int(sys.argv[2]) if len(sys.argv) > 2 else 1

    crawler = SimpleCrawler()

    if max_pages == 1:
        result = crawler.crawl(url)
        if result:
            print(f"\n--- 爬取结果 ---")
            print(f"标题: {result['title']}")
            print(f"链接数: {result['link_count']}")
            for i, link in enumerate(result["links"][:10], 1):
                print(f"  {i}. {link['text']} → {link['href']}")
    else:
        results = crawler.crawl_sitemap(url, max_pages=max_pages)
        print(f"\n--- 爬取完成: {len(results)} 个页面 ---")
        for r in results:
            print(f"  [{r['title']}] {r['url']} ({r['link_count']} links)")


if __name__ == "__main__":
    main()
