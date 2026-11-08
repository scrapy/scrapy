from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Self
from urllib.parse import urljoin

import pytest
from twisted.internet import defer

from scrapy.core.scheduler import BaseScheduler
from scrapy.dupefilters import BaseDupeFilter
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.http import Request
from scrapy.spiders import Spider
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.python import global_object_name
from scrapy.utils.request import fingerprint
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from scrapy.crawler import Crawler
    from tests.mockserver.http import MockServer

PATHS = ["/a", "/b", "/c"]
URLS = [urljoin("https://example.org", p) for p in PATHS]


class MinimalScheduler:
    def __init__(self) -> None:
        self.requests: dict[bytes, Request] = {}

    def has_pending_requests(self) -> bool:
        return bool(self.requests)

    def enqueue_request(self, request: Request) -> bool:
        fp = fingerprint(request)
        if fp not in self.requests:
            self.requests[fp] = request
            return True
        return False

    def next_request(self) -> Request | None:
        if self.has_pending_requests():
            _, request = self.requests.popitem()
            return request
        return None


class SimpleScheduler(MinimalScheduler):
    async def open(self, spider: Spider) -> str:
        return "open"

    async def close(self, reason: str) -> str:
        return "close"

    def __len__(self) -> int:
        return len(self.requests)


class PathsSpider(Spider):
    name = "paths"

    def __init__(self, mockserver, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_urls = [mockserver.url(path) for path in PATHS]

    def parse(self, response):
        return {"path": urlparse_cached(response).path}


class InterfaceCheckMixin:
    scheduler: Any

    def test_scheduler_class(self):
        assert isinstance(self.scheduler, BaseScheduler)
        assert issubclass(self.scheduler.__class__, BaseScheduler)


class TestBaseScheduler(InterfaceCheckMixin):
    def setup_method(self):
        self.scheduler = BaseScheduler()  # type: ignore[abstract]

    def test_methods(self):
        assert self.scheduler.open(Spider("foo")) is None
        assert self.scheduler.close("finished") is None
        with pytest.raises(NotImplementedError):
            self.scheduler.has_pending_requests()
        with pytest.raises(NotImplementedError):
            self.scheduler.enqueue_request(Request("https://example.org"))
        with pytest.raises(NotImplementedError):
            self.scheduler.next_request()


class TestMinimalScheduler(InterfaceCheckMixin):
    def setup_method(self):
        self.scheduler = MinimalScheduler()

    def test_open_close(self):
        with pytest.raises(AttributeError):
            self.scheduler.open(Spider("foo"))
        with pytest.raises(AttributeError):
            self.scheduler.close("finished")

    def test_len(self):
        with pytest.raises(AttributeError):
            self.scheduler.__len__()
        with pytest.raises(TypeError):
            len(self.scheduler)

    def test_enqueue_dequeue(self):
        assert not self.scheduler.has_pending_requests()
        for url in URLS:
            assert self.scheduler.enqueue_request(Request(url))
            assert not self.scheduler.enqueue_request(Request(url))
        assert self.scheduler.has_pending_requests()

        dequeued = []
        while self.scheduler.has_pending_requests():
            request = self.scheduler.next_request()
            dequeued.append(request.url)
        assert set(dequeued) == set(URLS)
        assert not self.scheduler.has_pending_requests()


class TestSimpleScheduler(InterfaceCheckMixin):
    def setup_method(self):
        self.scheduler = SimpleScheduler()

    @coroutine_test
    async def test_enqueue_dequeue(self):
        open_result = await self.scheduler.open(Spider("foo"))
        assert open_result == "open"
        assert not self.scheduler.has_pending_requests()

        for url in URLS:
            assert self.scheduler.enqueue_request(Request(url))
            assert not self.scheduler.enqueue_request(Request(url))

        assert self.scheduler.has_pending_requests()
        assert len(self.scheduler) == len(URLS)

        dequeued = []
        while self.scheduler.has_pending_requests():
            request = self.scheduler.next_request()
            dequeued.append(request.url)
        assert set(dequeued) == set(URLS)

        assert not self.scheduler.has_pending_requests()
        assert len(self.scheduler) == 0

        close_result = await self.scheduler.close("")
        assert close_result == "close"


class TestMinimalSchedulerCrawl:
    scheduler_cls = MinimalScheduler

    @coroutine_test
    async def test_crawl(
        self, caplog: pytest.LogCaptureFixture, mockserver: MockServer
    ) -> None:
        settings = {
            "SCHEDULER": self.scheduler_cls,
        }
        with caplog.at_level(logging.DEBUG):
            crawler = get_crawler(PathsSpider, settings)
            await crawler.crawl_async(mockserver)
        for path in PATHS:
            assert f"{{'path': '{path}'}}" in caplog.text
        assert f"'item_scraped_count': {len(PATHS)}" in caplog.text


class TestSimpleSchedulerCrawl(TestMinimalSchedulerCrawl):
    scheduler_cls = SimpleScheduler


class CallsSpider(DefaultSpider):
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.calls: list[str] = []


class CoroutineScheduler(MinimalScheduler):
    async def open(self, spider: Spider) -> None:
        assert isinstance(spider, CallsSpider)
        self.spider = spider
        spider.calls.append("open")

    async def close(self, reason: str) -> None:
        self.spider.calls.append("close")


class DeferredScheduler(MinimalScheduler):
    def open(self, spider: Spider) -> defer.Deferred[None]:
        assert isinstance(spider, CallsSpider)
        self.spider = spider
        spider.calls.append("open")
        return defer.succeed(None)

    def close(self, reason: str) -> defer.Deferred[None]:
        self.spider.calls.append("close")
        return defer.succeed(None)


class RecordingDupeFilter(BaseDupeFilter):
    def __init__(self, crawler: Crawler):
        self.crawler = crawler

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls(crawler)

    def record(self, call: str) -> None:
        assert isinstance(self.crawler.spider, CallsSpider)
        self.crawler.spider.calls.append(call)


class CoroutineDupeFilter(RecordingDupeFilter):
    async def open(self) -> None:
        self.record("open")

    async def close(self, reason: str) -> None:
        self.record("close")


class DeferredDupeFilter(RecordingDupeFilter):
    def open(self) -> defer.Deferred[None]:
        self.record("open")
        return defer.succeed(None)

    def close(self, reason: str) -> defer.Deferred[None]:
        self.record("close")
        return defer.succeed(None)


class TestOpenClose:
    """Scheduler and dupefilter open() and close() are awaited, and returning
    a Deferred from them is deprecated."""

    @staticmethod
    async def crawl(settings: dict[str, Any]) -> list[str]:
        crawler = get_crawler(CallsSpider, settings)
        await crawler.crawl_async()
        assert isinstance(crawler.spider, CallsSpider)
        return crawler.spider.calls

    @pytest.mark.parametrize(
        "settings",
        [
            {"SCHEDULER": CoroutineScheduler},
            {"DUPEFILTER_CLASS": CoroutineDupeFilter},
        ],
    )
    @coroutine_test
    async def test_coroutine(self, settings: dict[str, Any]) -> None:
        assert await self.crawl(settings) == ["open", "close"]

    @pytest.mark.parametrize(
        ("setting", "cls"),
        [
            ("SCHEDULER", DeferredScheduler),
            ("DUPEFILTER_CLASS", DeferredDupeFilter),
        ],
    )
    @coroutine_test
    async def test_deferred(
        self, setting: str, cls: type[DeferredScheduler | DeferredDupeFilter]
    ) -> None:
        with pytest.warns(ScrapyDeprecationWarning) as record:
            calls = await self.crawl({setting: cls})
        assert calls == ["open", "close"]
        suffix = (
            " returned a Deferred, this is deprecated."
            " Please refactor this function to return a coroutine."
        )
        # The dupefilter methods are named instead of the Scheduler ones that
        # return their result, in every reactor mode.
        assert [
            str(w.message).removesuffix(suffix)
            for w in record
            if str(w.message).endswith(suffix)
        ] == [global_object_name(cls.open), global_object_name(cls.close)]
