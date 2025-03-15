from __future__ import annotations

from collections import deque
from logging import ERROR

from testfixtures import LogCapture
from twisted.internet.defer import Deferred
from twisted.trial.unittest import TestCase

from scrapy import Request, SeedingPolicy, Spider, signals
from scrapy.core.engine import ExecutionEngine
from scrapy.utils.defer import deferred_f_from_coro_f, maybe_deferred_to_future
from scrapy.utils.test import get_crawler
from tests.test_scheduler import MemoryScheduler, PriorityScheduler

from .mockserver import MockServer


def sleep(seconds: float = ExecutionEngine._MIN_BACK_IN_SECONDS):
    from twisted.internet import reactor

    deferred = Deferred()
    reactor.callLater(seconds, deferred.callback, None)
    return maybe_deferred_to_future(deferred)


class MainTestCase(TestCase):
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
    async def test_greedy_sleep(self):
        """If the seeds sleep long enough, scheduler requests should be
        processed in the meantime."""

        class TestScheduler(MemoryScheduler):
            queue = ["data:,b"]

        class TestSpider(Spider):
            name = "test"

            async def yield_seeds(self):
                yield Request("data:,a")
                await sleep(ExecutionEngine._MIN_BACK_IN_SECONDS * 2)
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
        assert actual_urls == expected_urls, (
            f"{actual_urls=} != {expected_urls=}\n{log}"
        )

    @deferred_f_from_coro_f
    async def test_greedy_scheduler_sleep(self):
        """If the scheduler sleeps but not longer than the seeds, its
        processing should resume before that of the seeds, instead of being
        blocked by the seeds finishing processing."""

        class TestScheduler(MemoryScheduler):
            pause = True
            queue = ["data:,a"]

        class TestSpider(Spider):
            name = "test"

            async def yield_seeds(self):
                seconds = ExecutionEngine._MIN_BACK_IN_SECONDS
                await sleep(seconds)
                self.crawler.engine._slot.scheduler.pause = False
                await sleep(seconds)
                yield Request("data:,b")

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
        expected_urls = ["data:,a", "data:,b"]
        assert actual_urls == expected_urls, (
            f"{actual_urls=} != {expected_urls=}\n{log}"
        )

    @deferred_f_from_coro_f
    async def test_greedy_exception(self):
        """If the seeds raise an unhandled exception, scheduler requests should
        still be processed."""

        class TestScheduler(MemoryScheduler):
            queue = ["data:,b"]

        class TestSpider(Spider):
            name = "test"

            async def yield_seeds(self):
                yield Request("data:,a")
                raise RuntimeError

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
        expected_urls = ["data:,a", "data:,b"]
        assert actual_urls == expected_urls, (
            f"{actual_urls=} != {expected_urls=}\n{log}"
        )

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
    async def test_lazy_sleep(self):
        """If the scheduler reports having requests but yields none, the lazy
        policy schedules requests from seeds."""

        class TestScheduler(MemoryScheduler):
            queue = ["data:,b"]
            pause = True

        class TestSpider(Spider):
            name = "test"

            async def yield_seeds(self):
                self.crawler.engine._slot.scheduler.pause = False
                yield Request("data:,a")
                yield Request("data:,c")

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
            start_urls = ["data:,c"]

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
        assert actual_urls == expected_urls, f"{actual_urls=} != {expected_urls=}"
        assert "in next_request\n    raise request" in str(log), log


class MockServerTestCase(TestCase):
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
