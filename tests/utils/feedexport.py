from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin
from urllib.request import pathname2url

from scrapy import Field, Item, Spider
from scrapy.utils.test import get_crawler

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

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
