from __future__ import annotations

import shutil
import tempfile
from abc import ABC, abstractmethod
from collections import deque
from typing import Any, NamedTuple

import pytest
from twisted.internet import defer
from twisted.trial.unittest import TestCase

from scrapy.core.downloader import Downloader
from scrapy.core.scheduler import BaseScheduler, Scheduler
from scrapy.crawler import Crawler
from scrapy.http import Request
from scrapy.spiders import Spider
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.misc import load_object
from scrapy.utils.test import get_crawler
from tests.mockserver import MockServer


class MemoryScheduler(BaseScheduler):
    paused = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.queue = deque(
            Request(value) if isinstance(value, str) else value
            for value in getattr(self, "queue", [])
        )

    def enqueue_request(self, request: Request) -> bool:
        self.queue.append(request)
        return True

    def has_pending_requests(self) -> bool:
        return self.paused or bool(self.queue)

    def next_request(self) -> Request | None:
        if self.paused:
            return None
        try:
            return self.queue.pop()
        except IndexError:
            return None

    def pause(self) -> None:
        self.paused = True

    def unpause(self) -> None:
        self.paused = False


class MockEngine(NamedTuple):
    downloader: MockDownloader


class MockSlot(NamedTuple):
    active: list[Any]


class MockDownloader:
    def __init__(self):
        self.slots = {}

    def get_slot_key(self, request):
        if Downloader.DOWNLOAD_SLOT in request.meta:
            return request.meta[Downloader.DOWNLOAD_SLOT]

        return urlparse_cached(request).hostname or ""

    def increment(self, slot_key):
        slot = self.slots.setdefault(slot_key, MockSlot(active=[]))
        slot.active.append(1)

    def decrement(self, slot_key):
        slot = self.slots.get(slot_key)
        slot.active.pop()

    def close(self):
        pass


class MockCrawler(Crawler):
    def __init__(self, priority_queue_cls, jobdir):
        settings = {
            "SCHEDULER_DEBUG": False,
            "SCHEDULER_DISK_QUEUE": "scrapy.squeues.PickleLifoDiskQueue",
            "SCHEDULER_MEMORY_QUEUE": "scrapy.squeues.LifoMemoryQueue",
            "SCHEDULER_PRIORITY_QUEUE": priority_queue_cls,
            "JOBDIR": jobdir,
            "DUPEFILTER_CLASS": "scrapy.dupefilters.BaseDupeFilter",
        }
        super().__init__(Spider, settings)
        self.engine = MockEngine(downloader=MockDownloader())
        self.stats = load_object(self.settings["STATS_CLASS"])(self)


class SchedulerHandler(ABC):
    jobdir = None

    @property
    @abstractmethod
    def priority_queue_cls(self) -> str:
        raise NotImplementedError

    def create_scheduler(self):
        self.mock_crawler = MockCrawler(self.priority_queue_cls, self.jobdir)
        self.scheduler = Scheduler.from_crawler(self.mock_crawler)
        self.spider = Spider(name="spider")
        self.scheduler.open(self.spider)

    def close_scheduler(self):
        self.scheduler.close("finished")
        self.mock_crawler.stop()
        self.mock_crawler.engine.downloader.close()

    def setup_method(self):
        self.create_scheduler()

    def teardown_method(self):
        self.close_scheduler()


_PRIORITIES = [
    ("http://foo.com/a", -2),
    ("http://foo.com/d", 1),
    ("http://foo.com/b", -1),
    ("http://foo.com/c", 0),
    ("http://foo.com/e", 2),
]


_URLS = {"http://foo.com/a", "http://foo.com/b", "http://foo.com/c"}


