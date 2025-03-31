from __future__ import annotations

from collections import deque
from logging import ERROR
from typing import TYPE_CHECKING

from testfixtures import LogCapture
from twisted.internet.defer import Deferred
from twisted.trial.unittest import TestCase

from scrapy import Request, Spider, signals
from scrapy.core.engine import ExecutionEngine
from scrapy.utils.defer import deferred_f_from_coro_f, maybe_deferred_to_future
from scrapy.utils.test import get_crawler

from .mockserver import MockServer
from .test_scheduler import MemoryScheduler

if TYPE_CHECKING:
    from scrapy.http import Response


async def sleep(seconds: float = ExecutionEngine._MIN_BACK_IN_SECONDS) -> None:
    from twisted.internet import reactor

    deferred: Deferred[None] = Deferred()
    reactor.callLater(seconds, deferred.callback, None)
    await maybe_deferred_to_future(deferred)


class MainTestCase(TestCase):
    @deferred_f_from_coro_f
    async def test_start_exception(self):
        """If Spider.start() raises an unhandled exception, scheduler requests
        should still be processed."""

        class TestSpider(Spider):
            name = "test"

            async def start(self):
                yield Request("data:,a")
                self.crawler.engine.scheduler.enqueue_request(Request("data:,b"))
                raise RuntimeError

            def parse(self, response):
                pass

        actual_urls = []

        def track_url(request, spider):
            actual_urls.append(request.url)

        settings = {"SCHEDULER": MemoryScheduler}
        crawler = get_crawler(TestSpider, settings_dict=settings)
        crawler.signals.connect(track_url, signals.request_reached_downloader)
        with LogCapture() as log:
            await maybe_deferred_to_future(crawler.crawl())
        assert crawler.stats.get_value("finish_reason") == "finished"
        expected_urls = ["data:,a", "data:,b"]
        assert actual_urls == expected_urls, (
            f"{actual_urls=} != {expected_urls=}\n{log}"
        )

    @deferred_f_from_coro_f
    async def test_close_during_start_iteration(self):
        class TestSpider(Spider):
            name = "test"

            async def start(self):
                assert self.crawler.engine is not None
                await maybe_deferred_to_future(self.crawler.engine.close())
                yield Request("data:,a")

            def parse(self, response):
                pass

        actual_urls = []

        def track_url(request, spider):
            actual_urls.append(request.url)

        settings = {"SCHEDULER": MemoryScheduler}
        crawler = get_crawler(TestSpider, settings_dict=settings)
        crawler.signals.connect(track_url, signals.request_reached_downloader)

        with LogCapture(level=ERROR) as log:
            await maybe_deferred_to_future(crawler.crawl())

        assert not log.records, f"{log.records=}"
        finish_reason = crawler.stats.get_value("finish_reason")
        assert finish_reason == "shutdown", f"{finish_reason=}"
        expected_urls = []
        assert actual_urls == expected_urls, f"{actual_urls=} != {expected_urls=}"

    # Unexpected scheduler exceptions

    @deferred_f_from_coro_f
    async def test_scheduler_has_pending_requests_exception(self):
        """If Scheduler.has_pending_requests() raises an exception while
        checking if the spider is idle, consider the return value to be False
        (i.e. the spider is indeed idle), and log a traceback."""

        class TestScheduler(MemoryScheduler):
            def has_pending_requests(self):
                raise RuntimeError

            def next_request(self):
                return None

        class TestSpider(Spider):
            name = "test"
            start_urls = []

            def parse(self, response):
                pass

        actual_urls = []

        def track_url(request, spider):
            actual_urls.append(request.url)

        settings = {"SCHEDULER": TestScheduler}
        crawler = get_crawler(TestSpider, settings_dict=settings)
        crawler.signals.connect(track_url, signals.request_reached_downloader)
        with LogCapture() as log:
            await maybe_deferred_to_future(crawler.crawl())
        assert crawler.stats.get_value("finish_reason") == "finished"
        expected_urls = []
        assert actual_urls == expected_urls, f"{actual_urls=} != {expected_urls=}"
        assert "in has_pending_requests\n    raise RuntimeError" in str(log), log

    @deferred_f_from_coro_f
    async def test_scheduler_enqueue_request_exception(self):
        class TestScheduler(MemoryScheduler):
            def enqueue_request(self, request):
                raise RuntimeError

        class TestSpider(Spider):
            name = "test"
            start_urls = ["data:,"]

            def parse(self, response):
                pass

        actual_dropped_urls = []

        def track_dropped_url(request, spider):
            actual_dropped_urls.append(request.url)

        settings = {"SCHEDULER": TestScheduler}
        crawler = get_crawler(TestSpider, settings_dict=settings)
        crawler.signals.connect(track_dropped_url, signals.request_dropped)
        with LogCapture() as log:
            await maybe_deferred_to_future(crawler.crawl())
        assert crawler.stats.get_value("finish_reason") == "finished"
        expected_dropped_urls = ["data:,"]
        assert actual_dropped_urls == expected_dropped_urls, (
            f"{actual_dropped_urls=} != {expected_dropped_urls=}"
        )
        assert "in enqueue_request\n    raise RuntimeError" in str(log), log

    @deferred_f_from_coro_f
    async def test_scheduler_next_request_exception(self):
        class TestScheduler(MemoryScheduler):
            queue = ["data:,b", RuntimeError(), "data:,a"]

            def next_request(self):
                request = super().next_request()
                if isinstance(request, Exception):
                    raise request
                return request

        class TestSpider(Spider):
            name = "test"

            async def start(self):
                await self.crawler.signals.wait_for(signals.scheduler_empty)
                yield Request("data:,c")

            def parse(self, response):
                pass

        actual_urls = []

        def track_url(request, spider):
            actual_urls.append(request.url)

        settings = {"SCHEDULER": TestScheduler}
        crawler = get_crawler(TestSpider, settings_dict=settings)
        crawler.signals.connect(track_url, signals.request_reached_downloader)
        with LogCapture() as log:
            await maybe_deferred_to_future(crawler.crawl())
        assert crawler.stats.get_value("finish_reason") == "finished"
        expected_urls = ["data:,a", "data:,b", "data:,c"]
        assert actual_urls == expected_urls, f"{actual_urls=} != {expected_urls=}"
        assert "in next_request\n    raise request" in str(log), log


