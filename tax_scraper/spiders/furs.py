"""
Spider for fu.gov.si - Slovenian Financial Administration (FURS) official website.
"""

import scrapy
from typing import Iterator
from urllib.parse import urljoin

from ..core.base_spider import BaseTaxSpider
from ..core.items import TaxArticleItem
from .registry import SpiderRegistry


@SpiderRegistry.register
class FursSpider(BaseTaxSpider):
    """
    Spider for scraping tax information from fu.gov.si (FURS - Finančna uprava).

    This is the official Slovenian government tax authority website.
    Contains authoritative information about all tax types.

    Sections of interest:
    - /davki/ - Tax information
    - /fizicne_osebe/ - Individuals
    - /poslovni_subjekti/ - Business entities
    - /novice/ - News/updates
    """

    name = "furs"
    allowed_domains = ["fu.gov.si", "www.fu.gov.si"]
    start_urls = [
        "https://www.fu.gov.si/",
        "https://www.fu.gov.si/davki/",
        "https://www.fu.gov.si/fizicne_osebe/",
        "https://www.fu.gov.si/poslovni_subjekti/",
    ]

    # Government sites may be slower - be respectful
    custom_settings = {
        **BaseTaxSpider.custom_settings,
        "DOWNLOAD_DELAY": 2,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
    }

    # Track visited URLs to avoid duplicates
    visited_urls = set()

    def parse_article_list(self, response) -> Iterator[scrapy.Request]:
        """
        Parse FURS pages - both navigation and content pages.

        FURS structure is hierarchical with main sections and sub-pages.
        We crawl both to find all content pages.
        """
        self.logger.info(f"Parsing FURS page: {response.url}")

        # Skip if already visited
        if response.url in self.visited_urls:
            return
        self.visited_urls.add(response.url)

        # Check if this page has substantial content - if so, parse it
        main_content = response.css(".main-content, .content, article, .vsebina")
        if main_content:
            content_text = " ".join(main_content.css("*::text").getall())
            if len(content_text) > 500:  # Has real content
                yield from self.parse_article(response)

        # Find and follow relevant links
        relevant_sections = [
            "/davki/",
            "/fizicne_osebe/",
            "/poslovni_subjekti/",
            "/novice/",
            "/podrobnejsi_opis/",
            "/dohodnina/",
            "/ddv/",
        ]

        # Get all internal links
        all_links = response.css('a[href]::attr(href)').getall()

        for link in all_links:
            full_url = urljoin(response.url, link)

            # Skip external links
            if "fu.gov.si" not in full_url:
                continue

            # Skip already visited
            if full_url in self.visited_urls:
                continue

            # Skip non-content links
            skip_patterns = [
                ".pdf", ".doc", ".xls", ".zip",
                "/en/", "/iskalnik/", "mailto:",
                "/obrazci/", "#", "javascript:",
            ]
            if any(p in full_url.lower() for p in skip_patterns):
                continue

            # Prioritize relevant sections
            is_relevant = any(section in full_url for section in relevant_sections)

            self.articles_found += 1
            yield scrapy.Request(
                full_url,
                callback=self.parse_article_list,
                priority=1 if is_relevant else 0,
                meta={"depth": response.meta.get("depth", 0) + 1},
            )

    def parse_article(self, response) -> Iterator[TaxArticleItem]:
        """
        Parse a FURS content page.
        """
        self.logger.info(f"Extracting content from: {response.url}")

        loader = self.create_loader(response)

        # Title
        title_selectors = [
            "h1::text",
            ".page-title::text",
            'meta[property="og:title"]::attr(content)',
            "title::text",
        ]
        for selector in title_selectors:
            title = response.css(selector).get()
            if title:
                loader.add_value("title", title.replace(" | GOV.SI", "").strip())
                break

        # Main content
        content_selectors = [
            ".main-content",
            ".vsebina",
            ".content",
            "article",
            "#content",
            "main",
        ]
        for selector in content_selectors:
            content_el = response.css(selector)
            if content_el:
                # Get text but exclude navigation elements
                content_parts = []
                for text in content_el.css("p::text, li::text, h2::text, h3::text, td::text").getall():
                    if text.strip():
                        content_parts.append(text.strip())

                if content_parts:
                    loader.add_value("content", " ".join(content_parts))
                    break

        # Check if we have enough content
        item = loader.load_item()
        if len(item.get("content", "")) < 200:
            self.logger.debug(f"Skipping low-content page: {response.url}")
            return

        # Update date if available
        date_selectors = [
            'meta[property="article:modified_time"]::attr(content)',
            'meta[property="article:published_time"]::attr(content)',
            ".date::text",
            ".objava-datum::text",
        ]
        for selector in date_selectors:
            date = response.css(selector).get()
            if date:
                loader.add_value("published_date", date)
                break

        loader.add_value("author", "FURS")
        loader.add_value("raw_html", response.text)

        yield self.finalize_item(loader)