class TestSchedulerInMemoryBase(SchedulerHandler):
    def test_length(self):
        assert not self.scheduler.has_pending_requests()
        assert len(self.scheduler) == 0

        for url in _URLS:
            self.scheduler.enqueue_request(Request(url))

        assert self.scheduler.has_pending_requests()
        assert len(self.scheduler) == len(_URLS)

    def test_dequeue(self):
        for url in _URLS:
            self.scheduler.enqueue_request(Request(url))

        urls = set()
        while self.scheduler.has_pending_requests():
            urls.add(self.scheduler.next_request().url)

        assert urls == _URLS

    def test_dequeue_priorities(self):
        for url, priority in _PRIORITIES:
            self.scheduler.enqueue_request(Request(url, priority=priority))

        priorities = []
        while self.scheduler.has_pending_requests():
            priorities.append(self.scheduler.next_request().priority)

        assert priorities == sorted([x[1] for x in _PRIORITIES], key=lambda x: -x)


class TestSchedulerOnDiskBase(SchedulerHandler):
    def setup_method(self):
        self.jobdir = tempfile.mkdtemp()
        self.create_scheduler()

    def teardown_method(self):
        self.close_scheduler()

        shutil.rmtree(self.jobdir)
        self.jobdir = None

    def test_length(self):
        assert not self.scheduler.has_pending_requests()
        assert len(self.scheduler) == 0

        for url in _URLS:
            self.scheduler.enqueue_request(Request(url))

        self.close_scheduler()
        self.create_scheduler()

        assert self.scheduler.has_pending_requests()
        assert len(self.scheduler) == len(_URLS)

    def test_dequeue(self):
        for url in _URLS:
            self.scheduler.enqueue_request(Request(url))

        self.close_scheduler()
        self.create_scheduler()

        urls = set()
        while self.scheduler.has_pending_requests():
            urls.add(self.scheduler.next_request().url)

        assert urls == _URLS

    def test_dequeue_priorities(self):
        for url, priority in _PRIORITIES:
            self.scheduler.enqueue_request(Request(url, priority=priority))

        self.close_scheduler()
        self.create_scheduler()

        priorities = []
        while self.scheduler.has_pending_requests():
            priorities.append(self.scheduler.next_request().priority)

        assert priorities == sorted([x[1] for x in _PRIORITIES], key=lambda x: -x)


class TestSchedulerInMemory(TestSchedulerInMemoryBase):
    @property
    def priority_queue_cls(self) -> str:
        return "scrapy.pqueues.ScrapyPriorityQueue"


class TestSchedulerOnDisk(TestSchedulerOnDiskBase):
    @property
    def priority_queue_cls(self) -> str:
        return "scrapy.pqueues.ScrapyPriorityQueue"


_URLS_WITH_SLOTS = [
    ("http://foo.com/a", "a"),
    ("http://foo.com/b", "a"),
    ("http://foo.com/c", "b"),
    ("http://foo.com/d", "b"),
    ("http://foo.com/e", "c"),
    ("http://foo.com/f", "c"),
]


class TestMigration:
    def test_migration(self, tmpdir):
        class PrevSchedulerHandler(SchedulerHandler):
            jobdir = tmpdir

            @property
            def priority_queue_cls(self) -> str:
                return "scrapy.pqueues.ScrapyPriorityQueue"

        class NextSchedulerHandler(SchedulerHandler):
            jobdir = tmpdir

            @property
            def priority_queue_cls(self) -> str:
                return "scrapy.pqueues.DownloaderAwarePriorityQueue"

        prev_scheduler_handler = PrevSchedulerHandler()
        prev_scheduler_handler.create_scheduler()
        for url in _URLS:
            prev_scheduler_handler.scheduler.enqueue_request(Request(url))
        prev_scheduler_handler.close_scheduler()

        next_scheduler_handler = NextSchedulerHandler()
        with pytest.raises(
            ValueError,
            match="DownloaderAwarePriorityQueue accepts ``slot_startprios`` as a dict",
        ):
            next_scheduler_handler.create_scheduler()


