from __future__ import annotations

from urllib.parse import urljoin

import pytest
from testfixtures import LogCapture
from twisted.internet import defer
from twisted.trial.unittest import TestCase

from scrapy.core.scheduler import BaseScheduler
from scrapy.http import Request
from scrapy.spiders import Spider
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.request import fingerprint
from scrapy.utils.test import get_crawler
from tests.mockserver import MockServer

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
            fp, request = self.requests.popitem()
            return request
        return None


class SimpleScheduler(MinimalScheduler):
    def open(self, spider: Spider) -> defer.Deferred:
        return defer.succeed("open")

    def close(self, reason: str) -> defer.Deferred:
        return defer.succeed("close")

    def __len__(self) -> int:
        return len(self.requests)


class PathsSpider(Spider):
    name = "paths"

    def __init__(self, mockserver, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_urls = map(mockserver.url, PATHS)

    def parse(self, response):
        return {"path": urlparse_cached(response).path}


class InterfaceCheckMixin:
    def test_scheduler_class(self):
        assert isinstance(self.scheduler, BaseScheduler)
        assert issubclass(self.scheduler.__class__, BaseScheduler)


class TestBaseScheduler(InterfaceCheckMixin):
    def setup_method(self):
        self.scheduler = BaseScheduler()

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
        assert self.scheduler.has_pending_requests

        dequeued = []
        while self.scheduler.has_pending_requests():
            request = self.scheduler.next_request()
            dequeued.append(request.url)
        assert set(dequeued) == set(URLS)
        assert not self.scheduler.has_pending_requests()


class SimpleSchedulerTest(TestCase, InterfaceCheckMixin):
    def setUp(self):
        self.scheduler = SimpleScheduler()

    @defer.inlineCallbacks
    def test_enqueue_dequeue(self):
        open_result = yield self.scheduler.open(Spider("foo"))
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

        close_result = yield self.scheduler.close("")
        assert close_result == "close"


class MinimalSchedulerCrawlTest(TestCase):
    scheduler_cls = MinimalScheduler

    @defer.inlineCallbacks
    def test_crawl(self):
        with MockServer() as mockserver:
            settings = {
                "SCHEDULER": self.scheduler_cls,
            }
            with LogCapture() as log:
                crawler = get_crawler(PathsSpider, settings)
                yield crawler.crawl(mockserver)
            for path in PATHS:
                assert f"{{'path': '{path}'}}" in str(log)
            assert f"'item_scraped_count': {len(PATHS)}" in str(log)


class SimpleSchedulerCrawlTest(MinimalSchedulerCrawlTest):
    scheduler_cls = SimpleScheduler
