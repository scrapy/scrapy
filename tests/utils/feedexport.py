from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin
from urllib.request import pathname2url

from scrapy import Field, Item, Spider
from scrapy.utils.test import get_crawler

if TYPE_CHECKING:
    from collections.abc import Iterable

    from scrapy.crawler import Crawler
    from tests.mockserver.http import MockServer


def path_to_url(path: str | Path) -> str:
    return urljoin("file:", pathname2url(str(path)))


def printf_escape(s: str) -> str:
    return s.replace("%", "%%")


class MyItem(Item):
    foo = Field()
    egg = Field()
    baz = Field()


class MyItem2(Item):
    foo = Field()
    hello = Field()


async def crawl_items(
    mockserver: MockServer, items: Iterable[Any], settings: dict[str, Any]
) -> Crawler:
    """Run a spider that yields *items* from a single response with
    *settings*, and return its crawler."""

    class TestSpider(Spider):
        name = "testspider"
        start_urls = [mockserver.url("/")]

        def parse(self, response):
            yield from items

    crawler = get_crawler(TestSpider, settings)
    await crawler.crawl_async()
    return crawler


async def export_by_path(
    mockserver: MockServer, items: Iterable[Any], settings: dict[str, Any]
) -> dict[str | Path, bytes]:
    """Export *items* with *settings*, whose ``FEEDS`` are keyed by local
    paths, and return the contents of those paths that were written."""
    feeds = settings["FEEDS"]
    feed_urls = {
        printf_escape(path_to_url(path)): options for path, options in feeds.items()
    }
    await crawl_items(mockserver, items, {**settings, "FEEDS": feed_urls})
    return {path: Path(path).read_bytes() for path in feeds if Path(path).exists()}
