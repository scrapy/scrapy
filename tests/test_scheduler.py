from __future__ import annotations

import logging
import warnings
from abc import ABC, abstractmethod
from collections import deque
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import TYPE_CHECKING, Any, NamedTuple, cast
from unittest.mock import Mock

import pytest

from scrapy.core.downloader import Downloader
from scrapy.core.scheduler import BaseScheduler, Scheduler, ThrottlerAwareScheduler
from scrapy.crawler import Crawler
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.http import Request
from scrapy.spiders import Spider
from scrapy.utils.defer import ensure_awaitable
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.misc import load_object
from scrapy.utils.test import get_crawler
from tests.mockserver.http import MockServer
from tests.utils.decorators import coroutine_test, inline_callbacks_test

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from pathlib import Path

    from scrapy.http.request import CallbackT


class MemoryScheduler(BaseScheduler):
    paused = False

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.queue: deque[Request] = deque(
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


class MockSlot(NamedTuple):
    active: list[Any]


class MockDownloader:
    def __init__(self) -> None:
        self.slots: dict[str, MockSlot] = {}

    def get_slot_key(self, request: Request) -> str:
        if Downloader.DOWNLOAD_SLOT in request.meta:
            return cast("str", request.meta[Downloader.DOWNLOAD_SLOT])

        return urlparse_cached(request).hostname or ""

    def increment(self, slot_key: str) -> None:
        slot = self.slots.setdefault(slot_key, MockSlot(active=[]))
        slot.active.append(1)

    def decrement(self, slot_key: str) -> None:
        slot = self.slots[slot_key]
        slot.active.pop()

    def close(self) -> None:
        pass


class MockCrawler(Crawler):
    def __init__(self, priority_queue_cls: str, jobdir: Path | None):
        settings = {
            "SCHEDULER_DEBUG": False,
            "SCHEDULER_DISK_QUEUE": "scrapy.squeues.PickleLifoDiskQueue",
            "SCHEDULER_MEMORY_QUEUE": "scrapy.squeues.LifoMemoryQueue",
            "SCHEDULER_PRIORITY_QUEUE": priority_queue_cls,
            "JOBDIR": str(jobdir) if jobdir is not None else None,
            "DUPEFILTER_CLASS": "scrapy.dupefilters.BaseDupeFilter",
        }
        super().__init__(Spider, settings)
        self.engine = Mock(downloader=MockDownloader())
        self.stats = load_object(self.settings["STATS_CLASS"])(self)


@asynccontextmanager
async def create_scheduler(
    priority_queue_cls: str, jobdir: Path | None
) -> AsyncGenerator[Scheduler]:
    mock_crawler = MockCrawler(priority_queue_cls, jobdir)
    scheduler = Scheduler.from_crawler(mock_crawler)
    spider = Spider(name="spider")
    await ensure_awaitable(scheduler.open(spider))
    try:
        yield scheduler
    finally:
        await ensure_awaitable(scheduler.close("finished"))
        await mock_crawler.stop_async()
        assert mock_crawler.engine
        mock_crawler.engine.downloader.close()


_PRIORITIES = [
    ("http://foo.com/a", -2),
    ("http://foo.com/d", 1),
    ("http://foo.com/b", -1),
    ("http://foo.com/c", 0),
    ("http://foo.com/e", 2),
]


_URLS = {"http://foo.com/a", "http://foo.com/b", "http://foo.com/c"}


class TestSchedulerBase(ABC):
    @property
    @abstractmethod
    def priority_queue_cls(self) -> str:
        raise NotImplementedError

    @pytest.fixture
    def jobdir(self) -> Path | None:
        return None

    def create_scheduler(
        self, jobdir: Path | None
    ) -> AbstractAsyncContextManager[Scheduler]:
        return create_scheduler(self.priority_queue_cls, jobdir)

    # TODO: unify test methods using "reopen" like in DownloaderAwareSchedulerTestMixin


class TestSchedulerInMemoryBase(TestSchedulerBase):
    @coroutine_test
    async def test_length(self, jobdir: Path | None) -> None:
        async with self.create_scheduler(jobdir) as scheduler:
            assert not scheduler.has_pending_requests()
            assert len(scheduler) == 0

            for url in _URLS:
                scheduler.enqueue_request(Request(url))

            assert scheduler.has_pending_requests()
            assert len(scheduler) == len(_URLS)

    @coroutine_test
    async def test_dequeue(self, jobdir: Path | None) -> None:
        async with self.create_scheduler(jobdir) as scheduler:
            for url in _URLS:
                scheduler.enqueue_request(Request(url))

            urls = set()
            while scheduler.has_pending_requests():
                request = scheduler.next_request()
                assert request is not None
                urls.add(request.url)

        assert urls == _URLS

    @coroutine_test
    async def test_dequeue_priorities(self, jobdir: Path | None) -> None:
        async with self.create_scheduler(jobdir) as scheduler:
            for url, priority in _PRIORITIES:
                scheduler.enqueue_request(Request(url, priority=priority))

            priorities = []
            while scheduler.has_pending_requests():
                request = scheduler.next_request()
                assert request is not None
                priorities.append(request.priority)

        assert priorities == sorted([x[1] for x in _PRIORITIES], key=lambda x: -x)


class TestSchedulerOnDiskBase(TestSchedulerBase):
    @pytest.fixture
    def jobdir(self, tmp_path: Path) -> Path | None:
        return tmp_path

    @coroutine_test
    async def test_length(self, jobdir: Path | None) -> None:
        async with self.create_scheduler(jobdir) as scheduler:
            assert not scheduler.has_pending_requests()
            assert len(scheduler) == 0
            for url in _URLS:
                scheduler.enqueue_request(Request(url))

        async with self.create_scheduler(jobdir) as scheduler:
            assert scheduler.has_pending_requests()
            assert len(scheduler) == len(_URLS)

    @coroutine_test
    async def test_dequeue(self, jobdir: Path | None) -> None:
        async with self.create_scheduler(jobdir) as scheduler:
            for url in _URLS:
                scheduler.enqueue_request(Request(url))

        urls = set()
        async with self.create_scheduler(jobdir) as scheduler:
            while scheduler.has_pending_requests():
                request = scheduler.next_request()
                assert request is not None
                urls.add(request.url)
        assert urls == _URLS

    @coroutine_test
    async def test_dequeue_priorities(self, jobdir: Path | None) -> None:
        async with self.create_scheduler(jobdir) as scheduler:
            for url, priority in _PRIORITIES:
                scheduler.enqueue_request(Request(url, priority=priority))

        priorities = []
        async with self.create_scheduler(jobdir) as scheduler:
            while scheduler.has_pending_requests():
                request = scheduler.next_request()
                assert request is not None
                priorities.append(request.priority)
        assert priorities == sorted([x[1] for x in _PRIORITIES], key=lambda x: -x)


class TestSchedulerInMemory(TestSchedulerInMemoryBase):
    priority_queue_cls = "scrapy.pqueues.ScrapyPriorityQueue"


class TestSchedulerOnDisk(TestSchedulerOnDiskBase):
    priority_queue_cls = "scrapy.pqueues.ScrapyPriorityQueue"


_URLS_WITH_SLOTS = [
    ("http://foo.com/a", "a"),
    ("http://foo.com/b", "a"),
    ("http://foo.com/c", "b"),
    ("http://foo.com/d", "b"),
    ("http://foo.com/e", "c"),
    ("http://foo.com/f", "c"),
]


class TestMigration:
    @coroutine_test
    async def test_migration(self, tmp_path: Path) -> None:
        async with create_scheduler(
            "scrapy.pqueues.ScrapyPriorityQueue", tmp_path
        ) as prev_scheduler:
            for url in _URLS:
                prev_scheduler.enqueue_request(Request(url))

        with pytest.raises(
            ValueError,
            match="DownloaderAwarePriorityQueue accepts ``slot_startprios`` as a dict",
        ):
            async with create_scheduler(
                "scrapy.pqueues.DownloaderAwarePriorityQueue", tmp_path
            ):
                pass


def _is_scheduling_fair(enqueued_slots: list[str], dequeued_slots: list[str]) -> bool:
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


class DownloaderAwareSchedulerTestMixin(TestSchedulerBase):
    reopen = False
    priority_queue_cls = "scrapy.pqueues.DownloaderAwarePriorityQueue"

    @coroutine_test
    async def test_logic(self, jobdir: Path | None) -> None:
        def _setup(scheduler: Scheduler) -> None:
            for url, slot in _URLS_WITH_SLOTS:
                request = Request(url)
                request.meta[Downloader.DOWNLOAD_SLOT] = slot
                scheduler.enqueue_request(request)

        def _assert(scheduler: Scheduler) -> None:
            dequeued_slots: list[str] = []
            requests: list[Request] = []
            assert scheduler.crawler
            assert scheduler.crawler.engine
            downloader = scheduler.crawler.engine.downloader
            assert isinstance(downloader, MockDownloader)
            while scheduler.has_pending_requests():
                request = scheduler.next_request()
                assert request is not None
                slot = downloader.get_slot_key(request)
                dequeued_slots.append(slot)
                downloader.increment(slot)
                requests.append(request)

            for request in requests:
                slot = downloader.get_slot_key(request)
                downloader.decrement(slot)

            assert _is_scheduling_fair([s for u, s in _URLS_WITH_SLOTS], dequeued_slots)
            assert sum(len(s.active) for s in downloader.slots.values()) == 0

        if self.reopen:
            async with self.create_scheduler(jobdir) as scheduler:
                _setup(scheduler)
            async with self.create_scheduler(jobdir) as scheduler:
                _assert(scheduler)
        else:
            async with self.create_scheduler(jobdir) as scheduler:
                _setup(scheduler)
                _assert(scheduler)


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


class TestIntegrationWithDownloaderAwareInMemory:
    def setup_method(self):
        self.crawler = get_crawler(
            spidercls=StartUrlsSpider,
            settings_dict={
                "SCHEDULER_PRIORITY_QUEUE": "scrapy.pqueues.DownloaderAwarePriorityQueue",
                "DUPEFILTER_CLASS": "scrapy.dupefilters.BaseDupeFilter",
            },
        )

    @inline_callbacks_test
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
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                category=ScrapyDeprecationWarning,
                message="The CONCURRENT_REQUESTS_PER_IP setting is deprecated",
            )
            with pytest.raises(
                ValueError, match="does not support CONCURRENT_REQUESTS_PER_IP"
            ):
                self._incompatible()


