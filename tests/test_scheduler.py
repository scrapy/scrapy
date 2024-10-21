from __future__ import annotations

import collections
import shutil
import tempfile
import unittest

from twisted.internet import defer
from twisted.trial.unittest import TestCase

from scrapy.core.downloader import Downloader
from scrapy.core.scheduler import Scheduler
from scrapy.crawler import Crawler
from scrapy.http import Request
from scrapy.spiders import Spider
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.misc import load_object
from scrapy.utils.test import get_crawler
from tests.mockserver import MockServer

MockEngine = collections.namedtuple("MockEngine", ["downloader"])
MockSlot = collections.namedtuple("MockSlot", ["active"])


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


class SchedulerHandler:
    priority_queue_cls: str | None = None
    jobdir = None

    def create_scheduler(self):
        self.mock_crawler = MockCrawler(self.priority_queue_cls, self.jobdir)
        self.scheduler = Scheduler.from_crawler(self.mock_crawler)
        self.spider = Spider(name="spider")
        self.scheduler.open(self.spider)

    def close_scheduler(self):
        self.scheduler.close("finished")
        self.mock_crawler.stop()
        self.mock_crawler.engine.downloader.close()

    def setUp(self):
        self.create_scheduler()

    def tearDown(self):
        self.close_scheduler()


_PRIORITIES = [
    ("http://foo.com/a", -2),
    ("http://foo.com/d", 1),
    ("http://foo.com/b", -1),
    ("http://foo.com/c", 0),
    ("http://foo.com/e", 2),
]


_URLS = {"http://foo.com/a", "http://foo.com/b", "http://foo.com/c"}


class BaseSchedulerInMemoryTester(SchedulerHandler):
    def test_length(self):
        self.assertFalse(self.scheduler.has_pending_requests())
        self.assertEqual(len(self.scheduler), 0)

        for url in _URLS:
            self.scheduler.enqueue_request(Request(url))

        self.assertTrue(self.scheduler.has_pending_requests())
        self.assertEqual(len(self.scheduler), len(_URLS))

    def test_dequeue(self):
        for url in _URLS:
            self.scheduler.enqueue_request(Request(url))

        urls = set()
        while self.scheduler.has_pending_requests():
            urls.add(self.scheduler.next_request().url)

        self.assertEqual(urls, _URLS)

    def test_dequeue_priorities(self):
        for url, priority in _PRIORITIES:
            self.scheduler.enqueue_request(Request(url, priority=priority))

        priorities = []
        while self.scheduler.has_pending_requests():
            priorities.append(self.scheduler.next_request().priority)

        self.assertEqual(
            priorities, sorted([x[1] for x in _PRIORITIES], key=lambda x: -x)
        )


class BaseSchedulerOnDiskTester(SchedulerHandler):
    def setUp(self):
        self.jobdir = tempfile.mkdtemp()
        self.create_scheduler()

    def tearDown(self):
        self.close_scheduler()

        shutil.rmtree(self.jobdir)
        self.jobdir = None

    def test_length(self):
        self.assertFalse(self.scheduler.has_pending_requests())
        self.assertEqual(len(self.scheduler), 0)

        for url in _URLS:
            self.scheduler.enqueue_request(Request(url))

        self.close_scheduler()
        self.create_scheduler()

        self.assertTrue(self.scheduler.has_pending_requests())
        self.assertEqual(len(self.scheduler), len(_URLS))

    def test_dequeue(self):
        for url in _URLS:
            self.scheduler.enqueue_request(Request(url))

        self.close_scheduler()
        self.create_scheduler()

        urls = set()
        while self.scheduler.has_pending_requests():
            urls.add(self.scheduler.next_request().url)

        self.assertEqual(urls, _URLS)

    def test_dequeue_priorities(self):
        for url, priority in _PRIORITIES:
            self.scheduler.enqueue_request(Request(url, priority=priority))

        self.close_scheduler()
        self.create_scheduler()

        priorities = []
        while self.scheduler.has_pending_requests():
            priorities.append(self.scheduler.next_request().priority)

        self.assertEqual(
            priorities, sorted([x[1] for x in _PRIORITIES], key=lambda x: -x)
        )


class TestSchedulerInMemory(BaseSchedulerInMemoryTester, unittest.TestCase):
    priority_queue_cls = "scrapy.pqueues.ScrapyPriorityQueue"


class TestSchedulerOnDisk(BaseSchedulerOnDiskTester, unittest.TestCase):
    priority_queue_cls = "scrapy.pqueues.ScrapyPriorityQueue"


_URLS_WITH_SLOTS = [
    ("http://foo.com/a", "a"),
    ("http://foo.com/b", "a"),
    ("http://foo.com/c", "b"),
    ("http://foo.com/d", "b"),
    ("http://foo.com/e", "c"),
    ("http://foo.com/f", "c"),
]


class TestMigration(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _migration(self, tmp_dir):
        prev_scheduler_handler = SchedulerHandler()
        prev_scheduler_handler.priority_queue_cls = "scrapy.pqueues.ScrapyPriorityQueue"
        prev_scheduler_handler.jobdir = tmp_dir

        prev_scheduler_handler.create_scheduler()
        for url in _URLS:
            prev_scheduler_handler.scheduler.enqueue_request(Request(url))
        prev_scheduler_handler.close_scheduler()

        next_scheduler_handler = SchedulerHandler()
        next_scheduler_handler.priority_queue_cls = (
            "scrapy.pqueues.DownloaderAwarePriorityQueue"
        )
        next_scheduler_handler.jobdir = tmp_dir

        next_scheduler_handler.create_scheduler()

    def test_migration(self):
        with self.assertRaises(ValueError):
            self._migration(self.tmpdir)


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
    priority_queue_cls: str | None = "scrapy.pqueues.DownloaderAwarePriorityQueue"
    reopen = False

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
            # pylint: disable=protected-access
            slot = downloader.get_slot_key(request)
            dequeued_slots.append(slot)
            downloader.increment(slot)
            requests.append(request)

        for request in requests:
            # pylint: disable=protected-access
            slot = downloader.get_slot_key(request)
            downloader.decrement(slot)

        self.assertTrue(
            _is_scheduling_fair([s for u, s in _URLS_WITH_SLOTS], dequeued_slots)
        )
        self.assertEqual(sum(len(s.active) for s in downloader.slots.values()), 0)


class TestSchedulerWithDownloaderAwareInMemory(
    DownloaderAwareSchedulerTestMixin, BaseSchedulerInMemoryTester, unittest.TestCase
):
    pass


class TestSchedulerWithDownloaderAwareOnDisk(
    DownloaderAwareSchedulerTestMixin, BaseSchedulerOnDiskTester, unittest.TestCase
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
            self.assertEqual(
                self.crawler.stats.get_value("downloader/response_count"),
                len(start_urls),
            )


class TestIncompatibility(unittest.TestCase):
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
        with self.assertRaises(ValueError):
            self._incompatible()
