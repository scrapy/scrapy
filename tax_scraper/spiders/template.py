"""
Template for creating new site spiders.

Copy this file and modify for your target site:
1. Rename the file to match your site (e.g., mysite.py)
2. Rename the class (e.g., MySiteSpider)
3. Update name, allowed_domains, start_urls
4. Implement parse_article_list() and parse_article()
5. The spider will be auto-discovered

Example usage after creation:
    python -m tax_scraper scrape --site mysite
"""

import scrapy
from typing import Iterator

from ..core.base_spider import BaseTaxSpider
from ..core.items import TaxArticleItem
from .registry import SpiderRegistry


# Uncomment @SpiderRegistry.register when ready to use
# @SpiderRegistry.register
class TemplateSpider(BaseTaxSpider):
    """
    Spider for [YOUR SITE NAME].

    Brief description of the site and what content it has.
    """

    name = "template"  # Unique identifier for this spider
    allowed_domains = ["example.com"]  # Allowed domains to crawl
    start_urls = [
        "https://example.com/tax-articles/",  # Starting URL(s)
    ]

    # Optional: Custom settings for this specific site
    custom_settings = {
        **BaseTaxSpider.custom_settings,
        # Uncomment and modify as needed:
        # "DOWNLOAD_DELAY": 2,  # Seconds between requests
        # "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        # "COOKIES_ENABLED": True,  # If site needs cookies
    }

    def parse_article_list(self, response) -> Iterator[scrapy.Request]:
        """
        Parse the listing page(s) to find article links.

        TODO: Implement for your site:
        1. Identify CSS/XPath selectors for article links
        2. Yield Request for each article
        3. Handle pagination if present
        """
        self.logger.info(f"Parsing list page: {response.url}")

        # Example: Extract article links
        # Modify these selectors based on the target site's HTML structure
        article_links = response.css("article a::attr(href)").getall()

        for link in article_links:
            full_url = response.urljoin(link)
            self.articles_found += 1
            yield scrapy.Request(
                full_url,
                callback=self.parse_article,
            )

        # Example: Handle pagination
        next_page = response.css("a.next::attr(href)").get()
        if next_page:
            yield scrapy.Request(
                response.urljoin(next_page),
                callback=self.parse_article_list,
            )

    def parse_article(self, response) -> Iterator[TaxArticleItem]:
        """
        Parse an individual article page.

        TODO: Implement for your site:
        1. Create loader with self.create_loader(response)
        2. Add title, content, author, date using CSS/XPath selectors
        3. Finalize with self.finalize_item(loader)
        """
        self.logger.info(f"Parsing article: {response.url}")

        loader = self.create_loader(response)

        # Example: Extract title
        # Modify selector based on site structure
        loader.add_css("title", "h1::text")

        # Example: Extract content
        # Get all paragraph text from the article
        content = response.css("article p::text").getall()
        loader.add_value("content", " ".join(content))

        # Example: Extract author (optional)
        loader.add_css("author", ".author-name::text")

        # Example: Extract date (optional)
        loader.add_css("published_date", "time::attr(datetime)")

        # Optional: Store raw HTML for reprocessing later
        loader.add_value("raw_html", response.text)

        # Finalize and yield the item
        yield self.finalize_item(loader)
