"""
Base spider class for all tax content scrapers.
Provides common functionality and enforces consistent behavior.
"""

import scrapy
from abc import abstractmethod
from datetime import datetime
from urllib.parse import urlparse
from typing import List, Optional, Iterator, Any

from .items import TaxArticleItem, TaxArticleLoader
from ..filters.tax_keywords import TaxKeywordFilter


class BaseTaxSpider(scrapy.Spider):
    """
    Abstract base class for tax content spiders.

    All site-specific spiders should inherit from this class and implement:
        - parse_article_list(): Extract article links from listing pages
        - parse_article(): Extract content from individual articles

    Attributes:
        name: Spider identifier (required)
        allowed_domains: List of allowed domains
        start_urls: Initial URLs to crawl
        tax_filter: Keyword filter instance
    """

    # Default settings for polite crawling
    custom_settings = {
        "DOWNLOAD_DELAY": 1,  # 1 second between requests
        "RANDOMIZE_DOWNLOAD_DELAY": True,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
        "COOKIES_ENABLED": False,
        "USER_AGENT": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "DEFAULT_REQUEST_HEADERS": {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "sl,en;q=0.9",
        },
        "RETRY_ENABLED": True,
        "RETRY_TIMES": 3,
        "RETRY_HTTP_CODES": [500, 502, 503, 504, 408, 429],
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tax_filter = TaxKeywordFilter()
        self.articles_found = 0
        self.articles_scraped = 0

    @property
    def source_domain(self) -> str:
        """Return the primary domain being scraped."""
        if self.allowed_domains:
            return self.allowed_domains[0]
        return urlparse(self.start_urls[0]).netloc if self.start_urls else "unknown"

    def parse(self, response):
        """
        Default entry point - routes to article list parsing.
        Override if your site needs different initial handling.
        """
        yield from self.parse_article_list(response)

    @abstractmethod
    def parse_article_list(self, response) -> Iterator[scrapy.Request]:
        """
        Parse a listing page and yield requests for individual articles.

        Should:
            1. Extract links to individual articles
            2. Yield Request objects with callback=self.parse_article
            3. Handle pagination if present

        Args:
            response: Scrapy Response object

        Yields:
            scrapy.Request objects for article pages
        """
        pass

    @abstractmethod
    def parse_article(self, response) -> Iterator[TaxArticleItem]:
        """
        Parse an individual article page and extract content.

        Should use create_loader() to build items consistently.

        Args:
            response: Scrapy Response object

        Yields:
            TaxArticleItem objects
        """
        pass

    def create_loader(self, response) -> TaxArticleLoader:
        """
        Create a pre-configured item loader for an article.

        Automatically sets:
            - id (from URL)
            - source (domain)
            - url
            - scraped_at
            - language

        Args:
            response: Scrapy Response object

        Returns:
            Configured TaxArticleLoader
        """
        loader = TaxArticleLoader(item=TaxArticleItem(), response=response)

        # Auto-populate standard fields
        loader.add_value("url", response.url)
        loader.add_value("source", self.source_domain)
        loader.add_value("scraped_at", datetime.utcnow().isoformat())
        loader.add_value("language", "sl")

        return loader

    def classify_content(self, text: str) -> dict:
        """
        Analyze text and return classification info.

        Args:
            text: Article text content

        Returns:
            dict with 'category' and 'tax_topics' keys
        """
        return self.tax_filter.classify(text)

    def finalize_item(self, loader: TaxArticleLoader) -> TaxArticleItem:
        """
        Finalize item: generate ID, summary, and classifications.

        Call this after adding all fields to the loader.

        Args:
            loader: Populated TaxArticleLoader

        Returns:
            Finalized TaxArticleItem
        """
        item = loader.load_item()

        # Generate ID from URL
        import hashlib
        if item.get("url"):
            item["id"] = hashlib.sha256(item["url"].encode()).hexdigest()[:16]

        # Generate summary from content
        content = item.get("content", "")
        if content:
            item["summary"] = content[:500] + "..." if len(content) > 500 else content

            # Classify content
            classification = self.classify_content(content)
            item["category"] = classification["category"]
            item["tax_topics"] = classification["tax_topics"]

        self.articles_scraped += 1
        return item

    def closed(self, reason):
        """Log statistics when spider closes."""
        self.logger.info(
            f"Spider closed: {reason}. "
            f"Found {self.articles_found} articles, scraped {self.articles_scraped}."
        )
