from typing import Dict, Optional
from unittest import TestCase

from twisted.internet import defer
from twisted.trial.unittest import TestCase as TwistedTestCase

from scrapy.core.scheduler import BaseScheduler
from scrapy.http import Request
from scrapy.spiders import Spider
from scrapy.utils.request import request_fingerprint


_URLS = ["http://foo.com/a", "http://foo.com/b", "http://foo.com/c"]


class DummyScheduler(BaseScheduler):
    def __init__(self) -> None:
        self.requests: Dict[str, Request] = {}

    def open(self, spider: Spider) -> Optional[defer.Deferred]:
        return defer.succeed("open")

    def close(self, reason: str) -> Optional[defer.Deferred]:
        return defer.succeed("close")

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

    def __len__(self) -> int:
        return len(self.requests)


class BaseSchedulerTest(TestCase):
    def setUp(self):
        self.scheduler = BaseScheduler()

    def test_methods(self):
        self.assertIsNone(self.scheduler.open(Spider("foo")))
        self.assertIsNone(self.scheduler.close("finished"))
        self.assertRaises(NotImplementedError, self.scheduler.has_pending_requests)
        self.assertRaises(NotImplementedError, self.scheduler.enqueue_request, Request("https://example.org"))
        self.assertRaises(NotImplementedError, self.scheduler.next_request)


class DummySchedulerTest(TwistedTestCase):
    def setUp(self):
        self.scheduler = DummyScheduler()

    @defer.inlineCallbacks
    def test_methods(self):
        open_result = yield self.scheduler.open(Spider("foo"))
        self.assertEqual(open_result, "open")
        self.assertFalse(self.scheduler.has_pending_requests())

        for url in _URLS:
            self.assertTrue(self.scheduler.enqueue_request(Request(url)))
            self.assertFalse(self.scheduler.enqueue_request(Request(url)))

        self.assertTrue(self.scheduler.has_pending_requests)
        self.assertEqual(len(self.scheduler), len(_URLS))

        dequeued = []
        while self.scheduler.has_pending_requests():
            request = self.scheduler.next_request()
            dequeued.append(request.url)
        self.assertEqual(set(dequeued), set(_URLS))

        self.assertFalse(self.scheduler.has_pending_requests())
        self.assertEqual(len(self.scheduler), 0)

        close_result = yield self.scheduler.close("")
        self.assertEqual(close_result, "close")