class RequestSendOrderTestCase(TestCase):
    seconds = 0.1  # increase if flaky

    @classmethod
    def setUpClass(cls):
        cls.mockserver = MockServer()
        cls.mockserver.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.mockserver.__exit__(None, None, None)  # increase if flaky

    def request(self, num, response_seconds, download_slots=1):
        url = self.mockserver.url(f"/delay?n={response_seconds}&{num}")
        meta = {"download_slot": str(num % download_slots)}
        return Request(url, meta=meta)

    def get_num(self, request_or_response: Request | Response):
        return int(request_or_response.url.rsplit("&", maxsplit=1)[1])

    @deferred_f_from_coro_f
    async def _test_request_order(
        self,
        start_nums,
        cb_nums=None,
        settings=None,
        response_seconds=None,
        download_slots=1,
        start_fn=None,
        parse_fn=None,
    ):
        cb_nums = cb_nums or []
        settings = settings or {}
        response_seconds = response_seconds or self.seconds

        cb_requests = deque(
            [self.request(num, response_seconds, download_slots) for num in cb_nums]
        )

        if start_fn is None:

            async def start_fn(spider):
                for num in start_nums:
                    yield self.request(num, response_seconds, download_slots)

        if parse_fn is None:

            def parse_fn(spider, response):
                while cb_requests:
                    yield cb_requests.popleft()

        class TestSpider(Spider):
            name = "test"
            start = start_fn
            parse = parse_fn

        actual_nums = []

        def track_num(request, spider):
            actual_nums.append(self.get_num(request))

        crawler = get_crawler(TestSpider, settings_dict=settings)
        crawler.signals.connect(track_num, signals.request_reached_downloader)
        await maybe_deferred_to_future(crawler.crawl())
        assert crawler.stats.get_value("finish_reason") == "finished"
        expected_nums = sorted(start_nums + cb_nums)
        assert actual_nums == expected_nums, f"{actual_nums=} != {expected_nums=}"

    # Examples from the “Start requests” section of the documentation about
    # spiders.

    @deferred_f_from_coro_f
    async def test_start_requests_first(self):
        start_nums = [1, 3, 2]
        cb_nums = [4]
        response_seconds = self.seconds
        download_slots = 1

        async def start(spider):
            for num in start_nums:
                request = self.request(num, response_seconds, download_slots)
                yield request.replace(priority=1)

        await maybe_deferred_to_future(
            self._test_request_order(
                start_nums=start_nums,
                cb_nums=cb_nums,
                settings={"CONCURRENT_REQUESTS": 1},
                response_seconds=response_seconds,
                start_fn=start,
            )
        )

    @deferred_f_from_coro_f
    async def test_start_requests_first_sorted(self):
        start_nums = [1, 2, 3]
        cb_nums = [4]
        response_seconds = self.seconds
        download_slots = 1

        async def start(spider):
            priority = len(start_nums)
            for num in start_nums:
                request = self.request(num, response_seconds, download_slots)
                yield request.replace(priority=priority)
                priority -= 1

        await maybe_deferred_to_future(
            self._test_request_order(
                start_nums=start_nums,
                cb_nums=cb_nums,
                settings={"CONCURRENT_REQUESTS": 1},
                response_seconds=response_seconds,
                start_fn=start,
            )
        )

    @deferred_f_from_coro_f
    async def test_front_load(self):
        start_nums = [2, 1]
        response_seconds = 0
        download_slots = 1

        async def start(spider):
            # typing:
            assert spider.crawler.engine is not None
            assert isinstance(spider.crawler.engine.scheduler, MemoryScheduler)

            spider.crawler.engine.scheduler.pause()
            # By pausing the scheduler, a is scheduled before b is sent,
            # and since the scheduler uses a LIFO queue, a is sent first.
            yield self.request(2, response_seconds, download_slots)
            yield self.request(1, response_seconds, download_slots)
            spider.crawler.engine.scheduler.unpause()

        await maybe_deferred_to_future(
            self._test_request_order(
                start_nums=start_nums,
                settings={"SCHEDULER": MemoryScheduler},
                response_seconds=response_seconds,
                start_fn=start,
            )
        )

    @deferred_f_from_coro_f
    async def test_lazy(self):
        start_nums = [1, 2, 4]
        cb_nums = [3]
        response_seconds = self.seconds * 2**1  # increase if flaky
        download_slots = 1

        async def start(spider):
            for num in start_nums:
                if spider.crawler.engine.needs_backout():
                    await spider.crawler.signals.wait_for(signals.scheduler_empty)
                request = self.request(num, response_seconds, download_slots)
                yield request

        await maybe_deferred_to_future(
            self._test_request_order(
                start_nums=start_nums,
                cb_nums=cb_nums,
                settings={
                    "CONCURRENT_REQUESTS": 1,
                    # Without the lazy approach, a FIFO queue would yield the
                    # start requests in a different order.
                    "SCHEDULER_MEMORY_QUEUE": "scrapy.squeues.FifoMemoryQueue",
                },
                response_seconds=response_seconds,
                start_fn=start,
            )
        )

    @deferred_f_from_coro_f
    async def test_idle(self):
        # The requests already in the scheduler (a) take priority over start
        # requests.
        # Callback requests (b, c) take priority over start requests as well. a
        # yields b, b yields c.
        # Once there are no more ongoing requests, the first start request (d)
        # is sent. Then the requests from its callback (e) take priority. This
        # is recursive, the requests from the callback of the callback (f) take
        # priority as well.
        # Only once there are no more ongoing requests again is the second
        # start request (g) sent.

        nums = [1, 2, 3, 4, 5, 6, 7]
        response_seconds = 0
        download_slots = 1

        def _request(num):
            return self.request(num, response_seconds, download_slots)

        class TestScheduler(MemoryScheduler):
            queue = [_request(1)]

        async def start(spider):
            for request in [_request(4), _request(7)]:
                await spider.crawler.signals.wait_for(signals.spider_start_blocking)
                yield request

        def parse(spider, response):
            num = self.get_num(response)
            if num in {1, 2, 4, 5}:
                yield _request(num + 1)

        await maybe_deferred_to_future(
            self._test_request_order(
                start_nums=nums,
                settings={"SCHEDULER": TestScheduler},
                response_seconds=response_seconds,
                start_fn=start,
                parse_fn=parse,
            )
        )

    # Delay handling

    @deferred_f_from_coro_f
    async def test_delays(self):
        """Delays in Spider.start() or in the scheduler (i.e. returning no
        requests while also returning True from the has_pending_requests()
        method) should cause the spider to miss the processing of any later
        requests."""
        seconds = ExecutionEngine._MIN_BACK_IN_SECONDS

        def _request(num):
            return self.request(num, seconds)

        async def start(spider):
            from twisted.internet import reactor

            yield _request(1)

            # Let request 1 be processed.
            await spider.crawler.signals.wait_for(signals.scheduler_empty)

            spider.crawler.engine.scheduler.pause()
            spider.crawler.engine.scheduler.enqueue_request(_request(2))

            # During this time, the scheduler reports having requests but
            # returns None.
            await spider.crawler.signals.wait_for(signals.scheduler_empty)

            spider.crawler.engine.scheduler.unpause()

            # The scheduler request is processed.
            await spider.crawler.signals.wait_for(signals.scheduler_empty)

            yield _request(3)

            spider.crawler.engine.scheduler.pause()
            spider.crawler.engine.scheduler.enqueue_request(_request(4))

            # The last start request is processed during the time until the
            # delayed call below, proving that the start iteration can
            # finish before a scheduler “sleep” without causing the
            # scheduler to finish.
            reactor.callLater(0, spider.crawler.engine.scheduler.unpause)

        await maybe_deferred_to_future(
            self._test_request_order(
                start_nums=[1, 2, 3, 4],
                settings={"SCHEDULER": MemoryScheduler},
                response_seconds=seconds,
                start_fn=start,
            )
        )
