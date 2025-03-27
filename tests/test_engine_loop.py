from collections import deque

from twisted.internet.defer import Deferred
from twisted.trial.unittest import TestCase

from scrapy import Request, Spider, signals
from scrapy.utils.defer import deferred_f_from_coro_f, maybe_deferred_to_future
from scrapy.utils.test import get_crawler

from .mockserver import MockServer
from .test_scheduler import MemoryScheduler


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


class RequestSendOrderTestCase(TestCase):
    seconds = 0.1  # increase if flaky

    @classmethod
    def setUpClass(cls):
        cls.mockserver = MockServer()
        cls.mockserver.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.mockserver.__exit__(None, None, None)  # increase if flaky

    def _request(self, num, response_seconds, download_slots):
        url = self.mockserver.url(f"/delay?n={response_seconds}&{num}")
        meta = {"download_slot": str(num % download_slots)}
        return Request(url, meta=meta)

    @deferred_f_from_coro_f
    async def _test_request_order(
        self,
        start_nums,
        cb_nums,
        settings=None,
        response_seconds=None,
        download_slots=1,
        start_fn=None,
    ):
        settings = settings or {}
        response_seconds = response_seconds or self.seconds

        if start_fn is None:

            async def start_fn(spider):
                for num in start_nums:
                    yield self._request(num, response_seconds, download_slots)

        class TestSpider(Spider):
            name = "test"
            cb_requests = deque(
                [
                    self._request(num, response_seconds, download_slots)
                    for num in cb_nums
                ]
            )
            start = start_fn

            def parse(self, response):
                while self.cb_requests:
                    yield self.cb_requests.popleft()

        actual_nums = []

        def track_num(request, spider):
            actual_nums.append(int(request.url.rsplit("&", maxsplit=1)[1]))

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
                request = self._request(num, response_seconds, download_slots)
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
                request = self._request(num, response_seconds, download_slots)
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
    async def test_lazy(self):
        start_nums = [1, 2, 4]
        cb_nums = [3]
        response_seconds = self.seconds
        download_slots = 1

        async def start(spider):
            for num in start_nums:
                if spider.crawler.engine.needs_backout():
                    await spider.crawler.signals.wait_for(signals.scheduler_empty)
                request = self._request(num, response_seconds, download_slots)
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
