from __future__ import annotations

import warnings
from abc import ABC, abstractmethod
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest

from scrapy.core.downloader import Downloader
from scrapy.core.scheduler import Scheduler
from scrapy.crawler import Crawler
from scrapy.dupefilters import BaseDupeFilter
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.http import Request
from scrapy.spiders import Spider
from scrapy.utils.defer import ensure_awaitable
from scrapy.utils.misc import build_from_crawler, load_object
from scrapy.utils.test import get_crawler
from tests.mockserver.http import MockServer
from tests.utils.decorators import coroutine_test, inline_callbacks_test
from tests.utils.downloader import MockDownloader

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable
    from pathlib import Path


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
    scheduler = build_from_crawler(Scheduler, mock_crawler)
    spider = Spider.from_crawler(mock_crawler, name="spider")
    await ensure_awaitable(scheduler.open(spider))
    try:
        yield scheduler
    finally:
        await ensure_awaitable(scheduler.close("finished"))
        await mock_crawler.stop_async()
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
    reopen = False

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

    @asynccontextmanager
    async def create_scheduler_for_assertions(
        self, jobdir: Path | None, setup: Callable[[Scheduler], None]
    ) -> AsyncGenerator[Scheduler]:
        if self.reopen:
            async with self.create_scheduler(jobdir) as scheduler:
                setup(scheduler)
            async with self.create_scheduler(jobdir) as scheduler:
                yield scheduler
        else:
            async with self.create_scheduler(jobdir) as scheduler:
                setup(scheduler)
                yield scheduler


class SchedulerTestMixin(TestSchedulerBase):
    @coroutine_test
    async def test_length(self, jobdir: Path | None) -> None:
        def _setup(scheduler: Scheduler) -> None:
            assert not scheduler.has_pending_requests()
            assert len(scheduler) == 0

            for url in _URLS:
                scheduler.enqueue_request(Request(url))

        async with self.create_scheduler_for_assertions(jobdir, _setup) as scheduler:
            assert scheduler.has_pending_requests()
            assert len(scheduler) == len(_URLS)

    @coroutine_test
    async def test_dequeue(self, jobdir: Path | None) -> None:
        def _setup(scheduler: Scheduler) -> None:
            for url in _URLS:
                scheduler.enqueue_request(Request(url))

        urls = set()
        async with self.create_scheduler_for_assertions(jobdir, _setup) as scheduler:
            while scheduler.has_pending_requests():
                request = scheduler.next_request()
                assert request is not None
                urls.add(request.url)

        assert urls == _URLS

    @coroutine_test
    async def test_dequeue_priorities(self, jobdir: Path | None) -> None:
        def _setup(scheduler: Scheduler) -> None:
            for url, priority in _PRIORITIES:
                scheduler.enqueue_request(Request(url, priority=priority))

        priorities = []
        async with self.create_scheduler_for_assertions(jobdir, _setup) as scheduler:
            while scheduler.has_pending_requests():
                request = scheduler.next_request()
                assert request is not None
                priorities.append(request.priority)

        assert priorities == sorted([x[1] for x in _PRIORITIES], key=lambda x: -x)


class TestSchedulerInMemoryBase(SchedulerTestMixin):
    pass


class TestSchedulerOnDiskBase(SchedulerTestMixin):
    reopen = True

    @pytest.fixture
    def jobdir(self, tmp_path: Path) -> Path | None:
        return tmp_path


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
    def _incompatible(self) -> None:
        settings = {
            "SCHEDULER_PRIORITY_QUEUE": "scrapy.pqueues.DownloaderAwarePriorityQueue",
            "CONCURRENT_REQUESTS_PER_IP": 1,
        }
        crawler = get_crawler(Spider, settings)
        scheduler = build_from_crawler(Scheduler, crawler)
        spider = Spider.from_crawler(crawler, name="spider")
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


def test_scheduler_without_crawler() -> None:
    """The crawler argument of Scheduler is optional."""
    scheduler = Scheduler(BaseDupeFilter())
    assert scheduler.crawler is None


@coroutine_test
async def test_unserializable_requests(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Requests that cannot be serialized fall back to the memory queue."""

    class UnserializableSpider(Spider):
        name = "unserializable"

        async def start(self):
            for index in range(2):
                yield Request(f"data:,{index}", meta={"callable": lambda: None})

    crawler = get_crawler(
        UnserializableSpider, {"JOBDIR": str(tmp_path), "SCHEDULER_DEBUG": True}
    )
    await crawler.crawl_async()
    assert crawler.stats.get_value("scheduler/unserializable") == 2
    assert crawler.stats.get_value("scheduler/enqueued/memory") == 2
    assert caplog.text.count("Unable to serialize request") == 1
