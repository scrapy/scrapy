"""Tests that make sure parts needed for the scrapy-poet stack work."""

from typing import get_type_hints

from scrapy import Spider
from scrapy.spiders import CrawlSpider, CSVFeedSpider, SitemapSpider, XMLFeedSpider


def test_callbacks():
    """Making sure annotations on all non-abstract callbacks can be resolved."""

    for cb in [
        Spider._parse,
        CrawlSpider._parse,
        CrawlSpider._callback,
        XMLFeedSpider._parse,
        CSVFeedSpider._parse,
        SitemapSpider._parse_sitemap,
    ]:
        get_type_hints(cb)
