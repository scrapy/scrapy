from typing import Dict, Optional
from unittest import TestCase
from urllib.parse import urljoin, urlparse

from testfixtures import LogCapture
from twisted.internet import defer
from twisted.trial.unittest import TestCase as TwistedTestCase

from scrapy.core.scheduler import BaseScheduler
from scrapy.crawler import CrawlerRunner
from scrapy.http import Request
from scrapy.spiders import Spider
from scrapy.utils.request import request_fingerprint

from tests.mockserver import MockServer


PATHS = ["/a", "/b", "/c"]
URLS = [urljoin("https://example.org", p) for p in PATHS]


class MinimalScheduler:
    def __init__(self) -> None:
        self.requests: Dict[str, Request] = {}

    def has_pending_requests(self) -> bool:
        return bool(self.requests)

    def enqueue_request(self, request: Request) -> bool:
        fp = request_fingerprint(request)
        if fp not in self.requests:
            self.requests[fp] = request
            return True
        return False

    def next_request(self) -> Optional[Request]:
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


class TestSpider(Spider):
    name = "test"

    def __init__(self, mockserver, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_urls = map(mockserver.url, PATHS)

    def parse(self, response):
        return {"path": urlparse(response.url).path}


class InterfaceCheckMixin:
    def test_scheduler_class(self):
        self.assertTrue(isinstance(self.scheduler, BaseScheduler))
        self.assertTrue(issubclass(self.scheduler.__class__, BaseScheduler))


class BaseSchedulerTest(TestCase, InterfaceCheckMixin):
    def setUp(self):
        self.scheduler = BaseScheduler()

    def test_methods(self):
        self.assertIsNone(self.scheduler.open(Spider("foo")))
        self.assertIsNone(self.scheduler.close("finished"))
        self.assertRaises(NotImplementedError, self.scheduler.has_pending_requests)
        self.assertRaises(NotImplementedError, self.scheduler.enqueue_request, Request("https://example.org"))
        self.assertRaises(NotImplementedError, self.scheduler.next_request)


class MinimalSchedulerTest(TestCase, InterfaceCheckMixin):
    def setUp(self):
        self.scheduler = MinimalScheduler()

    def test_open_close(self):
        with self.assertRaises(AttributeError):
            self.scheduler.open(Spider("foo"))
        with self.assertRaises(AttributeError):
            self.scheduler.close("finished")

    def test_len(self):
        with self.assertRaises(AttributeError):
            self.scheduler.__len__()
        with self.assertRaises(TypeError):
            len(self.scheduler)

    def test_enqueue_dequeue(self):
        self.assertFalse(self.scheduler.has_pending_requests())
        for url in URLS:
            self.assertTrue(self.scheduler.enqueue_request(Request(url)))
            self.assertFalse(self.scheduler.enqueue_request(Request(url)))
        self.assertTrue(self.scheduler.has_pending_requests)

        dequeued = []
        while self.scheduler.has_pending_requests():
            request = self.scheduler.next_request()
            dequeued.append(request.url)
        self.assertEqual(set(dequeued), set(URLS))
        self.assertFalse(self.scheduler.has_pending_requests())


class SimpleSchedulerTest(TwistedTestCase, InterfaceCheckMixin):
    def setUp(self):
        self.scheduler = SimpleScheduler()

    @defer.inlineCallbacks
    def test_enqueue_dequeue(self):
        open_result = yield self.scheduler.open(Spider("foo"))
        self.assertEqual(open_result, "open")
        self.assertFalse(self.scheduler.has_pending_requests())

        for url in URLS:
            self.assertTrue(self.scheduler.enqueue_request(Request(url)))
            self.assertFalse(self.scheduler.enqueue_request(Request(url)))

        self.assertTrue(self.scheduler.has_pending_requests())
        self.assertEqual(len(self.scheduler), len(URLS))

        dequeued = []
        while self.scheduler.has_pending_requests():
            request = self.scheduler.next_request()
            dequeued.append(request.url)
        self.assertEqual(set(dequeued), set(URLS))

        self.assertFalse(self.scheduler.has_pending_requests())
        self.assertEqual(len(self.scheduler), 0)

        close_result = yield self.scheduler.close("")
        self.assertEqual(close_result, "close")


class MinimalSchedulerCrawlTest(TwistedTestCase):
    scheduler_cls = MinimalScheduler

    @defer.inlineCallbacks
    def test_crawl(self):
        with MockServer() as mockserver:
            settings = {"SCHEDULER": self.scheduler_cls}
            with LogCapture() as log:
                yield CrawlerRunner(settings).crawl(TestSpider, mockserver)
            for path in PATHS:
                self.assertIn(f"{{'path': '{path}'}}", str(log))
            self.assertIn(f"'item_scraped_count': {len(PATHS)}", str(log))


class SimpleSchedulerCrawlTest(MinimalSchedulerCrawlTest):
    scheduler_cls = SimpleScheduler
