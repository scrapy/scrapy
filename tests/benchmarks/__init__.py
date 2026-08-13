from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from scrapy.http import Response
from scrapy.utils.test import get_crawler

if TYPE_CHECKING:
    from scrapy import Request, Spider
    from scrapy.crawler import Crawler


class NullDownloadHandler:
    """Download handler that returns an empty response without doing any I/O.

    It lets benchmarks measure the engine, the scheduler and the middlewares
    without also measuring HTTP parsing and socket handling, and reach as many
    hostnames as they need without DNS resolution.

    It yields control to the event loop once per request, so that requests can
    be in progress at the same time and concurrency limits apply. The peak
    number of requests in progress is tracked in the
    ``benchmark/peak_concurrency`` stat.
    """

    lazy = False

    def __init__(self, crawler: Crawler):
        self._crawler = crawler
        self._active = 0

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> NullDownloadHandler:
        return cls(crawler)

    async def download_request(self, request: Request) -> Response:
        self._active += 1
        assert self._crawler.stats
        self._crawler.stats.max_value("benchmark/peak_concurrency", self._active)
        try:
            await asyncio.sleep(0)
            return Response(request.url, request=request)
        finally:
            self._active -= 1

    async def close(self) -> None:
        pass


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