_THROTTLER_AWARE_PQ = "scrapy.pqueues.ThrottlerAwarePriorityQueue"


class TestThrottlerAwareScheduler:
    def _crawler(self, settings_dict: dict[str, Any] | None = None) -> Crawler:
        settings = {
            "SCHEDULER_PRIORITY_QUEUE": _THROTTLER_AWARE_PQ,
            "DUPEFILTER_CLASS": "scrapy.dupefilters.BaseDupeFilter",
            **(settings_dict or {}),
        }
        return get_crawler(Spider, settings)

    def _scheduler(self, crawler: Crawler) -> ThrottlerAwareScheduler:
        spider = Spider(name="spider")
        crawler.spider = spider
        scheduler = ThrottlerAwareScheduler.from_crawler(crawler)
        scheduler.open(spider)
        return scheduler

    @coroutine_test
    async def test_enqueue_async_and_dequeue(self) -> None:
        scheduler = self._scheduler(self._crawler())
        assert await scheduler.enqueue_request_async(Request("http://a.com/1")) is True
        assert scheduler.has_pending_requests()
        assert len(scheduler) == 1
        request = scheduler.next_request()
        assert request is not None
        assert request.url == "http://a.com/1"
        assert scheduler.next_request() is None
        assert not scheduler.has_pending_requests()
        scheduler.close("finished")

    def test_sync_enqueue_raises(self) -> None:
        scheduler = self._scheduler(self._crawler())
        with pytest.raises(RuntimeError, match="asynchronous enqueue path"):
            scheduler.enqueue_request(Request("http://a.com/1"))
        scheduler.close("finished")

    def test_requires_throttler_aware_priority_queue(self) -> None:
        crawler = self._crawler(
            {"SCHEDULER_PRIORITY_QUEUE": "scrapy.pqueues.ScrapyPriorityQueue"}
        )
        spider = Spider(name="spider")
        crawler.spider = spider
        scheduler = ThrottlerAwareScheduler.from_crawler(crawler)
        with pytest.raises(ValueError, match="throttler-aware priority queue"):
            scheduler.open(spider)

    @coroutine_test
    async def test_delay_blocks_and_reports_delay(self) -> None:
        crawler = self._crawler(
            {
                "THROTTLER_SCOPES": {"slow.com": {"delay": 1000.0}},
                "RANDOMIZE_DOWNLOAD_DELAY": False,
            },
        )
        scheduler = self._scheduler(crawler)
        await scheduler.enqueue_request_async(Request("http://slow.com/1"))
        await scheduler.enqueue_request_async(Request("http://slow.com/2"))
        # The first request is sendable; the second is blocked by the delay.
        first = scheduler.next_request()
        assert first is not None
        assert scheduler.next_request() is None
        assert scheduler.has_pending_requests()
        assert scheduler.get_next_request_delay() == pytest.approx(1000.0, abs=1.0)
        scheduler.close("finished")

    @coroutine_test
    async def test_no_delay_when_only_concurrency_blocked(self) -> None:
        crawler = self._crawler(
            {"THROTTLER_SCOPES": {"slow.com": {"concurrency": 1}}},
        )
        scheduler = self._scheduler(crawler)
        await scheduler.enqueue_request_async(Request("http://slow.com/1"))
        await scheduler.enqueue_request_async(Request("http://slow.com/2"))
        assert scheduler.next_request() is not None
        assert scheduler.next_request() is None
        # A purely concurrency-blocked state has no time-based wakeup.
        assert scheduler.get_next_request_delay() is None
        scheduler.close("finished")

    @coroutine_test
    async def test_delayed_request_survives_jobdir_stop(self, tmp_path: Path) -> None:
        # A request held back by its per-request delay must not be
        # lost on a graceful stop when a JOBDIR is configured: it is flushed to
        # the disk queue on close and restored on resume.
        crawler = self._crawler(
            {"JOBDIR": str(tmp_path), "RANDOMIZE_DOWNLOAD_DELAY": False}
        )
        scheduler = self._scheduler(crawler)
        request = Request("http://a.com/slow", meta={"delay": 1000.0})
        assert await scheduler.enqueue_request_async(request) is True
        assert len(scheduler) == 1
        # The delay holds it back, so nothing is dequeued before the stop.
        assert scheduler.next_request() is None
        scheduler.close("finished")

        # Resume from the same JOBDIR: the request is still there and, having
        # been held once, is now sendable.
        resumed = self._scheduler(
            self._crawler({"JOBDIR": str(tmp_path), "RANDOMIZE_DOWNLOAD_DELAY": False})
        )
        assert len(resumed) == 1
        resumed_request = resumed.next_request()
        assert resumed_request is not None
        assert resumed_request.url == "http://a.com/slow"
        resumed.close("finished")

    @coroutine_test
    async def test_enqueue_async_filters_duplicates(self) -> None:
        crawler = self._crawler(
            {"DUPEFILTER_CLASS": "scrapy.dupefilters.RFPDupeFilter"}
        )
        scheduler = self._scheduler(crawler)
        assert crawler.spider is not None
        crawler.spider.crawler = crawler  # the dupefilter logs via spider.crawler
        assert await scheduler.enqueue_request_async(Request("http://a.com/1")) is True
        # The same request is filtered out the second time around.
        assert await scheduler.enqueue_request_async(Request("http://a.com/1")) is False
        assert len(scheduler) == 1
        scheduler.close("finished")

    @coroutine_test
    async def test_enqueue_async_unserializable_falls_back_to_memory(
        self, tmp_path: Path, caplog
    ) -> None:
        crawler = self._crawler({"JOBDIR": str(tmp_path), "SCHEDULER_DEBUG": True})
        scheduler = self._scheduler(crawler)
        # A lambda callback cannot be serialized to disk, so the request falls
        # back to the in-memory queue and the failure is logged once.
        request = Request(
            "http://a.com/1", callback=cast("CallbackT", lambda response: None)
        )
        with caplog.at_level(logging.WARNING, logger="scrapy.core.scheduler"):
            assert await scheduler.enqueue_request_async(request) is True
        assert "Unable to serialize request" in caplog.text
        assert crawler.stats is not None
        assert crawler.stats.get_value("scheduler/unserializable") == 1
        assert crawler.stats.get_value("scheduler/enqueued/memory") == 1
        scheduler.close("finished")

    @coroutine_test
    async def test_enqueue_async_unserializable_without_debug(
        self, tmp_path: Path
    ) -> None:
        # Same fallback as above, but with SCHEDULER_DEBUG off the failure is
        # tracked in stats without logging a warning.
        crawler = self._crawler({"JOBDIR": str(tmp_path)})
        scheduler = self._scheduler(crawler)
        request = Request(
            "http://a.com/1", callback=cast("CallbackT", lambda response: None)
        )
        assert await scheduler.enqueue_request_async(request) is True
        assert crawler.stats is not None
        assert crawler.stats.get_value("scheduler/unserializable") == 1
        scheduler.close("finished")

    @coroutine_test
    async def test_resume_from_disk(self, tmp_path: Path) -> None:
        settings = {"JOBDIR": str(tmp_path)}
        scheduler = self._scheduler(self._crawler(settings))
        await scheduler.enqueue_request_async(Request("http://a.com/1"))
        await scheduler.enqueue_request_async(Request("http://b.com/1"))
        scheduler.close("shutdown")

        scheduler2 = self._scheduler(self._crawler(settings))
        assert len(scheduler2) == 2
        urls = set()
        while (request := scheduler2.next_request()) is not None:
            urls.add(request.url)
        assert urls == {"http://a.com/1", "http://b.com/1"}
        scheduler2.close("finished")


