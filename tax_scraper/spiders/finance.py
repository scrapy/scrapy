"""
Spider for finance.si - Slovenian financial news portal.
"""

import scrapy
from typing import Iterator

from ..core.base_spider import BaseTaxSpider
from ..core.items import TaxArticleItem
from .registry import SpiderRegistry


@SpiderRegistry.register
class FinanceSpider(BaseTaxSpider):
    """
    Spider for scraping tax-related articles from finance.si.

    Finance.si is a major Slovenian financial news portal.
    We focus on tax-related articles (davki section).
    """

    name = "finance"
    allowed_domains = ["finance.si", "www.finance.si"]
    start_urls = [
        "https://www.finance.si/davki",
        "https://www.finance.si/tag/davki",
    ]

    # News sites often have rate limiting
    custom_settings = {
        **BaseTaxSpider.custom_settings,
        "DOWNLOAD_DELAY": 2,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        # Handle potential paywall/cookie notices
        "COOKIES_ENABLED": True,
    }

    def parse_article_list(self, response) -> Iterator[scrapy.Request]:
        """
        Parse finance.si article listings.

        Common news site structure with article cards/lists.
        """
        self.logger.info(f"Parsing finance.si list: {response.url}")

        # Article link selectors for news sites
        article_selectors = [
            "article a::attr(href)",
            ".article-item a::attr(href)",
            ".news-item a::attr(href)",
            'a.article-link::attr(href)',
            ".teaser a::attr(href)",
            "h2 a::attr(href)",
            "h3 a::attr(href)",
            '.post a[href*="/"]::attr(href)',
        ]

        found_urls = set()
        for selector in article_selectors:
            urls = response.css(selector).getall()
            found_urls.update(urls)

        for url in found_urls:
            full_url = response.urljoin(url)

            # Only process finance.si URLs
            if "finance.si" not in full_url:
                continue

            # Skip non-article URLs
            skip_patterns = [
                "/tag/", "/avtor/", "/kategorija/",
                "/page/", "/stran/", "#",
                "/prijava", "/registracija",
                ".pdf", ".jpg", ".png",
            ]
            if any(p in full_url.lower() for p in skip_patterns):
                continue

            # Article URLs typically have a pattern with slugs
            # e.g., /finance/davki/some-article-title
            if len(url) > 20:  # Likely an article, not a category
                self.articles_found += 1
                yield scrapy.Request(
                    full_url,
                    callback=self.parse_article,
                )

        # Pagination - try various patterns
        next_selectors = [
            "a.next::attr(href)",
            ".pagination a.next::attr(href)",
            'a[rel="next"]::attr(href)',
            'a:contains("Naprej")::attr(href)',
            'a:contains("Naslednja")::attr(href)',
            ".pager-next a::attr(href)",
        ]

        for selector in next_selectors:
            next_page = response.css(selector).get()
            if next_page:
                yield scrapy.Request(
                    response.urljoin(next_page),
                    callback=self.parse_article_list,
                )
                break

    def parse_article(self, response) -> Iterator[TaxArticleItem]:
        """
        Parse a finance.si article.
        """
        self.logger.info(f"Parsing article: {response.url}")

        # Check for paywall/premium content
        paywall_indicators = [
            ".paywall",
            ".premium-only",
            ".subscription-required",
        ]
        for indicator in paywall_indicators:
            if response.css(indicator):
                self.logger.info(f"Skipping premium article: {response.url}")
                return

        loader = self.create_loader(response)

        # Title
        title_selectors = [
            "h1.article-title::text",
            "h1::text",
            'meta[property="og:title"]::attr(content)',
            ".article-header h1::text",
            "title::text",
        ]
        for selector in title_selectors:
            title = response.css(selector).get()
            if title:
                # Clean up title
                title = title.replace(" | Finance.si", "").strip()
                loader.add_value("title", title)
                break

        # Content - news articles usually have clear article body
        content_selectors = [
            ".article-body",
            ".article-content",
            ".post-content",
            "article .content",
            ".story-body",
            "[itemprop='articleBody']",
        ]

        for selector in content_selectors:
            content_el = response.css(selector)
            if content_el:
                # Get all paragraph text
                paragraphs = content_el.css("p::text").getall()
                if paragraphs:
                    loader.add_value("content", " ".join(paragraphs))
                    break

        # If no content found with specific selectors, try generic
        if not loader.get_output_value("content"):
            # Fallback: get all text from article tag
            article_text = response.css("article *::text").getall()
            if article_text:
                loader.add_value("content", " ".join(article_text))

        # Author
        author_selectors = [
            ".author-name::text",
            'meta[name="author"]::attr(content)',
            ".article-author::text",
            "[itemprop='author']::text",
            ".byline::text",
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
            "[itemprop='datePublished']::attr(content)",
            ".article-date::text",
            ".publish-date::text",
        ]
        for selector in date_selectors:
            date = response.css(selector).get()
            if date:
                loader.add_value("published_date", date)
                break

        loader.add_value("raw_html", response.text)

        yield self.finalize_item(loader)
