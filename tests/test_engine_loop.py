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
    # See the comment on the matching line above.
    timeout = ExecutionEngine._SLOT_HEARTBEAT_INTERVAL

    @classmethod
    def setUpClass(cls):
        cls.mockserver = MockServer()
        cls.mockserver.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.mockserver.__exit__(None, None, None)

    @deferred_f_from_coro_f
    async def test_default_behavior(self):
        """Verify the behavior that the docs claims is the default when it
        comes to start request send order."""
        seconds = 0.1

        def _url(id, delay=seconds):
            return self.mockserver.url(f"/delay?n={seconds}&{id}")

        class TestSpider(Spider):
            name = "test"
            start_urls = [_url("a", delay=0), _url("b"), _url("d"), _url("e")]
            queue = deque([Request(_url("c"))])

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

        settings = {"CONCURRENT_REQUESTS": 2}
        crawler = get_crawler(TestSpider, settings_dict=settings)
        crawler.signals.connect(track_url, signals.request_reached_downloader)
        await maybe_deferred_to_future(crawler.crawl())
        assert crawler.stats.get_value("finish_reason") == "finished"
        expected_urls = [_url(letter) for letter in "abcd"]
        assert actual_urls == expected_urls, f"{actual_urls=} != {expected_urls=}"
