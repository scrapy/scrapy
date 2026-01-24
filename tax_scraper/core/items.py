"""
Data schema for scraped tax content.
Optimized for AI training data requirements.
"""

import scrapy
from scrapy.loader import ItemLoader
from itemloaders.processors import TakeFirst, MapCompose, Join
from w3lib.html import remove_tags
import hashlib
from datetime import datetime


def clean_text(text):
    """Clean and normalize text content."""
    if text:
        return " ".join(text.split())
    return ""


def generate_id(values):
    """Generate unique ID from URL."""
    if values:
        url = values[0] if isinstance(values, list) else values
        return hashlib.sha256(url.encode()).hexdigest()[:16]
    return None


class TaxArticleItem(scrapy.Item):
    """
    Unified schema for tax-related content.

    Fields:
        id: Unique identifier (hash of URL)
        source: Website domain
        url: Full URL of the article
        title: Article title
        content: Full text content (cleaned)
        summary: First 500 characters for preview
        category: Tax category (individual | s.p. | d.o.o. | general)
        tax_topics: List of detected tax keywords
        author: Article author if available
        published_date: Original publication date
        scraped_at: Timestamp when scraped
        language: Content language (default: sl)
        raw_html: Optional raw HTML for reprocessing
    """

    # Identifiers
    id = scrapy.Field()
    source = scrapy.Field()
    url = scrapy.Field()

    # Content
    title = scrapy.Field()
    content = scrapy.Field()
    summary = scrapy.Field()
    raw_html = scrapy.Field()

    # Classification
    category = scrapy.Field()
    tax_topics = scrapy.Field()

    # Metadata
    author = scrapy.Field()
    published_date = scrapy.Field()
    scraped_at = scrapy.Field()
    language = scrapy.Field()


class TaxArticleLoader(ItemLoader):
    """Item loader with default processors for cleaning data."""

    default_item_class = TaxArticleItem
    default_output_processor = TakeFirst()

    # Text cleaning
    title_in = MapCompose(remove_tags, clean_text)
    content_in = MapCompose(remove_tags, clean_text)
    author_in = MapCompose(remove_tags, clean_text)

    # Lists
    tax_topics_out = lambda x: list(set(x)) if x else []
