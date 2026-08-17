"""
Some spiders used for testing and benchmarking
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

from twisted.internet import defer

from scrapy import signals
from scrapy.exceptions import StopDownload
from scrapy.http import Request, TextResponse
from scrapy.item import Item
from scrapy.linkextractors import LinkExtractor
from scrapy.spidermiddlewares.httperror import HttpError
from scrapy.spiders import Spider
from scrapy.spiders.crawl import CrawlSpider, Rule
from scrapy.utils.defer import deferred_to_future, maybe_deferred_to_future
from scrapy.utils.test import get_from_asyncio_queue

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Iterator

    from twisted.python.failure import Failure
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.http import Headers, Response
    from scrapy.http.request import CallbackT
    from tests.mockserver.http import MockServer


class MockServerSpider(Spider):
    def __init__(
        self,
        *args: Any,
        mockserver: MockServer | None = None,
        is_secure: bool = False,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        self.mockserver = mockserver
        self.is_secure = is_secure


class RawResponseSpider(MockServerSpider):
    """Base class for spiders that fetch a response built by the test itself.

    Subclasses return the body from :meth:`raw_body` and request
    :attr:`raw_url`, which the mock server answers with that body verbatim
    under :attr:`content_type`. This lets tests reach parsing code that only
    a specific kind of response triggers while still going through a regular
    crawl, instead of calling internal parsing methods directly.
    """

    name = "raw_response"
    content_type = "text/plain"

    def raw_body(self) -> str:
        raise NotImplementedError

    @property
    def raw_url(self) -> str:
        assert self.mockserver
        raw = (
            "HTTP/1.1 200 OK\r\n"
            f"Content-Type: {self.content_type}\r\n"
            "Connection: close\r\n"
            "\r\n"
            f"{self.raw_body()}"
        )
        return self.mockserver.url("/raw?" + urlencode({"raw": raw}))


class MetaSpider(MockServerSpider):
    name = "meta"

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.meta: dict[str, Any] = {}

    def closed(self, reason: str) -> None:
        self.meta["close_reason"] = reason


class FollowAllSpider(MetaSpider):
    name = "follow"
    link_extractor = LinkExtractor()

    def __init__(
        self,
        total: int = 10,
        show: int = 20,
        order: str = "rand",
        maxlatency: float = 0.0,
        *args: Any,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        self.urls_visited: list[str] = []
        self.times: list[float] = []
        qargs = {"total": total, "show": show, "order": order, "maxlatency": maxlatency}
        assert self.mockserver
        url = self.mockserver.url(f"/follow?{urlencode(qargs, doseq=True)}")
        self.start_urls = [url]

    def parse(self, response: Response) -> Iterator[Any]:
        assert isinstance(response, TextResponse)
        self.urls_visited.append(response.url)
        self.times.append(time.time())
        for link in self.link_extractor.extract_links(response):
            yield Request(link.url, callback=self.parse)


class DelaySpider(MetaSpider):
    name = "delay"

    def __init__(self, n: float = 1, b: float = 0, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.n = n
        self.b = b
        self.t1 = self.t2 = self.t2_err = 0.0

    async def start(self) -> AsyncIterator[Any]:
        self.t1 = time.time()
        assert self.mockserver
        url = self.mockserver.url(f"/delay?n={self.n}&b={self.b}")
        yield Request(url, callback=self.parse, errback=self.errback)

    def parse(self, response: Response) -> Any:
        self.t2 = time.time()

    def errback(self, failure: Failure) -> None:
        self.t2_err = time.time()


class LogSpider(MetaSpider):
    name = "log_spider"

    def log_debug(self, message: str, extra: dict[str, Any] | None = None) -> None:
        self.logger.debug(message, extra=extra)

    def log_info(self, message: str, extra: dict[str, Any] | None = None) -> None:
        self.logger.info(message, extra=extra)

    def log_warning(self, message: str, extra: dict[str, Any] | None = None) -> None:
        self.logger.warning(message, extra=extra)

    def log_error(self, message: str, extra: dict[str, Any] | None = None) -> None:
        self.logger.error(message, extra=extra)

    def log_critical(self, message: str, extra: dict[str, Any] | None = None) -> None:
        self.logger.critical(message, extra=extra)

    def parse(self, response: Response) -> None:
        pass


class SlowSpider(DelaySpider):
    name = "slow"

    async def start(self) -> AsyncIterator[Any]:
        assert self.mockserver
        # 1st response is fast
        url = self.mockserver.url("/delay?n=0&b=0")
        yield Request(url, callback=self.parse, errback=self.errback)

        # 2nd response is slow
        url = self.mockserver.url(f"/delay?n={self.n}&b={self.b}")
        yield Request(url, callback=self.parse, errback=self.errback)

    def parse(self, response: Response) -> Iterator[Any]:
        yield Item()


class SimpleSpider(MetaSpider):
    name = "simple"

    def __init__(self, url: str = "http://localhost:8998", *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.start_urls = [url]

    def parse(self, response: Response) -> Any:
        self.logger.info(f"Got response {response.status}")


class AsyncDefSpider(SimpleSpider):
    name = "asyncdef"

    async def parse(self, response: Response) -> None:
        await defer.succeed(42)
        self.logger.info(f"Got response {response.status}")


class AsyncDefAsyncioSpider(SimpleSpider):
    name = "asyncdef_asyncio"

    async def parse(self, response: Response) -> None:
        await asyncio.sleep(0.2)
        status = await get_from_asyncio_queue(response.status)
        self.logger.info(f"Got response {status}")


class AsyncDefAsyncioReturnSpider(SimpleSpider):
    name = "asyncdef_asyncio_return"

    async def parse(self, response: Response) -> Any:
        await asyncio.sleep(0.2)
        status = await get_from_asyncio_queue(response.status)
        self.logger.info(f"Got response {status}")
        return [{"id": 1}, {"id": 2}]


class AsyncDefAsyncioReturnSingleElementSpider(SimpleSpider):
    name = "asyncdef_asyncio_return_single_element"

    async def parse(self, response: Response) -> Any:
        await asyncio.sleep(0.1)
        status = await get_from_asyncio_queue(response.status)
        self.logger.info(f"Got response {status}")
        return {"foo": 42}


class AsyncDefAsyncioReqsReturnSpider(SimpleSpider):
    name = "asyncdef_asyncio_reqs_return"

    async def parse(self, response: Response) -> Any:
        await asyncio.sleep(0.2)
        req_id = response.meta.get("req_id", 0)
        status = await get_from_asyncio_queue(response.status)
        self.logger.info(f"Got response {status}, req_id {req_id}")
        if req_id > 0:
            return None
        reqs = []
        for i in range(1, 3):
            req = Request(self.start_urls[0], dont_filter=True, meta={"req_id": i})
            reqs.append(req)
        return reqs


class AsyncDefAsyncioGenExcSpider(SimpleSpider):
    name = "asyncdef_asyncio_gen_exc"

    async def parse(self, response: Response) -> AsyncIterator[Any]:
        for i in range(10):
            await asyncio.sleep(0.1)
            yield {"foo": i}
            if i > 5:
                raise ValueError("Stopping the processing")


class AsyncDefDeferredDirectSpider(SimpleSpider):
    name = "asyncdef_deferred_direct"

    async def parse(self, response: Response) -> AsyncIterator[Any]:
        await defer.succeed(None)
        yield {"code": 200}


class AsyncDefDeferredWrappedSpider(SimpleSpider):
    name = "asyncdef_deferred_wrapped"

    async def parse(self, response: Response) -> AsyncIterator[Any]:
        await deferred_to_future(defer.succeed(None))
        yield {"code": 200}


class AsyncDefDeferredMaybeWrappedSpider(SimpleSpider):
    name = "asyncdef_deferred_maybe_wrapped"

    async def parse(self, response: Response) -> AsyncIterator[Any]:
        await maybe_deferred_to_future(defer.succeed(None))
        yield {"code": 200}


class AsyncDefAsyncioGenSpider(SimpleSpider):
    name = "asyncdef_asyncio_gen"

    async def parse(self, response: Response) -> AsyncIterator[Any]:
        await asyncio.sleep(0.2)
        yield {"foo": 42}
        self.logger.info(f"Got response {response.status}")


class AsyncDefAsyncioGenLoopSpider(SimpleSpider):
    name = "asyncdef_asyncio_gen_loop"

    async def parse(self, response: Response) -> AsyncIterator[Any]:
        for i in range(10):
            await asyncio.sleep(0.1)
            yield {"foo": i}
        self.logger.info(f"Got response {response.status}")


class AsyncDefAsyncioGenComplexSpider(SimpleSpider):
    name = "asyncdef_asyncio_gen_complex"
    initial_reqs = 4
    following_reqs = 3
    depth = 2

    def _get_req(self, index: int, cb: CallbackT | None = None) -> Request:
        assert self.mockserver
        return Request(
            self.mockserver.url(f"/status?n=200&request={index}"),
            meta={"index": index},
            dont_filter=True,
            callback=cb,
        )

    async def start(self) -> AsyncIterator[Any]:
        for i in range(1, self.initial_reqs + 1):
            yield self._get_req(i)

    async def parse(self, response: Response) -> AsyncIterator[Any]:
        index = response.meta["index"]
        yield {"index": index}
        if index < 10**self.depth:
            for new_index in range(10 * index, 10 * index + self.following_reqs):
                yield self._get_req(new_index)
        yield self._get_req(index, cb=self.parse2)
        await asyncio.sleep(0.1)
        yield {"index": index + 5}

    async def parse2(self, response: Response) -> AsyncIterator[Any]:
        await asyncio.sleep(0.1)
        yield {"index2": response.meta["index"]}


class ItemSpider(FollowAllSpider):
    name = "item"

    def parse(self, response: Response) -> Iterator[Any]:
        for request in super().parse(response):
            yield request
            yield Item()
            yield {}


class MaxItemsAndRequestsSpider(FollowAllSpider):
    def __init__(
        self,
        max_items: int = 10,
        max_requests: int = 10,
        *args: Any,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        self.max_items = max_items
        self.max_requests = max_requests

    def parse(self, response: Response) -> Iterator[Any]:
        self.items_scraped = 0
        self.pages_crawled = 1  # account for the start url
        for request in super().parse(response):
            if self.pages_crawled < self.max_requests:
                yield request
                self.pages_crawled += 1
            if self.items_scraped < self.max_items:
                yield Item()
                self.items_scraped += 1


class DefaultError(Exception):
    pass


class ErrorSpider(FollowAllSpider):
    name = "error"
    exception_cls: type[Exception] = DefaultError

    def raise_exception(self) -> None:
        raise self.exception_cls("Expected exception")

    def parse(self, response: Response) -> Iterator[Any]:
        for request in super().parse(response):
            yield request
            self.raise_exception()


class BrokenStartSpider(FollowAllSpider):
    fail_before_yield = False
    fail_yielding = False

    def __init__(self, *a: Any, **kw: Any):
        super().__init__(*a, **kw)
        self.seedsseen: list[Any] = []

    async def start(self) -> AsyncIterator[Any]:
        if self.fail_before_yield:
            1 / 0

        assert self.mockserver
        for s in range(100):
            qargs = {"total": 10, "seed": s}
            url = self.mockserver.url(f"/follow?{urlencode(qargs, doseq=True)}")
            yield Request(url, meta={"seed": s})
            if self.fail_yielding:
                2 / 0

        assert self.seedsseen, "All seeds consumed before any download happened"

    def parse(self, response: Response) -> Iterator[Any]:
        self.seedsseen.append(response.meta.get("seed"))
        yield from super().parse(response)


class StartItemSpider(FollowAllSpider):
    async def start(self) -> AsyncIterator[Any]:
        yield {"name": "test item"}


class StartGoodAndBadOutput(FollowAllSpider):
    async def start(self) -> AsyncIterator[Any]:
        yield {"a": "a"}
        yield Request("data:,a")
        yield "data:,b"
        yield object()


class SingleRequestSpider(MetaSpider):
    seed: Request | str | None = None
    callback_func: Callable[[Response], Any] | None = None
    errback_func: Callable[[Failure], Any] | None = None

    async def start(self) -> AsyncIterator[Any]:
        if isinstance(self.seed, Request):
            yield self.seed.replace(callback=self.parse, errback=self.on_error)
        else:
            assert self.seed
            yield Request(self.seed, callback=self.parse, errback=self.on_error)

    def parse(self, response: Response) -> Any:
        self.meta.setdefault("responses", []).append(response)
        if callable(self.callback_func):
            return self.callback_func(response)
        if "next" in response.meta:
            return response.meta["next"]
        return None

    def on_error(self, failure: Failure) -> Any:
        self.meta["failure"] = failure
        if callable(self.errback_func):
            return self.errback_func(failure)
        return None


class DuplicateStartSpider(MockServerSpider):
    dont_filter = True
    name = "duplicatestartrequests"
    distinct_urls = 2
    dupe_factor = 3

    async def start(self) -> AsyncIterator[Any]:
        assert self.mockserver
        for i in range(self.distinct_urls):
            for _ in range(self.dupe_factor):
                url = self.mockserver.url(f"/echo?headers=1&body=test{i}")
                yield Request(url, dont_filter=self.dont_filter)

    def __init__(self, url: str = "http://localhost:8998", *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.visited = 0

    def parse(self, response: Response) -> None:
        self.visited += 1


class CrawlSpiderWithParseMethod(MockServerSpider, CrawlSpider):
    """
    A CrawlSpider which overrides the 'parse' method
    """

    name = "crawl_spider_with_parse_method"
    custom_settings: dict[str, Any] = {
        "RETRY_HTTP_CODES": [],  # no need to retry
    }
    rules = (Rule(LinkExtractor(), callback="parse", follow=True),)

    async def start(self) -> AsyncIterator[Any]:
        test_body = b"""
        <html>
            <head><title>Page title</title></head>
            <body>
                <p><a href="/status?n=200">Item 200</a></p>  <!-- callback -->
                <p><a href="/status?n=201">Item 201</a></p>  <!-- callback -->
            </body>
        </html>
        """
        assert self.mockserver
        url = self.mockserver.url("/alpayload")
        yield Request(url, method="POST", body=test_body)

    def parse(self, response: Response, foo: str | None = None) -> Iterator[Any]:
        self.logger.info("[parse] status %i (foo: %s)", response.status, foo)
        assert self.mockserver
        yield Request(
            self.mockserver.url("/status?n=202"), self.parse, cb_kwargs={"foo": "bar"}
        )


class CrawlSpiderWithAsyncCallback(CrawlSpiderWithParseMethod):
    """A CrawlSpider with an async def callback"""

    name = "crawl_spider_with_async_callback"
    rules = (Rule(LinkExtractor(), callback="parse_async", follow=True),)

    async def parse_async(self, response: Response, foo: str | None = None) -> Request:
        self.logger.info("[parse_async] status %i (foo: %s)", response.status, foo)
        assert self.mockserver
        return Request(
            self.mockserver.url("/status?n=202"),
            self.parse_async,
            cb_kwargs={"foo": "bar"},
        )


class CrawlSpiderWithAsyncGeneratorCallback(CrawlSpiderWithParseMethod):
    """A CrawlSpider with an async generator callback"""

    name = "crawl_spider_with_async_generator_callback"
    rules = (Rule(LinkExtractor(), callback="parse_async_gen", follow=True),)

    async def parse_async_gen(
        self, response: Response, foo: str | None = None
    ) -> AsyncIterator[Any]:
        self.logger.info("[parse_async_gen] status %i (foo: %s)", response.status, foo)
        assert self.mockserver
        yield Request(
            self.mockserver.url("/status?n=202"),
            self.parse_async_gen,
            cb_kwargs={"foo": "bar"},
        )


class CrawlSpiderWithErrback(CrawlSpiderWithParseMethod):
    name = "crawl_spider_with_errback"
    rules = (Rule(LinkExtractor(), callback="parse", errback="errback", follow=True),)

    async def start(self) -> AsyncIterator[Any]:
        test_body = b"""
        <html>
            <head><title>Page title</title></head>
            <body>
                <p><a href="/status?n=200">Item 200</a></p>  <!-- callback -->
                <p><a href="/status?n=201">Item 201</a></p>  <!-- callback -->
                <p><a href="/status?n=404">Item 404</a></p>  <!-- errback -->
                <p><a href="/status?n=500">Item 500</a></p>  <!-- errback -->
                <p><a href="/status?n=501">Item 501</a></p>  <!-- errback -->
            </body>
        </html>
        """
        assert self.mockserver
        url = self.mockserver.url("/alpayload")
        yield Request(url, method="POST", body=test_body)

    def errback(self, failure: Failure) -> None:
        assert isinstance(failure.value, HttpError)
        self.logger.info("[errback] status %i", failure.value.response.status)


class CrawlSpiderWithoutErrback(CrawlSpiderWithParseMethod):
    name = "crawl_spider_without_errback"

    async def start(self) -> AsyncIterator[Any]:
        test_body = b"""
        <html>
            <head><title>Page title</title></head>
            <body>
                <p><a href="/status?n=200">Item 200</a></p>  <!-- callback -->
                <p><a href="/status?n=404">Item 404</a></p>  <!-- failure, no errback -->
            </body>
        </html>
        """
        assert self.mockserver
        url = self.mockserver.url("/alpayload")
        yield Request(url, method="POST", body=test_body)


class CrawlSpiderWithProcessRequestCallbackKeywordArguments(CrawlSpiderWithParseMethod):
    name = "crawl_spider_with_process_request_cb_kwargs"
    rules = (
        Rule(
            LinkExtractor(),
            callback="parse",
            follow=True,
            process_request="process_request",
        ),
    )

    def process_request(self, request: Request, response: Response) -> Request:
        request.cb_kwargs["foo"] = "process_request"
        return request


class BytesReceivedCallbackSpider(MetaSpider):
    full_response_length = 2**18

    @classmethod
    def from_crawler(cls, crawler: Crawler, *args: Any, **kwargs: Any) -> Self:
        spider = super().from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider.bytes_received, signals.bytes_received)
        return spider

    async def start(self) -> AsyncIterator[Any]:
        body = b"a" * self.full_response_length
        assert self.mockserver
        url = self.mockserver.url("/alpayload", is_secure=self.is_secure)
        yield Request(url, method="POST", body=body, errback=self.errback)

    def parse(self, response: Response) -> None:
        self.meta["response"] = response

    def errback(self, failure: Failure) -> None:
        self.meta["failure"] = failure

    def bytes_received(self, data: bytes, request: Request, spider: Spider) -> None:
        self.meta["bytes_received"] = data
        raise StopDownload(fail=False)


class BytesReceivedErrbackSpider(BytesReceivedCallbackSpider):
    def bytes_received(self, data: bytes, request: Request, spider: Spider) -> None:
        self.meta["bytes_received"] = data
        raise StopDownload(fail=True)


class HeadersReceivedCallbackSpider(MetaSpider):
    @classmethod
    def from_crawler(cls, crawler: Crawler, *args: Any, **kwargs: Any) -> Self:
        spider = super().from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider.headers_received, signals.headers_received)
        return spider

    async def start(self) -> AsyncIterator[Any]:
        assert self.mockserver
        yield Request(
            self.mockserver.url("/status", is_secure=self.is_secure),
            errback=self.errback,
        )

    def parse(self, response: Response) -> None:
        self.meta["response"] = response

    def errback(self, failure: Failure) -> None:
        self.meta["failure"] = failure

    def headers_received(
        self, headers: Headers, body_length: int, request: Request, spider: Spider
    ) -> None:
        self.meta["headers_received"] = headers
        raise StopDownload(fail=False)


class HeadersReceivedErrbackSpider(HeadersReceivedCallbackSpider):
    def headers_received(
        self, headers: Headers, body_length: int, request: Request, spider: Spider
    ) -> None:
        self.meta["headers_received"] = headers
        raise StopDownload(fail=True)


class ExceptionSpider(Spider):
    name = "exception"

    @classmethod
    def from_crawler(cls, crawler: Crawler, *args: Any, **kwargs: Any) -> Self:
        raise ValueError("Exception in from_crawler method")


class NoRequestsSpider(Spider):
    name = "no_request"

    async def start(self) -> AsyncIterator[Any]:
        return
        yield
