"""
Some spiders used for testing and benchmarking
"""

from __future__ import annotations

import asyncio
import time
from urllib.parse import urlencode

from twisted.internet import defer

from scrapy import signals
from scrapy.exceptions import StopDownload
from scrapy.http import Request
from scrapy.item import Item
from scrapy.linkextractors import LinkExtractor
from scrapy.spiders import Spider
from scrapy.spiders.crawl import CrawlSpider, Rule
from scrapy.utils.defer import deferred_to_future, maybe_deferred_to_future
from scrapy.utils.test import get_from_asyncio_queue, get_web_client_agent_req


class MockServerSpider(Spider):
    def __init__(self, mockserver=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mockserver = mockserver


class MetaSpider(MockServerSpider):
    name = "meta"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.meta = {}

    def closed(self, reason):
        self.meta["close_reason"] = reason


class FollowAllSpider(MetaSpider):
    name = "follow"
    link_extractor = LinkExtractor()

    def __init__(
        self, total=10, show=20, order="rand", maxlatency=0.0, *args, **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.urls_visited = []
        self.times = []
        qargs = {"total": total, "show": show, "order": order, "maxlatency": maxlatency}
        url = self.mockserver.url(f"/follow?{urlencode(qargs, doseq=True)}")
        self.start_urls = [url]

    def parse(self, response):
        self.urls_visited.append(response.url)
        self.times.append(time.time())
        for link in self.link_extractor.extract_links(response):
            yield Request(link.url, callback=self.parse)


class DelaySpider(MetaSpider):
    name = "delay"

    def __init__(self, n=1, b=0, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.n = n
        self.b = b
        self.t1 = self.t2 = self.t2_err = 0

    def start_requests(self):
        self.t1 = time.time()
        url = self.mockserver.url(f"/delay?n={self.n}&b={self.b}")
        yield Request(url, callback=self.parse, errback=self.errback)

    def parse(self, response):
        self.t2 = time.time()

    def errback(self, failure):
        self.t2_err = time.time()


class LogSpider(MetaSpider):
    name = "log_spider"

    def log_debug(self, message: str, extra: dict | None = None):
        self.logger.debug(message, extra=extra)

    def log_info(self, message: str, extra: dict | None = None):
        self.logger.info(message, extra=extra)

    def log_warning(self, message: str, extra: dict | None = None):
        self.logger.warning(message, extra=extra)

    def log_error(self, message: str, extra: dict | None = None):
        self.logger.error(message, extra=extra)

    def log_critical(self, message: str, extra: dict | None = None):
        self.logger.critical(message, extra=extra)

    def parse(self, response):
        pass


class SlowSpider(DelaySpider):
    name = "slow"

    def start_requests(self):
        # 1st response is fast
        url = self.mockserver.url("/delay?n=0&b=0")
        yield Request(url, callback=self.parse, errback=self.errback)

        # 2nd response is slow
        url = self.mockserver.url(f"/delay?n={self.n}&b={self.b}")
        yield Request(url, callback=self.parse, errback=self.errback)

    def parse(self, response):
        yield Item()


class SimpleSpider(MetaSpider):
    name = "simple"

    def __init__(self, url="http://localhost:8998", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_urls = [url]

    def parse(self, response):
        self.logger.info(f"Got response {response.status}")


class AsyncDefSpider(SimpleSpider):
    name = "asyncdef"

    async def parse(self, response):
        await defer.succeed(42)
        self.logger.info(f"Got response {response.status}")


class AsyncDefAsyncioSpider(SimpleSpider):
    name = "asyncdef_asyncio"

    async def parse(self, response):
        await asyncio.sleep(0.2)
        status = await get_from_asyncio_queue(response.status)
        self.logger.info(f"Got response {status}")


class AsyncDefAsyncioReturnSpider(SimpleSpider):
    name = "asyncdef_asyncio_return"

    async def parse(self, response):
        await asyncio.sleep(0.2)
        status = await get_from_asyncio_queue(response.status)
        self.logger.info(f"Got response {status}")
        return [{"id": 1}, {"id": 2}]


class AsyncDefAsyncioReturnSingleElementSpider(SimpleSpider):
    name = "asyncdef_asyncio_return_single_element"

    async def parse(self, response):
        await asyncio.sleep(0.1)
        status = await get_from_asyncio_queue(response.status)
        self.logger.info(f"Got response {status}")
        return {"foo": 42}


class AsyncDefAsyncioReqsReturnSpider(SimpleSpider):
    name = "asyncdef_asyncio_reqs_return"

    async def parse(self, response):
        await asyncio.sleep(0.2)
        req_id = response.meta.get("req_id", 0)
        status = await get_from_asyncio_queue(response.status)
        self.logger.info(f"Got response {status}, req_id {req_id}")
        if req_id > 0:
            return
        reqs = []
        for i in range(1, 3):
            req = Request(self.start_urls[0], dont_filter=True, meta={"req_id": i})
            reqs.append(req)
        return reqs


class AsyncDefAsyncioGenExcSpider(SimpleSpider):
    name = "asyncdef_asyncio_gen_exc"

    async def parse(self, response):
        for i in range(10):
            await asyncio.sleep(0.1)
            yield {"foo": i}
            if i > 5:
                raise ValueError("Stopping the processing")


class AsyncDefDeferredDirectSpider(SimpleSpider):
    name = "asyncdef_deferred_direct"

    async def parse(self, response):
        resp = await get_web_client_agent_req(self.mockserver.url("/status?n=200"))
        yield {"code": resp.code}


class AsyncDefDeferredWrappedSpider(SimpleSpider):
    name = "asyncdef_deferred_wrapped"

    async def parse(self, response):
        resp = await deferred_to_future(
            get_web_client_agent_req(self.mockserver.url("/status?n=200"))
        )
        yield {"code": resp.code}


class AsyncDefDeferredMaybeWrappedSpider(SimpleSpider):
    name = "asyncdef_deferred_wrapped"

    async def parse(self, response):
        resp = await maybe_deferred_to_future(
            get_web_client_agent_req(self.mockserver.url("/status?n=200"))
        )
        yield {"code": resp.code}


class AsyncDefAsyncioGenSpider(SimpleSpider):
    name = "asyncdef_asyncio_gen"

    async def parse(self, response):
        await asyncio.sleep(0.2)
        yield {"foo": 42}
        self.logger.info(f"Got response {response.status}")


class AsyncDefAsyncioGenLoopSpider(SimpleSpider):
    name = "asyncdef_asyncio_gen_loop"

    async def parse(self, response):
        for i in range(10):
            await asyncio.sleep(0.1)
            yield {"foo": i}
        self.logger.info(f"Got response {response.status}")


class AsyncDefAsyncioGenComplexSpider(SimpleSpider):
    name = "asyncdef_asyncio_gen_complex"
    initial_reqs = 4
    following_reqs = 3
    depth = 2

    def _get_req(self, index, cb=None):
        return Request(
            self.mockserver.url(f"/status?n=200&request={index}"),
            meta={"index": index},
            dont_filter=True,
            callback=cb,
        )

    def start_requests(self):
        for i in range(1, self.initial_reqs + 1):
            yield self._get_req(i)

    async def parse(self, response):
        index = response.meta["index"]
        yield {"index": index}
        if index < 10**self.depth:
            for new_index in range(10 * index, 10 * index + self.following_reqs):
                yield self._get_req(new_index)
        yield self._get_req(index, cb=self.parse2)
        await asyncio.sleep(0.1)
        yield {"index": index + 5}

    async def parse2(self, response):
        await asyncio.sleep(0.1)
        yield {"index2": response.meta["index"]}


class ItemSpider(FollowAllSpider):
    name = "item"

    def parse(self, response):
        for request in super().parse(response):
            yield request
            yield Item()
            yield {}


class MaxItemsAndRequestsSpider(FollowAllSpider):
    def __init__(self, max_items=10, max_requests=10, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.max_items = max_items
        self.max_requests = max_requests

    def parse(self, response):
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
    exception_cls = DefaultError

    def raise_exception(self):
        raise self.exception_cls("Expected exception")

    def parse(self, response):
        for request in super().parse(response):
            yield request
            self.raise_exception()


class BrokenStartRequestsSpider(FollowAllSpider):
    fail_before_yield = False
    fail_yielding = False

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.seedsseen = []

    def start_requests(self):
        if self.fail_before_yield:
            1 / 0

        for s in range(100):
            qargs = {"total": 10, "seed": s}
            url = self.mockserver.url(f"/follow?{urlencode(qargs, doseq=True)}")
            yield Request(url, meta={"seed": s})
            if self.fail_yielding:
                2 / 0

        assert (
            self.seedsseen
        ), "All start requests consumed before any download happened"

    def parse(self, response):
        self.seedsseen.append(response.meta.get("seed"))
        yield from super().parse(response)


class StartRequestsItemSpider(FollowAllSpider):
    def start_requests(self):
        yield {"name": "test item"}


class StartRequestsGoodAndBadOutput(FollowAllSpider):
    def start_requests(self):
        yield {"a": "a"}
        yield Request("data:,a")
        yield "data:,b"
        yield object()


class SingleRequestSpider(MetaSpider):
    seed = None
    callback_func = None
    errback_func = None

    def start_requests(self):
        if isinstance(self.seed, Request):
            yield self.seed.replace(callback=self.parse, errback=self.on_error)
        else:
            yield Request(self.seed, callback=self.parse, errback=self.on_error)

    def parse(self, response):
        self.meta.setdefault("responses", []).append(response)
        if callable(self.callback_func):
            return self.callback_func(response)
        if "next" in response.meta:
            return response.meta["next"]
        return None

    def on_error(self, failure):
        self.meta["failure"] = failure
        if callable(self.errback_func):
            return self.errback_func(failure)
        return None


class DuplicateStartRequestsSpider(MockServerSpider):
    dont_filter = True
    name = "duplicatestartrequests"
    distinct_urls = 2
    dupe_factor = 3

    def start_requests(self):
        for i in range(0, self.distinct_urls):
            for j in range(0, self.dupe_factor):
                url = self.mockserver.url(f"/echo?headers=1&body=test{i}")
                yield Request(url, dont_filter=self.dont_filter)

    def __init__(self, url="http://localhost:8998", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.visited = 0

    def parse(self, response):
        self.visited += 1


class CrawlSpiderWithParseMethod(MockServerSpider, CrawlSpider):
    """
    A CrawlSpider which overrides the 'parse' method
    """

    name = "crawl_spider_with_parse_method"
    custom_settings: dict = {
        "RETRY_HTTP_CODES": [],  # no need to retry
    }
    rules = (Rule(LinkExtractor(), callback="parse", follow=True),)

    def start_requests(self):
        test_body = b"""
        <html>
            <head><title>Page title<title></head>
            <body>
                <p><a href="/status?n=200">Item 200</a></p>  <!-- callback -->
                <p><a href="/status?n=201">Item 201</a></p>  <!-- callback -->
            </body>
        </html>
        """
        url = self.mockserver.url("/alpayload")
        yield Request(url, method="POST", body=test_body)

    def parse(self, response, foo=None):
        self.logger.info("[parse] status %i (foo: %s)", response.status, foo)
        yield Request(
            self.mockserver.url("/status?n=202"), self.parse, cb_kwargs={"foo": "bar"}
        )


class CrawlSpiderWithAsyncCallback(CrawlSpiderWithParseMethod):
    """A CrawlSpider with an async def callback"""

    name = "crawl_spider_with_async_callback"
    rules = (Rule(LinkExtractor(), callback="parse_async", follow=True),)

    async def parse_async(self, response, foo=None):
        self.logger.info("[parse_async] status %i (foo: %s)", response.status, foo)
        return Request(
            self.mockserver.url("/status?n=202"),
            self.parse_async,
            cb_kwargs={"foo": "bar"},
        )


class CrawlSpiderWithAsyncGeneratorCallback(CrawlSpiderWithParseMethod):
    """A CrawlSpider with an async generator callback"""

    name = "crawl_spider_with_async_generator_callback"
    rules = (Rule(LinkExtractor(), callback="parse_async_gen", follow=True),)

    async def parse_async_gen(self, response, foo=None):
        self.logger.info("[parse_async_gen] status %i (foo: %s)", response.status, foo)
        yield Request(
            self.mockserver.url("/status?n=202"),
            self.parse_async_gen,
            cb_kwargs={"foo": "bar"},
        )


class CrawlSpiderWithErrback(CrawlSpiderWithParseMethod):
    name = "crawl_spider_with_errback"
    rules = (Rule(LinkExtractor(), callback="parse", errback="errback", follow=True),)

    def start_requests(self):
        test_body = b"""
        <html>
            <head><title>Page title<title></head>
            <body>
                <p><a href="/status?n=200">Item 200</a></p>  <!-- callback -->
                <p><a href="/status?n=201">Item 201</a></p>  <!-- callback -->
                <p><a href="/status?n=404">Item 404</a></p>  <!-- errback -->
                <p><a href="/status?n=500">Item 500</a></p>  <!-- errback -->
                <p><a href="/status?n=501">Item 501</a></p>  <!-- errback -->
            </body>
        </html>
        """
        url = self.mockserver.url("/alpayload")
        yield Request(url, method="POST", body=test_body)

    def errback(self, failure):
        self.logger.info("[errback] status %i", failure.value.response.status)


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

    def process_request(self, request, response):
        request.cb_kwargs["foo"] = "process_request"
        return request


class BytesReceivedCallbackSpider(MetaSpider):
    full_response_length = 2**18

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider.bytes_received, signals.bytes_received)
        return spider

    def start_requests(self):
        body = b"a" * self.full_response_length
        url = self.mockserver.url("/alpayload")
        yield Request(url, method="POST", body=body, errback=self.errback)

    def parse(self, response):
        self.meta["response"] = response

    def errback(self, failure):
        self.meta["failure"] = failure

    def bytes_received(self, data, request, spider):
        self.meta["bytes_received"] = data
        raise StopDownload(fail=False)


class BytesReceivedErrbackSpider(BytesReceivedCallbackSpider):
    def bytes_received(self, data, request, spider):
        self.meta["bytes_received"] = data
        raise StopDownload(fail=True)


class HeadersReceivedCallbackSpider(MetaSpider):
    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider.headers_received, signals.headers_received)
        return spider

    def start_requests(self):
        yield Request(self.mockserver.url("/status"), errback=self.errback)

    def parse(self, response):
        self.meta["response"] = response

    def errback(self, failure):
        self.meta["failure"] = failure

    def headers_received(self, headers, body_length, request, spider):
        self.meta["headers_received"] = headers
        raise StopDownload(fail=False)


class HeadersReceivedErrbackSpider(HeadersReceivedCallbackSpider):
    def headers_received(self, headers, body_length, request, spider):
        self.meta["headers_received"] = headers
        raise StopDownload(fail=True)