def _is_scheduling_fair(enqueued_slots, dequeued_slots):
    """
    We enqueued same number of requests for every slot.
    Assert correct order, e.g.

    >>> enqueued = ['a', 'b', 'c'] * 2
    >>> correct = ['a', 'c', 'b', 'b', 'a', 'c']
    >>> incorrect = ['a', 'a', 'b', 'c', 'c', 'b']
    >>> _is_scheduling_fair(enqueued, correct)
    True
    >>> _is_scheduling_fair(enqueued, incorrect)
    False
    """
    if len(dequeued_slots) != len(enqueued_slots):
        return False

    slots_number = len(set(enqueued_slots))
    for i in range(0, len(dequeued_slots), slots_number):
        part = dequeued_slots[i : i + slots_number]
        if len(part) != len(set(part)):
            return False

    return True


class DownloaderAwareSchedulerTestMixin:
    reopen = False

    @property
    def priority_queue_cls(self) -> str:
        return "scrapy.pqueues.DownloaderAwarePriorityQueue"

    def test_logic(self):
        for url, slot in _URLS_WITH_SLOTS:
            request = Request(url)
            request.meta[Downloader.DOWNLOAD_SLOT] = slot
            self.scheduler.enqueue_request(request)

        if self.reopen:
            self.close_scheduler()
            self.create_scheduler()

        dequeued_slots = []
        requests = []
        downloader = self.mock_crawler.engine.downloader
        while self.scheduler.has_pending_requests():
            request = self.scheduler.next_request()
            slot = downloader.get_slot_key(request)
            dequeued_slots.append(slot)
            downloader.increment(slot)
            requests.append(request)

        for request in requests:
            slot = downloader.get_slot_key(request)
            downloader.decrement(slot)

        assert _is_scheduling_fair([s for u, s in _URLS_WITH_SLOTS], dequeued_slots)
        assert sum(len(s.active) for s in downloader.slots.values()) == 0


class TestSchedulerWithDownloaderAwareInMemory(
    DownloaderAwareSchedulerTestMixin, TestSchedulerInMemoryBase
):
    pass


class TestSchedulerWithDownloaderAwareOnDisk(
    DownloaderAwareSchedulerTestMixin, TestSchedulerOnDiskBase
):
    reopen = True


class StartUrlsSpider(Spider):
    def __init__(self, start_urls):
        self.start_urls = start_urls
        super().__init__(name="StartUrlsSpider")

    def parse(self, response):
        pass


class TestIntegrationWithDownloaderAwareInMemory(TestCase):
    def setUp(self):
        self.crawler = get_crawler(
            spidercls=StartUrlsSpider,
            settings_dict={
                "SCHEDULER_PRIORITY_QUEUE": "scrapy.pqueues.DownloaderAwarePriorityQueue",
                "DUPEFILTER_CLASS": "scrapy.dupefilters.BaseDupeFilter",
            },
        )

    @defer.inlineCallbacks
    def tearDown(self):
        yield self.crawler.stop()

    @defer.inlineCallbacks
    def test_integration_downloader_aware_priority_queue(self):
        with MockServer() as mockserver:
            url = mockserver.url("/status?n=200", is_secure=False)
            start_urls = [url] * 6
            yield self.crawler.crawl(start_urls)
            assert self.crawler.stats.get_value("downloader/response_count") == len(
                start_urls
            )


class TestIncompatibility:
    def _incompatible(self):
        settings = {
            "SCHEDULER_PRIORITY_QUEUE": "scrapy.pqueues.DownloaderAwarePriorityQueue",
            "CONCURRENT_REQUESTS_PER_IP": 1,
        }
        crawler = get_crawler(Spider, settings)
        scheduler = Scheduler.from_crawler(crawler)
        spider = Spider(name="spider")
        scheduler.open(spider)

    def test_incompatibility(self):
        with pytest.raises(
            ValueError, match="does not support CONCURRENT_REQUESTS_PER_IP"
        ):
            self._incompatible()
