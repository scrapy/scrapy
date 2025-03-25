from collections import deque

from twisted.internet.defer import Deferred
from twisted.trial.unittest import TestCase

from scrapy import Request, Spider, signals
from scrapy.core.engine import ExecutionEngine
from scrapy.utils.defer import deferred_f_from_coro_f, maybe_deferred_to_future
from scrapy.utils.test import get_crawler

from .mockserver import MockServer
from .test_scheduler import MemoryScheduler


def sleep(seconds: float = 0.001):
    from twisted.internet import reactor

    deferred: Deferred[None] = Deferred()
    reactor.callLater(seconds, deferred.callback, None)
    return maybe_deferred_to_future(deferred)


class MainTestCase(TestCase):
    @deferred_f_from_coro_f
    async def test_sleep(self):
        """Neither asynchronous sleeps on Spider.start() nor the equivalent on
        the scheduler (returning no requests while also returning True from
        the has_pending_requests() method) should cause the spider to miss the
        processing of any later requests."""
        seconds = ExecutionEngine._SLOT_HEARTBEAT_INTERVAL + 0.01

        class TestSpider(Spider):
            name = "test"

            async def start(self):
                from twisted.internet import reactor

                yield Request("data:,a")

                await sleep(seconds)

                self.crawler.engine._slot.scheduler.pause()
                self.crawler.engine._slot.scheduler.enqueue_request(Request("data:,b"))

                # During this time, the reactor reports having requests but
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


class MockServerTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mockserver = MockServer()
        cls.mockserver.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.mockserver.__exit__(None, None, None)

    # Verify the default behavior of the engine loop as described in the docs,
    # in the “Spider start” section of the page about spdiers.

    fast_seconds = 0.001
    slow_seconds = 0.2  # increase if flaky

    @deferred_f_from_coro_f
    async def _test_request_order(
        self,
        start_nums,
        cb_nums,
        settings=None,
        response_seconds=None,
        download_slots=1,
    ):
        settings = settings or {}
        response_seconds = response_seconds or self.slow_seconds

        def _request(num):
            url = self.mockserver.url(f"/delay?n={response_seconds}&{num}")
            meta = {"download_slot": str(num % download_slots)}
            return Request(url, meta=meta)

        class TestSpider(Spider):
            name = "test"
            cb_requests = deque([_request(num) for num in cb_nums])

            async def start(self):
                for num in start_nums:
                    yield _request(num)

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

    @deferred_f_from_coro_f
    async def test_default(self):
        await maybe_deferred_to_future(
            self._test_request_order(
                start_nums=[
                    1,
                    2,
                    3,
                    4,
                    5,
                    6,
                    7,
                    8,
                    9,
                    10,
                    11,
                    12,
                    13,
                    14,
                    15,
                    16,
                    26,
                    24,
                    23,
                    22,
                    21,
                    20,
                    19,
                    18,
                    17,
                ],
                cb_nums=[25],
            )
        )

    @deferred_f_from_coro_f
    async def test_conc1(self):
        await maybe_deferred_to_future(
            self._test_request_order(
                start_nums=[1, 4, 2],
                cb_nums=[3],
                settings={"CONCURRENT_REQUESTS": 1},
            )
        )

    @deferred_f_from_coro_f
    async def test_conc2(self):
        await maybe_deferred_to_future(
            self._test_request_order(
                start_nums=[1, 2, 6, 4, 3],
                cb_nums=[5],
                settings={"CONCURRENT_REQUESTS": 2},
            )
        )

    @deferred_f_from_coro_f
    async def test_conc8(self):
        await maybe_deferred_to_future(
            self._test_request_order(
                start_nums=[1, 2, 3, 4, 5, 6, 7, 8, 18, 16, 15, 14, 13, 12, 11, 10, 9],
                cb_nums=[17],
                settings={"CONCURRENT_REQUESTS": 8},
            )
        )

    @deferred_f_from_coro_f
    async def test_conc16(self):
        await maybe_deferred_to_future(
            self._test_request_order(
                start_nums=[
                    1,
                    2,
                    3,
                    4,
                    5,
                    6,
                    7,
                    8,
                    9,
                    10,
                    11,
                    12,
                    13,
                    14,
                    15,
                    16,
                    34,
                    32,
                    31,
                    30,
                    29,
                    28,
                    27,
                    26,
                    25,
                    24,
                    23,
                    22,
                    21,
                    20,
                    19,
                    18,
                    17,
                ],
                cb_nums=[33],
                settings={"CONCURRENT_REQUESTS_PER_DOMAIN": 16},
            )
        )

    @deferred_f_from_coro_f
    async def test_conc3_ds2(self):
        await maybe_deferred_to_future(
            self._test_request_order(
                start_nums=[1, 2, 3, 8, 6, 5, 4],
                cb_nums=[7],
                settings={
                    "CONCURRENT_REQUESTS": 3,
                },
                download_slots=2,
            )
        )

    @deferred_f_from_coro_f
    async def test_tconc3_dconc2(self):
        await maybe_deferred_to_future(
            self._test_request_order(
                start_nums=[1, 2, 3, 7, 5, 4],
                cb_nums=[6],
                settings={
                    "CONCURRENT_REQUESTS": 3,
                    "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
                },
            )
        )

    @deferred_f_from_coro_f
    async def test_tconc5_dconc3(self):
        await maybe_deferred_to_future(
            self._test_request_order(
                start_nums=[1, 2, 3, 4, 5, 10, 8, 7, 6],
                cb_nums=[9],
                settings={
                    "CONCURRENT_REQUESTS": 5,
                    "CONCURRENT_REQUESTS_PER_DOMAIN": 3,
                },
            )
        )

    @deferred_f_from_coro_f
    async def test_tconc5_dconc2_ds3(self):
        await maybe_deferred_to_future(
            self._test_request_order(
                start_nums=[1, 2, 3, 4, 5, 12, 10, 9, 8, 7, 6],
                cb_nums=[11],
                settings={
                    "CONCURRENT_REQUESTS": 5,
                    "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
                },
                download_slots=3,
            )
        )

    @deferred_f_from_coro_f
    async def test_tconc5_dconc3_ds2(self):
        await maybe_deferred_to_future(
            self._test_request_order(
                start_nums=[1, 2, 3, 4, 5, 12, 10, 9, 8, 7, 6],
                cb_nums=[11],
                settings={
                    "CONCURRENT_REQUESTS": 5,
                    "CONCURRENT_REQUESTS_PER_DOMAIN": 3,
                },
                download_slots=2,
            )
        )

    @deferred_f_from_coro_f
    async def test_tconc7_dconc2_ds3(self):
        await maybe_deferred_to_future(
            self._test_request_order(
                start_nums=[1, 2, 3, 4, 5, 6, 7, 15, 13, 12, 11, 10, 9, 8],
                cb_nums=[14],
                settings={
                    "CONCURRENT_REQUESTS": 7,
                    "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
                },
                download_slots=3,
            )
        )

    @deferred_f_from_coro_f
    async def test_tconc7_dconc3_ds2(self):
        await maybe_deferred_to_future(
            self._test_request_order(
                start_nums=[1, 2, 3, 4, 5, 6, 7, 15, 13, 12, 11, 10, 9, 8],
                cb_nums=[14],
                settings={
                    "CONCURRENT_REQUESTS": 7,
                    "CONCURRENT_REQUESTS_PER_DOMAIN": 3,
                },
                download_slots=2,
            )
        )

    @deferred_f_from_coro_f
    async def test_fast(self):
        await maybe_deferred_to_future(
            self._test_request_order(
                start_nums=[1, 3, 2],
                cb_nums=[4],
                settings={"CONCURRENT_REQUESTS": 1},
                response_seconds=self.fast_seconds,
            )
        )
        # TODO: Test how increasing concurrency behaves with fast responses.

    # TODO: Test claims:
    # - :ref:`Awaiting <await>` slow operations in :meth:`~scrapy.Spider.start` may lower it.
    # - If responses are very fast, it can be more than :setting:`CONCURRENT_REQUESTS`.
    # - Otherwise, it can reach 16 (:setting:`CONCURRENT_REQUESTS`)
