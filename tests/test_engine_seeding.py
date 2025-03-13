from __future__ import annotations

from collections import defaultdict, deque

from twisted.trial.unittest import TestCase

from scrapy import Request, Spider, signals
from scrapy.core.engine import ExecutionEngine
from scrapy.core.scheduler import BaseScheduler
from scrapy.utils.defer import deferred_f_from_coro_f, maybe_deferred_to_future
from scrapy.utils.test import get_crawler

from .mockserver import MockServer
from .test_spider_yield_seeds import twisted_sleep


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
    async def test_lazy(self):
        class TestScheduler(BaseScheduler):
            def __init__(self, *args, **kwargs):
                self.requests = deque((Request("data:,a"),))

            def enqueue_request(self, request: Request) -> bool:
                self.requests.append(request)
                return True

            def has_pending_requests(self) -> bool:
                return bool(self.requests)

            def next_request(self) -> Request | None:
                try:
                    return self.requests.popleft()
                except IndexError:
                    return None

        class TestSpider(Spider):
            name = "test"
            start_urls = ["data:,b"]

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
    async def test_lazy_blocking(self):
        """If the scheduler reports having requests but yields none, the lazy
        policy schedules requests from seeds."""

        class TestScheduler(BaseScheduler):
            def __init__(self, *args, **kwargs):
                self.requests = deque()
                self.stop = False

            def enqueue_request(self, request: Request) -> bool:
                self.requests.append(request)
                return True

            def has_pending_requests(self) -> bool:
                return not self.stop

            def next_request(self) -> Request | None:
                try:
                    return self.requests.popleft()
                except IndexError:
                    return None

        sleep_seconds = 0.0001

        class TestSpider(Spider):
            name = "test"

            async def yield_seeds(self):
                await maybe_deferred_to_future(twisted_sleep(sleep_seconds))
                yield Request("data:,a")
                await maybe_deferred_to_future(twisted_sleep(sleep_seconds))
                self.crawler.engine._slot.scheduler.enqueue_request(Request("data:,b"))
                await maybe_deferred_to_future(twisted_sleep(sleep_seconds))
                yield Request("data:,c")
                self.crawler.engine._slot.scheduler.stop = True

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
        expected_urls = ["data:,a", "data:,b", "data:,c"]
        assert actual_urls == expected_urls, f"{actual_urls=} != {expected_urls=}"

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

        crawler = get_crawler(TestSpider)
        crawler.signals.connect(track_url, signals.request_reached_downloader)
        await maybe_deferred_to_future(crawler.crawl())
        assert crawler.stats.get_value("finish_reason") == "finished"
        expected_urls = ["data:,a", "data:,b", "data:,c"]
        assert actual_urls == expected_urls, f"{actual_urls=} != {expected_urls=}"

    @deferred_f_from_coro_f
    async def test_greedy(self):
        class TestScheduler(BaseScheduler):
            def __init__(self, *args, **kwargs):
                self.requests = deque((Request("data:,b"),))

            def enqueue_request(self, request: Request) -> bool:
                self.requests.append(request)
                return True

            def has_pending_requests(self) -> bool:
                return bool(self.requests)

            def next_request(self) -> Request | None:
                try:
                    return self.requests.pop()
                except IndexError:
                    return None

        class TestSpider(Spider):
            name = "test"
            start_urls = ["data:,a"]

            def parse(self, response):
                pass

        actual_urls = []

        def track_url(request, spider):
            actual_urls.append(request.url)

        settings = {"SCHEDULER": TestScheduler, "SEEDING_POLICY": "greedy"}
        crawler = get_crawler(TestSpider, settings_dict=settings)
        crawler.signals.connect(track_url, signals.request_reached_downloader)
        await maybe_deferred_to_future(crawler.crawl())
        assert crawler.stats.get_value("finish_reason") == "finished"
        expected_urls = ["data:,a", "data:,b"]
        assert actual_urls == expected_urls, f"{actual_urls=} != {expected_urls=}"

    @deferred_f_from_coro_f
    async def test_front_load(self):
        class TestScheduler(BaseScheduler):
            def __init__(self, *args, **kwargs):
                self.requests = defaultdict(deque)

            def enqueue_request(self, request: Request) -> bool:
                self.requests[request.priority].append(request)
                return True

            def has_pending_requests(self) -> bool:
                return bool(self.requests)

            def next_request(self) -> Request | None:
                if not self.requests:
                    return None
                priority = max(self.requests)
                request = self.requests[priority].popleft()
                if not self.requests[priority]:
                    del self.requests[priority]
                return request

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

        settings = {"SCHEDULER": TestScheduler, "SEEDING_POLICY": "front-load"}
        crawler = get_crawler(TestSpider, settings_dict=settings)
        crawler.signals.connect(track_url, signals.request_reached_downloader)
        await maybe_deferred_to_future(crawler.crawl())
        assert crawler.stats.get_value("finish_reason") == "finished"
        expected_urls = ["data:,a", "data:,b"]
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

        class TestScheduler(BaseScheduler):
            def __init__(self, *args, **kwargs):
                self.requests = deque((Request(_url("a")),))

            def enqueue_request(self, request: Request) -> bool:
                self.requests.append(request)
                return True

            def has_pending_requests(self) -> bool:
                return bool(self.requests)

            def next_request(self) -> Request | None:
                try:
                    return self.requests.popleft()
                except IndexError:
                    return None

        class TestSpider(Spider):
            name = "test"
            start_urls = [_url("b"), _url("d")]
            queue = deque((Request(_url("c")),))

            def parse(self, response):
                try:
                    request = self.queue.popleft()
                except IndexError:
                    pass
                else:
                    yield request

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
