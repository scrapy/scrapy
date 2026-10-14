from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

import pytest

from scrapy import Request, Spider
from scrapy.core.scraper import Scraper
from scrapy.exceptions import IgnoreRequest
from scrapy.http import Response
from scrapy.utils.defer import maybe_deferred_to_future
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler
from tests.spiders import SimpleSpider
from tests.utils.decorators import coroutine_test, inline_callbacks_test

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Generator, Iterable

    from twisted.internet.defer import Deferred

    from tests.mockserver.http import MockServer


@coroutine_test
async def test_scraper_exception(
    mockserver: MockServer,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    crawler = get_crawler(SimpleSpider)
    monkeypatch.setattr(
        "scrapy.core.engine.Scraper.handle_spider_output_async",
        lambda *args, **kwargs: 1 / 0,
    )
    await crawler.crawl_async(url=mockserver.url("/"))
    assert "Scraper bug processing" in caplog.text


@coroutine_test
async def test_open_spider_without_spider() -> None:
    scraper = Scraper(get_crawler(DefaultSpider))
    with pytest.raises(RuntimeError, match=r"called before Crawler\.spider is set"):
        await scraper.open_spider_async()


@inline_callbacks_test
def test_enqueue_scrape_without_slot() -> Generator[Deferred[Any], Any, None]:
    scraper = Scraper(get_crawler(DefaultSpider))
    with pytest.raises(RuntimeError, match="Scraper slot not assigned"):
        yield scraper.enqueue_scrape(Response("data:,"), Request("data:,"))


@coroutine_test
async def test_enqueue_scrape_wrong_type(caplog: pytest.LogCaptureFixture) -> None:
    crawler = get_crawler(DefaultSpider)
    crawler.spider = crawler._create_spider()
    scraper = Scraper(crawler)
    await scraper.open_spider_async()
    try:
        await maybe_deferred_to_future(
            scraper.enqueue_scrape("not a response", Request("data:,"))  # type: ignore[arg-type]
        )
    finally:
        await scraper.close_spider_async()
    assert "expected Response or Failure, got <class 'str'>" in caplog.text


@coroutine_test
async def test_call_spider_sets_request_on_response() -> None:
    class ParsingSpider(Spider):
        name = "parsing"

        def parse(self, response: Response) -> Iterable[Any]:
            return [response.url]

    crawler = get_crawler(ParsingSpider)
    crawler.spider = crawler._create_spider()
    scraper = Scraper(crawler)
    response = Response("data:,")
    request = Request("data:,")
    output = await scraper.call_spider_async(response, request)
    assert response.request is request
    assert list(cast("Iterable[Any]", output)) == ["data:,"]


@coroutine_test
async def test_errback_error_on_ignored_request(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An errback failing on an ignored request does not log a download error."""

    class IgnoreMiddleware:
        def process_request(self, request: Request) -> None:
            raise IgnoreRequest("nope")

    class ErrbackSpider(Spider):
        name = "errback"

        async def start(self) -> AsyncIterator[Any]:
            yield Request("data:,", errback=self.errback)

        def errback(self, failure: Any) -> None:
            raise ValueError("errback error")

    crawler = get_crawler(
        ErrbackSpider, {"DOWNLOADER_MIDDLEWARES": {IgnoreMiddleware: 1}}
    )
    with caplog.at_level(logging.DEBUG):
        await crawler.crawl_async()
    assert "Error downloading" not in caplog.text
    assert crawler.stats.get_value("spider_exceptions/ValueError") == 1


@coroutine_test
async def test_none_in_callback_output() -> None:
    """``None`` in the callback output is dropped, without dropping later items."""

    class NoneSpider(Spider):
        name = "none"

        async def start(self) -> AsyncIterator[Any]:
            yield Request("data:,")

        def parse(self, response: Response) -> Iterable[Any]:
            yield {"index": 1}
            yield None
            yield {"index": 2}

    crawler = get_crawler(
        NoneSpider,
        # The built-in spider middlewares would drop the None before the
        # scraper gets to see it. A single concurrent item makes sure that the
        # None and the item that follows it are handled by the same worker.
        {"CONCURRENT_ITEMS": 1, "SPIDER_MIDDLEWARES_BASE": {}},
    )
    await crawler.crawl_async()
    assert crawler.stats.get_value("item_scraped_count") == 2
