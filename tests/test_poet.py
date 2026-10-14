"""Tests that make sure parts needed for the scrapy-poet stack work."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, get_type_hints

import pytest

from scrapy import Spider
from scrapy.spiders import CrawlSpider, CSVFeedSpider, SitemapSpider, XMLFeedSpider

if TYPE_CHECKING:
    from collections.abc import Callable


@pytest.mark.parametrize(
    "cb",
    [
        Spider._parse,
        CrawlSpider._parse,
        CrawlSpider._callback,
        XMLFeedSpider._parse,
        CSVFeedSpider._parse,
        SitemapSpider._parse_sitemap,
    ],
    ids=lambda cb: cb.__qualname__,
)
def test_callbacks(cb: Callable[..., Any]) -> None:
    """Making sure annotations on all non-abstract callbacks can be resolved."""
    get_type_hints(cb)
