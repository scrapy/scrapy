from __future__ import annotations

from collections import deque
from logging import ERROR
from typing import TYPE_CHECKING

from testfixtures import LogCapture
from twisted.internet.defer import Deferred
from twisted.trial.unittest import TestCase

from scrapy import Request, Spider, signals
from scrapy.utils.defer import deferred_f_from_coro_f, maybe_deferred_to_future
from scrapy.utils.test import get_crawler

from .mockserver import MockServer
from .test_scheduler import MemoryScheduler

if TYPE_CHECKING:
    from scrapy.http import Response


async def sleep(seconds: float = 0.001) -> None:
    from twisted.internet import reactor

    deferred: Deferred[None] = Deferred()
    reactor.callLater(seconds, deferred.callback, None)
    await maybe_deferred_to_future(deferred)


class MainTestCase(TestCase):
    @deferred_f_from_coro_f
    async def test_sleep(self):
        """Neither asynchronous sleeps on Spider.start() nor the equivalent on
        the scheduler (returning no requests while also returning True from
        the has_pending_requests() method) should cause the spider to miss the
        processing of any later requests."""
        seconds = 2

        class TestSpider(Spider):
            name = "test"

            async def start(self):
                from twisted.internet import reactor

                yield Request("data:,a")

                await sleep(seconds)

                self.crawler.engine._slot.scheduler.pause()
                self.crawler.engine._slot.scheduler.enqueue_request(Request("data:,b"))

                # During this time, the scheduler reports having requests but
                # returns None.
                await sleep(seconds)

                self.crawler.engine._slot.scheduler.unpause()

                # The scheduler request is processed.
                await sleep(seconds)

                yield Request("data:,c")

                await sleep(seconds)

                self.crawler.engine._slot.scheduler.pause()
                self.crawler.engine._slot.scheduler.enqueue_request(Request("data:,d"))

                # The last start request is processed during the time until the
                # delayed call below, proving that the start iteration can
                # finish before a scheduler “sleep” without causing the
                # scheduler to finish.
                reactor.callLater(seconds, self.crawler.engine._slot.scheduler.unpause)

            def parse(self, response):
                pass

        actual_urls = []

        def track_url(request, spider):
            actual_urls.append(request.url)

        settings = {"SCHEDULER": MemoryScheduler}
        crawler = get_crawler(TestSpider, settings_dict=settings)
        crawler.signals.connect(track_url, signals.request_reached_downloader)
        await maybe_deferred_to_future(crawler.crawl())
        assert crawler.stats.get_value("finish_reason") == "finished"
        expected_urls = ["data:,a", "data:,b", "data:,c", "data:,d"]
        assert actual_urls == expected_urls, f"{actual_urls=} != {expected_urls=}"

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

        assert len(log.records) == 1
        assert log.records[0].msg == "Error running spider_closed_callback"
        finish_reason = crawler.stats.get_value("finish_reason")
        assert finish_reason == "shutdown", f"{finish_reason=}"
        expected_urls = []
        assert actual_urls == expected_urls, f"{actual_urls=} != {expected_urls=}"


class RequestSendOrderTestCase(TestCase):
    seconds = 0.1  # increase if flaky

    @classmethod
    def setUpClass(cls):
        cls.mockserver = MockServer()
        cls.mockserver.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.mockserver.__exit__(None, None, None)  # increase if flaky

    def request(self, num, response_seconds, download_slots, priority=0):
        url = self.mockserver.url(f"/delay?n={response_seconds}&{num}")
        meta = {"download_slot": str(num % download_slots)}
        return Request(url, meta=meta, priority=priority)

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

    @deferred_f_from_coro_f
    async def test_default(self):
        """By default, callback requests take priority over start requests and
        are sent in order. Priority matters, but given the same priority, a
        callback request takes precedence."""
        nums = [1, 2, 3, 4, 5, 6]
        response_seconds = 0
        download_slots = 1

        def _request(num, priority=0):
            return self.request(
                num, response_seconds, download_slots, priority=priority
            )

        async def start(spider):
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

        def parse(spider, response):
            return
            yield

        await maybe_deferred_to_future(
            self._test_request_order(
                start_nums=nums,
                settings={"CONCURRENT_REQUESTS": 1},
                response_seconds=response_seconds,
                start_fn=start,
                parse_fn=parse,
            )
        )

    @deferred_f_from_coro_f
    async def test_lifo_start(self):
        """Changing the queues of start requests to LIFO, matching the queues
        of non-start requests, does not cause all requests to be stored in the
        same queue objects, it only affects the order of start requests."""
        nums = [1, 2, 3, 4, 5, 6]
        response_seconds = 0
        download_slots = 1

        def _request(num, priority=0):
            return self.request(
                num, response_seconds, download_slots, priority=priority
            )

        async def start(spider):
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

        def parse(spider, response):
            return
            yield

        await maybe_deferred_to_future(
            self._test_request_order(
                start_nums=nums,
                settings={
                    "CONCURRENT_REQUESTS": 1,
                    "SCHEDULER_START_MEMORY_QUEUE": "scrapy.squeues.LifoMemoryQueue",
                },
                response_seconds=response_seconds,
                start_fn=start,
                parse_fn=parse,
            )
        )

    @deferred_f_from_coro_f
    async def test_shared_queues(self):
        """If SCHEDULER_START_*_QUEUE is falsy, start requests and other
        requests share the same queue, i.e. start requests are not priorized
        over other requests if their priority matches."""
        nums = list(range(1, 14))
        response_seconds = 0
        download_slots = 1

        def _request(num, priority=0):
            return self.request(
                num, response_seconds, download_slots, priority=priority
            )

        async def start(spider):
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

        def parse(spider, response):
            return
            yield

        await maybe_deferred_to_future(
            self._test_request_order(
                start_nums=nums,
                settings={
                    "CONCURRENT_REQUESTS": 1,
                    "SCHEDULER_START_MEMORY_QUEUE": None,
                },
                response_seconds=response_seconds,
                start_fn=start,
                parse_fn=parse,
            )
        )

    # Examples from the “Start requests” section of the documentation about
    # spiders.

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
                },
                response_seconds=response_seconds,
                start_fn=start,
            )
        )
