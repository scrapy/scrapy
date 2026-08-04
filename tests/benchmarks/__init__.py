from __future__ import annotations

from typing import TYPE_CHECKING, Any

from scrapy.utils.test import get_crawler

if TYPE_CHECKING:
    from scrapy import Spider
    from scrapy.crawler import Crawler


def crawl(spidercls: type[Spider], settings: dict[str, Any], **kwargs: Any) -> Crawler:
    """Run a crawl to completion and return its crawler.

    Unlike the rest of the test suite, benchmarks run without ``pytest-twisted``
    and drive the reactor themselves, since the code being measured must be
    callable synchronously by ``pytest-codspeed``.
    """
    from twisted.internet import reactor

    crawler = get_crawler(spidercls, settings)
    result: list[Any] = []
    crawler.crawl(**kwargs).addBoth(result.append)
    while not result:
        reactor.iterate(0.001)
    if isinstance(result[0], BaseException):
        raise result[0]
    return crawler
