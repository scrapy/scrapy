from __future__ import annotations

from typing import TYPE_CHECKING, Any

from scrapy import signals
from scrapy.utils.test import get_crawler

if TYPE_CHECKING:
    from scrapy.crawler import Crawler
    from scrapy.spiders import Spider
    from tests.mockserver.http import MockServer


async def crawl_items(
    spider_cls: type[Spider], mockserver: MockServer, **kwargs: Any
) -> tuple[list[Any], Crawler]:
    """Run *spider_cls* against *mockserver* and return the scraped items along
    with the crawler, which gives tests access to the resulting stats."""
    items: list[Any] = []

    def collect(item: Any) -> None:
        items.append(item)

    crawler = get_crawler(spider_cls)
    crawler.signals.connect(collect, signals.item_scraped)
    await crawler.crawl_async(mockserver=mockserver, **kwargs)
    return items, crawler
