"""
Spider for simic-partnerji.si blog - Slovenian tax advisory blog.
"""

import scrapy
from typing import Iterator

from ..core.base_spider import BaseTaxSpider
from ..core.items import TaxArticleItem
from .registry import SpiderRegistry


@SpiderRegistry.register
class SimicBlogSpider(BaseTaxSpider):
    """
    Spider for scraping tax articles from simic-partnerji.si/blog/

    This site is a Slovenian tax advisory firm's blog with articles about
    taxation for individuals, sole proprietors (s.p.), and companies (d.o.o.).
    """

    name = "simic"
    allowed_domains = ["simic-partnerji.si"]
    start_urls = ["https://simic-partnerji.si/blog/"]

    # Custom settings for this site
    custom_settings = {
        **BaseTaxSpider.custom_settings,
        "DOWNLOAD_DELAY": 1.5,  # Be extra polite
    }

    def parse_article_list(self, response) -> Iterator[scrapy.Request]:
        """
        Parse the blog listing page.

        Expected structure (common WordPress blog):
        - Article links in article/div containers
        - Pagination at the bottom
        """
        self.logger.info(f"Parsing article list: {response.url}")

        # Try multiple common selectors for blog listings
        article_selectors = [
            "article a::attr(href)",
            ".post a::attr(href)",
            ".blog-post a::attr(href)",
            ".entry-title a::attr(href)",
            "h2 a::attr(href)",
            ".post-title a::attr(href)",
            'a[href*="/blog/"]::attr(href)',
        ]

        found_urls = set()
        for selector in article_selectors:
            urls = response.css(selector).getall()
            found_urls.update(urls)

        # Filter to only blog article URLs
        for url in found_urls:
            full_url = response.urljoin(url)
            # Skip pagination, category, tag, and author URLs
            skip_patterns = ["/page/", "/category/", "/tag/", "/author/", "#"]
            if any(p in full_url for p in skip_patterns):
                continue

            # Must be on same domain
            if "simic-partnerji.si" in full_url:
                self.articles_found += 1
                yield scrapy.Request(
                    full_url,
                    callback=self.parse_article,
                    meta={"dont_redirect": False},
                )

        # Handle pagination
        next_page_selectors = [
            "a.next::attr(href)",
            ".nav-next a::attr(href)",
            'a[rel="next"]::attr(href)',
            ".pagination a.next::attr(href)",
            'a:contains("Naslednja")::attr(href)',
            'a:contains("»")::attr(href)',
        ]

        for selector in next_page_selectors:
            next_page = response.css(selector).get()
            if next_page:
                self.logger.info(f"Following pagination: {next_page}")
                yield scrapy.Request(
                    response.urljoin(next_page),
                    callback=self.parse_article_list,
                )
                break

    def parse_article(self, response) -> Iterator[TaxArticleItem]:
        """
        Parse an individual blog article.
        """
        self.logger.info(f"Parsing article: {response.url}")

        loader = self.create_loader(response)

        # Title - try multiple selectors
        title_selectors = [
            "h1.entry-title::text",
            "h1::text",
            ".post-title::text",
            'meta[property="og:title"]::attr(content)',
            "title::text",
        ]
        for selector in title_selectors:
            title = response.css(selector).get()
            if title:
                loader.add_value("title", title)
                break

        # Content - try multiple selectors
        content_selectors = [
            ".entry-content",
            ".post-content",
            "article .content",
            ".blog-content",
            "article",
        ]
        for selector in content_selectors:
            content = response.css(f"{selector} *::text").getall()
            if content:
                loader.add_value("content", " ".join(content))
                break

        # Author
        author_selectors = [
            ".author-name::text",
            'meta[name="author"]::attr(content)',
            ".post-author::text",
            'a[rel="author"]::text',
        ]
        for selector in author_selectors:
            author = response.css(selector).get()
            if author:
                loader.add_value("author", author)
                break

        # Published date
        date_selectors = [
            'time::attr(datetime)',
            'meta[property="article:published_time"]::attr(content)',
            ".post-date::text",
            ".entry-date::text",
        ]
        for selector in date_selectors:
            date = response.css(selector).get()
            if date:
                loader.add_value("published_date", date)
                break

        # Store raw HTML for potential reprocessing
        loader.add_value("raw_html", response.text)

        yield self.finalize_item(loader)
