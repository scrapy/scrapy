from __future__ import annotations

from collections import deque
from logging import ERROR

from testfixtures import LogCapture
from twisted.trial.unittest import TestCase

from scrapy import Request, SeedingPolicy, Spider, signals
from scrapy.core.engine import ExecutionEngine
from scrapy.utils.defer import deferred_f_from_coro_f, maybe_deferred_to_future
from scrapy.utils.test import get_crawler
from tests.test_scheduler import MemoryScheduler, PriorityScheduler

from .mockserver import MockServer


class MainTestCase(TestCase):
    # If the test ends before the heartbeat, it may mean that the logic to
    # re-schecule a new call of _start_next_requests under the right
    # ciscumstances is not properly implemented, and the hearatbeat is working
    # as a workaround for that issue. This is a performance issue and should
    # be addressed.
    #
    # It could also happen that, on some CI runners, some tests (e.g. those
    # below using a mock server) run too slow and proper handling overlaps with
    # the heartbeat. If that is the case, it may be worth considering
    # increasing the heartbeat time. It should be safe, since in most real live
    # scenarios the heartbeat should never make a difference, and we may
    # eventually remove the heartbeat altogether.
    timeout = ExecutionEngine._SLOT_HEARTBEAT_INTERVAL

    @deferred_f_from_coro_f
    async def test_greedy(self):
        class TestScheduler(MemoryScheduler):
            queue = ["data:,b"]

        class TestSpider(Spider):
            name = "test"
            start_urls = ["data:,a"]

            def parse(self, response):
                pass

        actual_urls = []

        def track_url(request, spider):
            actual_urls.append(request.url)

        settings = {"SCHEDULER": TestScheduler}
        crawler = get_crawler(TestSpider, settings_dict=settings)
        crawler.signals.connect(track_url, signals.request_reached_downloader)
        await maybe_deferred_to_future(crawler.crawl())
        assert crawler.stats.get_value("finish_reason") == "finished"
        expected_urls = ["data:,a", "data:,b"]
        assert actual_urls == expected_urls, f"{actual_urls=} != {expected_urls=}"

    @deferred_f_from_coro_f
    async def test_lazy(self):
        class TestScheduler(MemoryScheduler):
            queue = ["data:,a"]

        class TestSpider(Spider):
            name = "test"
            start_urls = ["data:,b"]

            def parse(self, response):
                pass

        actual_urls = []

        def track_url(request, spider):
            actual_urls.append(request.url)

        settings = {"SCHEDULER": TestScheduler, "SEEDING_POLICY": "lazy"}
        crawler = get_crawler(TestSpider, settings_dict=settings)
        crawler.signals.connect(track_url, signals.request_reached_downloader)
        await maybe_deferred_to_future(crawler.crawl())
        assert crawler.stats.get_value("finish_reason") == "finished"
        expected_urls = ["data:,a", "data:,b"]
        assert actual_urls == expected_urls, f"{actual_urls=} != {expected_urls=}"

    @deferred_f_from_coro_f
    async def test_lazy_blocking(self):
        """If the scheduler reports having requests but yields none, the lazy
        policy schedules requests from seeds."""

        class TestScheduler(MemoryScheduler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.stop = False

            def has_pending_requests(self) -> bool:
                return not self.stop

        class TestSpider(Spider):
            name = "test"

            async def yield_seeds(self):
                self.crawler.engine._slot.scheduler.enqueue_request(Request("data:,b"))
                yield Request("data:,a")
                yield Request("data:,c")
                self.crawler.engine._slot.scheduler.stop = True

            def parse(self, response):
                pass

        actual_urls = []

        def track_url(request, spider):
            actual_urls.append(request.url)

        settings = {"SCHEDULER": TestScheduler, "SEEDING_POLICY": "lazy"}
        crawler = get_crawler(TestSpider, settings_dict=settings)
        crawler.signals.connect(track_url, signals.request_reached_downloader)
        with LogCapture() as log:
            await maybe_deferred_to_future(crawler.crawl())
        assert crawler.stats.get_value("finish_reason") == "finished"
        expected_urls = ["data:,a", "data:,b", "data:,c"]
        assert actual_urls == expected_urls, (
            f"{actual_urls=} != {expected_urls=}\n{log}"
        )

    @deferred_f_from_coro_f
    async def test_lazy_seed_order(self):
        """By default, seed requests should be sent in the order in which they
        are iterated."""

        class TestSpider(Spider):
            name = "test"
            start_urls = ["data:,a", "data:,b", "data:,c"]

            def parse(self, response):
                pass

        actual_urls = []

        def track_url(request, spider):
            actual_urls.append(request.url)

        settings = {"SEEDING_POLICY": "lazy"}
        crawler = get_crawler(TestSpider, settings_dict=settings)
        crawler.signals.connect(track_url, signals.request_reached_downloader)
        await maybe_deferred_to_future(crawler.crawl())
        assert crawler.stats.get_value("finish_reason") == "finished"
        expected_urls = ["data:,a", "data:,b", "data:,c"]
        assert actual_urls == expected_urls, f"{actual_urls=} != {expected_urls=}"

    @deferred_f_from_coro_f
    async def test_front_load(self):
        class TestSpider(Spider):
            name = "test"

            async def yield_seeds(self):
                yield Request("data:,b", priority=0)
                yield Request("data:,a", priority=1)

            def parse(self, response):
                pass

        actual_urls = []

        def track_url(request, spider):
            actual_urls.append(request.url)

        settings = {"SCHEDULER": PriorityScheduler, "SEEDING_POLICY": "front_load"}
        crawler = get_crawler(TestSpider, settings_dict=settings)
        crawler.signals.connect(track_url, signals.request_reached_downloader)
        await maybe_deferred_to_future(crawler.crawl())
        assert crawler.stats.get_value("finish_reason") == "finished"
        expected_urls = ["data:,a", "data:,b"]
        assert actual_urls == expected_urls, f"{actual_urls=} != {expected_urls=}"

    @deferred_f_from_coro_f
    async def test_override(self):
        class TestSpider(Spider):
            name = "test"

            async def yield_seeds(self):
                yield "front-load"  # typo
                yield SeedingPolicy.front_load
                yield Request("data:,b", priority=1)
                yield Request("data:,a", priority=2)
                yield self.crawler.settings["SEEDING_POLICY"]
                yield Request("data:,c", priority=3)

            def parse(self, response):
                pass

        actual_items = []
        actual_urls = []

        def track_item(item, response, spider):
            actual_items.append(item)

        def track_url(request, spider):
            actual_urls.append(request.url)

        settings = {"SCHEDULER": PriorityScheduler, "SEEDING_POLICY": "lazy"}
        crawler = get_crawler(TestSpider, settings_dict=settings)
        crawler.signals.connect(track_item, signals.item_scraped)
        crawler.signals.connect(track_url, signals.request_reached_downloader)
        with LogCapture(level=ERROR) as log:
            await maybe_deferred_to_future(crawler.crawl())
        assert len(log.records) == 1
        assert "must be valid seeding policies" in str(log.records[0])
        assert crawler.stats.get_value("finish_reason") == "finished"
        assert not actual_items, (
            f"{actual_items=} should be empty, policies are not items"
        )
        expected_urls = ["data:,a", "data:,b", "data:,c"]
        assert actual_urls == expected_urls, f"{actual_urls=} != {expected_urls=}"


class MockServerTestCase(TestCase):
    # See the comment on the matching line above.
    timeout = ExecutionEngine._SLOT_HEARTBEAT_INTERVAL
    # If requests are too fast, test_idle will fail because the outcome will
    # match that of the lazy seeding policy.
    delay = 0.2

    @classmethod
    def setUpClass(cls):
        cls.mockserver = MockServer()
        cls.mockserver.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.mockserver.__exit__(None, None, None)

    @deferred_f_from_coro_f
    async def test_idle(self):
        def _url(id):
            return self.mockserver.url(f"/delay?n={self.delay}&{id}")

        class TestScheduler(MemoryScheduler):
            queue = [_url("a")]

        class TestSpider(Spider):
            name = "test"
            start_urls = [_url("b"), _url("d")]
            queue = deque([_url("c")])

            def parse(self, response):
                try:
                    url = self.queue.popleft()
                except IndexError:
                    pass
                else:
                    yield Request(url)

        actual_urls = []

        def track_url(request, spider):
            actual_urls.append(request.url)

        settings = {"SCHEDULER": TestScheduler, "SEEDING_POLICY": "idle"}
        crawler = get_crawler(TestSpider, settings_dict=settings)
        crawler.signals.connect(track_url, signals.request_reached_downloader)
        await maybe_deferred_to_future(crawler.crawl())
        assert crawler.stats.get_value("finish_reason") == "finished"
        expected_urls = [_url(letter) for letter in "abcd"]
        assert actual_urls == expected_urls, f"{actual_urls=} != {expected_urls=}"