class TestIntegrationWithThrottlerAwareScheduler:
    @inline_callbacks_test
    def test_integration(self):
        crawler = get_crawler(
            spidercls=StartUrlsSpider,
            settings_dict={
                "SCHEDULER": "scrapy.core.scheduler.ThrottlerAwareScheduler",
                "SCHEDULER_PRIORITY_QUEUE": "scrapy.pqueues.ThrottlerAwarePriorityQueue",
                "DUPEFILTER_CLASS": "scrapy.dupefilters.BaseDupeFilter",
            },
        )
        with MockServer() as mockserver:
            url = mockserver.url("/status?n=200", is_secure=False)
            start_urls = [url] * 6
            yield crawler.crawl(start_urls)
            assert crawler.stats.get_value("downloader/response_count") == len(
                start_urls
            )

    @inline_callbacks_test
    def test_integration_follow_requests(self):
        # Exercises the engine's asynchronous enqueue path for requests yielded
        # from a callback (not just start requests), and the idle guard that
        # keeps the spider open while an enqueue is in flight.
        class FollowSpider(Spider):
            name = "follow"

            def __init__(self, base_url, **kwargs):
                self.base_url = base_url
                super().__init__(**kwargs)

            async def start(self):
                yield Request(self.base_url + "/status?n=200")

            def parse(self, response):
                if b"follow" not in response.url.encode():
                    yield Request(response.url + "&follow=1", callback=self.parse)

        with MockServer() as mockserver:
            base_url = mockserver.url("", is_secure=False).rstrip("/")
            crawler = get_crawler(
                spidercls=FollowSpider,
                settings_dict={
                    "SCHEDULER": "scrapy.core.scheduler.ThrottlerAwareScheduler",
                    "SCHEDULER_PRIORITY_QUEUE": "scrapy.pqueues.ThrottlerAwarePriorityQueue",
                    "DUPEFILTER_CLASS": "scrapy.dupefilters.BaseDupeFilter",
                },
            )
            yield crawler.crawl(base_url=base_url)
            assert crawler.stats.get_value("downloader/response_count") == 2

    @inline_callbacks_test
    def test_integration_with_delay(self):
        # A small per-scope delay forces the engine to arm the throttler wakeup
        # timer between requests; the crawl must still complete.
        crawler = get_crawler(
            spidercls=StartUrlsSpider,
            settings_dict={
                "SCHEDULER": "scrapy.core.scheduler.ThrottlerAwareScheduler",
                "SCHEDULER_PRIORITY_QUEUE": "scrapy.pqueues.ThrottlerAwarePriorityQueue",
                "DUPEFILTER_CLASS": "scrapy.dupefilters.BaseDupeFilter",
                "RANDOMIZE_DOWNLOAD_DELAY": False,
                "THROTTLER_SCOPES": {"127.0.0.1": {"delay": 0.05}},
            },
        )
        with MockServer() as mockserver:
            url = mockserver.url("/status?n=200", is_secure=False)
            start_urls = [url] * 4
            yield crawler.crawl(start_urls)
            assert crawler.stats.get_value("downloader/response_count") == len(
                start_urls
            )
