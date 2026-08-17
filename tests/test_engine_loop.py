from __future__ import annotations

from collections import deque
from logging import ERROR
from typing import TYPE_CHECKING, Any

import pytest

from scrapy import Request, Spider, signals
from scrapy.core.scheduler import BaseScheduler
from scrapy.exceptions import CloseSpider
from scrapy.utils.asyncio import call_later, sleep
from scrapy.utils.test import get_crawler
from tests.mockserver.http import MockServer
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Iterator

    from scrapy.http import Response


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


class NoneStartSpider(Spider):
    name = "test"

    def start(self) -> None:  # type: ignore[override]
        return None


class CoroutineStartSpider(Spider):
    name = "test"

    async def start(self) -> None:  # type: ignore[override]
        return None


class SyncStartSpider(Spider):
    name = "test"

    def start(self) -> Iterator[Request]:  # type: ignore[override]
        yield Request("data:,a")


class TestMain:
    @coroutine_test
    async def test_sleep(self):
        """Neither asynchronous sleeps on Spider.start() nor the equivalent on
        the scheduler (returning no requests while also returning True from
        the has_pending_requests() method) should cause the spider to miss the
        processing of any later requests."""
        seconds = 2

        class TestSpider(Spider):
            name = "test"

            async def start(self) -> AsyncIterator[Any]:
                assert self.crawler.engine._slot
                scheduler = self.crawler.engine._slot.scheduler
                assert isinstance(scheduler, MemoryScheduler)

                yield Request("data:,a")

                await sleep(seconds)

                scheduler.pause()
                scheduler.enqueue_request(Request("data:,b"))

                # During this time, the scheduler reports having requests but
                # returns None.
                await sleep(seconds)

                scheduler.unpause()

                # The scheduler request is processed.
                await sleep(seconds)

                yield Request("data:,c")

                await sleep(seconds)

                scheduler.pause()
                scheduler.enqueue_request(Request("data:,d"))

                # The last start request is processed during the time until the
                # delayed call below, proving that the start iteration can
                # finish before a scheduler “sleep” without causing the
                # scheduler to finish.
                call_later(seconds, scheduler.unpause)

            def parse(self, response: Response) -> None:
                pass

        actual_urls = []

        def track_url(request: Request, spider: Spider) -> None:
            actual_urls.append(request.url)

        settings = {"SCHEDULER": MemoryScheduler}
        crawler = get_crawler(TestSpider, settings_dict=settings)
        crawler.signals.connect(track_url, signals.request_reached_downloader)
        await crawler.crawl_async()
        assert crawler.stats.get_value("finish_reason") == "finished"
        expected_urls = ["data:,a", "data:,b", "data:,c", "data:,d"]
        assert actual_urls == expected_urls, f"{actual_urls=} != {expected_urls=}"

    @coroutine_test
    async def test_close_during_start_iteration(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        class TestSpider(Spider):
            name = "test"

            async def start(self) -> AsyncIterator[Any]:
                await self.crawler.engine.close_async()
                yield Request("data:,a")

            def parse(self, response: Response) -> None:
                pass

        actual_urls = []

        def track_url(request: Request, spider: Spider) -> None:
            actual_urls.append(request.url)

        settings = {"SCHEDULER": MemoryScheduler}
        crawler = get_crawler(TestSpider, settings_dict=settings)
        crawler.signals.connect(track_url, signals.request_reached_downloader)

        caplog.clear()
        with caplog.at_level(ERROR):
            await crawler.crawl_async()

        assert not caplog.records
        assert crawler.stats.get_value("finish_reason") == "shutdown"
        assert not actual_urls

    @pytest.mark.parametrize(
        ("spider_cls", "expected_type"),
        [
            (NoneStartSpider, "<class 'NoneType'>"),
            (CoroutineStartSpider, "<class 'coroutine'>"),
            (SyncStartSpider, "<class 'generator'>"),
        ],
    )
    @coroutine_test
    async def test_start_not_an_async_generator(
        self,
        spider_cls: type[Spider],
        expected_type: str,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        crawler = get_crawler(spider_cls)

        caplog.clear()
        with caplog.at_level(ERROR):
            await crawler.crawl_async()

        assert (
            f"{spider_cls.__name__}.start() must be an asynchronous generator,"
            f" i.e. an async def method with yield statements, got {expected_type}"
        ) in caplog.text
        assert crawler.stats
        assert crawler.stats.get_value("finish_reason") == "start_error"

    @coroutine_test
    async def test_start_error(self, caplog: pytest.LogCaptureFixture) -> None:
        class TestSpider(Spider):
            name = "test"

            async def start(self):
                yield Request("data:,a")
                raise ValueError

            def parse(self, response):
                pass

        actual_urls = []
        errors = []

        def track_url(request, spider):
            actual_urls.append(request.url)

        def track_error(failure, response, spider):
            errors.append((failure, response))

        settings = {"SCHEDULER": MemoryScheduler}
        crawler = get_crawler(TestSpider, settings_dict=settings)
        crawler.signals.connect(track_url, signals.request_reached_downloader)
        crawler.signals.connect(track_error, signals.spider_error)

        caplog.clear()
        with caplog.at_level(ERROR):
            await crawler.crawl_async()

        # The requests yielded before the exception are still crawled.
        assert actual_urls == ["data:,a"]
        assert len(caplog.records) == 1
        assert len(errors) == 1
        failure, response = errors[0]
        assert isinstance(failure.value, ValueError)
        assert response is None
        assert crawler.stats.get_value("finish_reason") == "start_error"
        assert crawler.stats.get_value("spider_exceptions/count") == 1
        assert crawler.stats.get_value("spider_exceptions/ValueError") == 1

    @coroutine_test
    async def test_close_spider_from_start(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        class TestSpider(Spider):
            name = "test"

            async def start(self):
                yield Request("data:,a")
                raise CloseSpider("my_reason")

            def parse(self, response):
                pass

        settings = {"SCHEDULER": MemoryScheduler}
        crawler = get_crawler(TestSpider, settings_dict=settings)

        caplog.clear()
        with caplog.at_level(ERROR):
            await crawler.crawl_async()

        assert not caplog.records
        assert crawler.stats.get_value("finish_reason") == "my_reason"
        assert crawler.stats.get_value("spider_exceptions/count") is None


class TestRequestSendOrder:
    mockserver: MockServer

    seconds = 0.1  # increase if flaky

    @classmethod
    def setup_class(cls):
        cls.mockserver = MockServer()
        cls.mockserver.__enter__()

    @classmethod
    def teardown_class(cls):
        cls.mockserver.__exit__(None, None, None)

    def request(
        self,
        num: int,
        response_seconds: float,
        download_slots: int,
        priority: int = 0,
    ) -> Request:
        url = self.mockserver.url(f"/delay?n={response_seconds}&{num}")
        meta = {"download_slot": str(num % download_slots)}
        return Request(url, meta=meta, priority=priority)

    def get_num(self, request_or_response: Request | Response) -> int:
        return int(request_or_response.url.rsplit("&", maxsplit=1)[1])

    async def _test_request_order(
        self,
        start_nums: list[int],
        cb_nums: list[int] | None = None,
        settings: dict[str, Any] | None = None,
        response_seconds: float | None = None,
        download_slots: int = 1,
        start_fn: Callable[[Spider], AsyncIterator[Any]] | None = None,
        parse_fn: Callable[..., Iterator[Any]] | None = None,
    ) -> None:
        cb_nums = cb_nums or []
        settings = settings or {}
        seconds = response_seconds or self.seconds

        cb_requests = deque(
            [self.request(num, seconds, download_slots) for num in cb_nums]
        )

        if start_fn is None:

            async def default_start(spider: Spider) -> AsyncIterator[Any]:
                for num in start_nums:
                    yield self.request(num, seconds, download_slots)

            start_fn = default_start

        if parse_fn is None:

            def default_parse(spider: Spider, response: Response) -> Iterator[Any]:
                while cb_requests:
                    yield cb_requests.popleft()

            parse_fn = default_parse

        spider_start = start_fn
        spider_parse = parse_fn

        class TestSpider(Spider):
            name = "test"
            start = spider_start
            parse = spider_parse

        actual_nums = []

        def track_num(request: Request, spider: Spider) -> None:
            actual_nums.append(self.get_num(request))

        crawler = get_crawler(TestSpider, settings_dict=settings)
        crawler.signals.connect(track_num, signals.request_reached_downloader)
        await crawler.crawl_async()
        assert crawler.stats.get_value("finish_reason") == "finished"
        expected_nums = sorted(start_nums + cb_nums)
        assert actual_nums == expected_nums, f"{actual_nums=} != {expected_nums=}"

    @coroutine_test
    async def test_default(self):
        """By default, callback requests take priority over start requests and
        are sent in order. Priority matters, but given the same priority, a
        callback request takes precedence."""
        nums = [1, 2, 3, 4, 5, 6]
        response_seconds = 0
        download_slots = 1

        def _request(num: int, priority: int = 0) -> Request:
            return self.request(
                num, response_seconds, download_slots, priority=priority
            )

        async def start(spider: Spider) -> AsyncIterator[Any]:
            assert spider.crawler.engine._slot
            # The first CONCURRENT_REQUESTS start requests are sent
            # immediately.
            yield _request(1)

            for request in (
                _request(2, priority=1),
                _request(5),
            ):
                spider.crawler.engine._slot.scheduler.enqueue_request(request)
            yield _request(6)
            yield _request(3, priority=1)
            yield _request(4, priority=1)

        def parse(spider: Spider, response: Response) -> Iterator[Any]:
            return
            yield

        await self._test_request_order(
            start_nums=nums,
            settings={"CONCURRENT_REQUESTS": 1},
            response_seconds=response_seconds,
            start_fn=start,
            parse_fn=parse,
        )

    @coroutine_test
    async def test_lifo_start(self):
        """Changing the queues of start requests to LIFO, matching the queues
        of non-start requests, does not cause all requests to be stored in the
        same queue objects, it only affects the order of start requests."""
        nums = [1, 2, 3, 4, 5, 6]
        response_seconds = 0
        download_slots = 1

        def _request(num: int, priority: int = 0) -> Request:
            return self.request(
                num, response_seconds, download_slots, priority=priority
            )

        async def start(spider: Spider) -> AsyncIterator[Any]:
            assert spider.crawler.engine._slot
            # The first CONCURRENT_REQUESTS start requests are sent
            # immediately.
            yield _request(1)

            for request in (
                _request(2, priority=1),
                _request(5),
            ):
                spider.crawler.engine._slot.scheduler.enqueue_request(request)
            yield _request(6)
            yield _request(4, priority=1)
            yield _request(3, priority=1)

        def parse(spider: Spider, response: Response) -> Iterator[Any]:
            return
            yield

        await self._test_request_order(
            start_nums=nums,
            settings={
                "CONCURRENT_REQUESTS": 1,
                "SCHEDULER_START_MEMORY_QUEUE": "scrapy.squeues.LifoMemoryQueue",
            },
            response_seconds=response_seconds,
            start_fn=start,
            parse_fn=parse,
        )

    @coroutine_test
    async def test_shared_queues(self):
        """If SCHEDULER_START_*_QUEUE is falsy, start requests and other
        requests share the same queue, i.e. start requests are not prioritized
        over other requests if their priority matches."""
        nums = list(range(1, 14))
        response_seconds = 0
        download_slots = 1

        def _request(num: int, priority: int = 0) -> Request:
            return self.request(
                num, response_seconds, download_slots, priority=priority
            )

        async def start(spider: Spider) -> AsyncIterator[Any]:
            assert spider.crawler.engine._slot
            # The first CONCURRENT_REQUESTS start requests are sent
            # immediately.
            yield _request(1)

            # Below, priority 1 requests are sent first, and requests are sent
            # in LIFO order.

            for request in (
                _request(7, priority=1),
                _request(6, priority=1),
                _request(13),
                _request(12),
            ):
                spider.crawler.engine._slot.scheduler.enqueue_request(request)

            yield _request(11)
            yield _request(10)
            yield _request(5, priority=1)
            yield _request(4, priority=1)

            for request in (
                _request(3, priority=1),
                _request(2, priority=1),
                _request(9),
                _request(8),
            ):
                spider.crawler.engine._slot.scheduler.enqueue_request(request)

        def parse(spider: Spider, response: Response) -> Iterator[Any]:
            return
            yield

        await self._test_request_order(
            start_nums=nums,
            settings={
                "CONCURRENT_REQUESTS": 1,
                "SCHEDULER_START_MEMORY_QUEUE": None,
            },
            response_seconds=response_seconds,
            start_fn=start,
            parse_fn=parse,
        )

    # Examples from the “Start requests” section of the documentation about
    # spiders.

    @coroutine_test
    async def test_lazy(self):
        start_nums = [1, 2, 4]
        cb_nums = [3]
        response_seconds = self.seconds * 2**1  # increase if flaky
        download_slots = 1

        async def start(spider: Spider) -> AsyncIterator[Any]:
            for num in start_nums:
                if spider.crawler.engine.needs_backout():
                    await spider.crawler.signals.wait_for(signals.scheduler_empty)
                request = self.request(num, response_seconds, download_slots)
                yield request

        await self._test_request_order(
            start_nums=start_nums,
            cb_nums=cb_nums,
            settings={
                "CONCURRENT_REQUESTS": 1,
            },
            response_seconds=response_seconds,
            start_fn=start,
        )
