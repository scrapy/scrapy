from collections import deque

import pytest
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


class RequestSendOrderTestCase(TestCase):
    """Test the intrincacies of request send order when all start requests and
    callback requests have the same priority.

    It is a very unintuitive behavior, documented as “undefined” so that we may
    change it in the future without breaking the contract.

    For the asyncio reactor:

    1.  First, the first CONCURRENT_REQUESTS start requests are sent in order.

        Awaiting slow operations in Spider.start() can lower that.

    2.  Then, assuming an even domain distribution in start requests (i.e.
        ABCABC, not AABBCC), the last N start requests are sent in reverse
        order, where N is:

            min(CONCURRENT_REQUESTS, CONCURRENT_REQUESTS_PER_DOMAIN * domain_count)

    3.  Finally, the remaining start requests are also sent in reverse order,
        but only when there are not enough pending requests yielded from
        callbacks to reach the configured concurrency.

    For the default Twisted reactor, step 1 sends the last CONCURRENT_REQUESTS
    start requests in reverse order instead.

    The reverse order is because the scheduler uses a LIFO queue by default
    (SCHEDULER_MEMORY_QUEUE, SCHEDULER_DISK_QUEUE). The order of the first few
    requests is unnaffected because they are sent as soon as they are
    scheduled, and the last start requests sent before callback requests are
    those that can be sent before the first callback requests are scheduled.
    """

    @classmethod
    def setUpClass(cls):
        cls.mockserver = MockServer()
        cls.mockserver.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.mockserver.__exit__(None, None, None)

    fast_seconds = 0.001
    slow_seconds = 0.4  # increase if flaky

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
        response_seconds = response_seconds or self.slow_seconds

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

    # Asyncio reactor behavior

    @pytest.mark.only_asyncio
    @deferred_f_from_coro_f
    async def test_ar_default(self):
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

    @pytest.mark.only_asyncio
    @deferred_f_from_coro_f
    async def test_ar_conc1(self):
        await maybe_deferred_to_future(
            self._test_request_order(
                start_nums=[1, 4, 2],
                cb_nums=[3],
                settings={"CONCURRENT_REQUESTS": 1},
            )
        )

    @pytest.mark.only_asyncio
    @deferred_f_from_coro_f
    async def test_ar_conc2(self):
        await maybe_deferred_to_future(
            self._test_request_order(
                start_nums=[1, 2, 6, 4, 3],
                cb_nums=[5],
                settings={"CONCURRENT_REQUESTS": 2},
            )
        )

    @pytest.mark.only_asyncio
    @deferred_f_from_coro_f
    async def test_ar_conc8(self):
        await maybe_deferred_to_future(
            self._test_request_order(
                start_nums=[1, 2, 3, 4, 5, 6, 7, 8, 18, 16, 15, 14, 13, 12, 11, 10, 9],
                cb_nums=[17],
                settings={"CONCURRENT_REQUESTS": 8},
            )
        )

    @pytest.mark.only_asyncio
    @deferred_f_from_coro_f
    async def test_ar_conc16(self):
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

    @pytest.mark.only_asyncio
    @deferred_f_from_coro_f
    async def test_ar_conc3_ds2(self):
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

    @pytest.mark.only_asyncio
    @deferred_f_from_coro_f
    async def test_ar_tconc3_dconc2(self):
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

    @pytest.mark.only_asyncio
    @deferred_f_from_coro_f
    async def test_ar_tconc5_dconc3(self):
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

    @pytest.mark.only_asyncio
    @deferred_f_from_coro_f
    async def test_ar_tconc5_dconc2_ds3(self):
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

    @pytest.mark.only_asyncio
    @deferred_f_from_coro_f
    async def test_ar_tconc5_dconc3_ds2(self):
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

    @pytest.mark.only_asyncio
    @deferred_f_from_coro_f
    async def test_ar_tconc7_dconc2_ds3(self):
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

    @pytest.mark.only_asyncio
    @deferred_f_from_coro_f
    async def test_ar_tconc7_dconc3_ds2(self):
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

    @pytest.mark.only_asyncio
    @deferred_f_from_coro_f
    async def test_ar_fast(self):
        """Very fast responses may increase the number of start requests sent
        in reverse order before the first callback request."""
        await maybe_deferred_to_future(
            self._test_request_order(
                start_nums=[1, 3, 2],
                cb_nums=[4],
                settings={"CONCURRENT_REQUESTS": 1},
                response_seconds=self.fast_seconds,
            )
        )

    # Default reactor behavior

    @pytest.mark.only_not_asyncio
    @deferred_f_from_coro_f
    async def test_dr_default(self):
        await maybe_deferred_to_future(
            self._test_request_order(
                start_nums=[
                    26,
                    24,
                    23,
                    22,
                    21,
                    20,
                    19,
                    18,
                    17,
                    16,
                    15,
                    14,
                    13,
                    12,
                    11,
                    10,
                    9,
                    8,
                    7,
                    6,
                    5,
                    4,
                    3,
                    2,
                    1,
                ],
                cb_nums=[25],
            )
        )

    @pytest.mark.only_not_asyncio
    @deferred_f_from_coro_f
    async def test_dr_conc1(self):
        await maybe_deferred_to_future(
            self._test_request_order(
                start_nums=[4, 2, 1],
                cb_nums=[3],
                settings={"CONCURRENT_REQUESTS": 1},
            )
        )

    @pytest.mark.only_not_asyncio
    @deferred_f_from_coro_f
    async def test_dr_conc2(self):
        await maybe_deferred_to_future(
            self._test_request_order(
                start_nums=[6, 4, 3, 2, 1],
                cb_nums=[5],
                settings={"CONCURRENT_REQUESTS": 2},
            )
        )

    @pytest.mark.only_not_asyncio
    @deferred_f_from_coro_f
    async def test_dr_conc8(self):
        await maybe_deferred_to_future(
            self._test_request_order(
                start_nums=[18, 16, 15, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1],
                cb_nums=[17],
                settings={"CONCURRENT_REQUESTS": 8},
            )
        )

    @pytest.mark.only_not_asyncio
    @deferred_f_from_coro_f
    async def test_dr_conc16(self):
        await maybe_deferred_to_future(
            self._test_request_order(
                start_nums=[
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
                    16,
                    15,
                    14,
                    13,
                    12,
                    11,
                    10,
                    9,
                    8,
                    7,
                    6,
                    5,
                    4,
                    3,
                    2,
                    1,
                ],
                cb_nums=[33],
                settings={"CONCURRENT_REQUESTS_PER_DOMAIN": 16},
            )
        )

    @pytest.mark.only_not_asyncio
    @deferred_f_from_coro_f
    async def test_dr_conc3_ds2(self):
        await maybe_deferred_to_future(
            self._test_request_order(
                start_nums=[8, 6, 5, 4, 3, 2, 1],
                cb_nums=[7],
                settings={
                    "CONCURRENT_REQUESTS": 3,
                },
                download_slots=2,
            )
        )

    @pytest.mark.only_not_asyncio
    @deferred_f_from_coro_f
    async def test_dr_tconc3_dconc2(self):
        await maybe_deferred_to_future(
            self._test_request_order(
                start_nums=[7, 5, 4, 3, 2, 1],
                cb_nums=[6],
                settings={
                    "CONCURRENT_REQUESTS": 3,
                    "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
                },
            )
        )

    @pytest.mark.only_not_asyncio
    @deferred_f_from_coro_f
    async def test_dr_tconc5_dconc3(self):
        await maybe_deferred_to_future(
            self._test_request_order(
                start_nums=[10, 8, 7, 6, 5, 4, 3, 2, 1],
                cb_nums=[9],
                settings={
                    "CONCURRENT_REQUESTS": 5,
                    "CONCURRENT_REQUESTS_PER_DOMAIN": 3,
                },
            )
        )

    @pytest.mark.only_not_asyncio
    @deferred_f_from_coro_f
    async def test_dr_tconc5_dconc2_ds3(self):
        await maybe_deferred_to_future(
            self._test_request_order(
                start_nums=[12, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1],
                cb_nums=[11],
                settings={
                    "CONCURRENT_REQUESTS": 5,
                    "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
                },
                download_slots=3,
            )
        )

    @pytest.mark.only_not_asyncio
    @deferred_f_from_coro_f
    async def test_dr_tconc5_dconc3_ds2(self):
        await maybe_deferred_to_future(
            self._test_request_order(
                start_nums=[12, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1],
                cb_nums=[11],
                settings={
                    "CONCURRENT_REQUESTS": 5,
                    "CONCURRENT_REQUESTS_PER_DOMAIN": 3,
                },
                download_slots=2,
            )
        )

    @pytest.mark.only_not_asyncio
    @deferred_f_from_coro_f
    async def test_dr_tconc7_dconc2_ds3(self):
        await maybe_deferred_to_future(
            self._test_request_order(
                start_nums=[15, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1],
                cb_nums=[14],
                settings={
                    "CONCURRENT_REQUESTS": 7,
                    "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
                },
                download_slots=3,
            )
        )

    @pytest.mark.only_not_asyncio
    @deferred_f_from_coro_f
    async def test_dr_tconc7_dconc3_ds2(self):
        await maybe_deferred_to_future(
            self._test_request_order(
                start_nums=[15, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1],
                cb_nums=[14],
                settings={
                    "CONCURRENT_REQUESTS": 7,
                    "CONCURRENT_REQUESTS_PER_DOMAIN": 3,
                },
                download_slots=2,
            )
        )

    @pytest.mark.only_not_asyncio
    @deferred_f_from_coro_f
    async def test_dr_fast(self):
        """Very fast responses may increase the number of start requests sent
        in reverse order before the first callback request."""
        await maybe_deferred_to_future(
            self._test_request_order(
                start_nums=[3, 2, 1],
                cb_nums=[4],
                settings={"CONCURRENT_REQUESTS": 1},
                response_seconds=self.fast_seconds,
            )
        )

    # Behavior shared by both reactors

    @deferred_f_from_coro_f
    async def test_await(self):
        """Awaiting slow operations in Spider.start() may lower the number of
        first start requests sent in order."""
        start_nums = [1, 3]
        cb_nums = [2]
        response_seconds = self.slow_seconds
        download_slots = 1

        async def start(spider):
            assert len(start_nums) > 1
            for num in start_nums[:-1]:
                yield self._request(num, response_seconds, download_slots)
                await sleep(response_seconds * 2)
            yield self._request(start_nums[-1], response_seconds, download_slots)

        await maybe_deferred_to_future(
            self._test_request_order(
                start_nums=start_nums,
                cb_nums=cb_nums,
                settings={"CONCURRENT_REQUESTS": 2},
                response_seconds=response_seconds,
                start_fn=start,
            )
        )

    # Examples from the “Start requests” section of the documentation about
    # spiders.

    @pytest.mark.only_asyncio
    @deferred_f_from_coro_f
    async def test_ar_start_requests_first(self):
        start_nums = [1, 3, 2]
        cb_nums = [4]
        response_seconds = self.slow_seconds
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

    @pytest.mark.only_not_asyncio
    @deferred_f_from_coro_f
    async def test_dr_start_requests_first(self):
        start_nums = [3, 2, 1]
        cb_nums = [4]
        response_seconds = self.slow_seconds
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
        response_seconds = self.slow_seconds
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
