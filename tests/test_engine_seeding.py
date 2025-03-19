from __future__ import annotations

from collections import deque

from twisted.internet.defer import inlineCallbacks
from twisted.trial.unittest import TestCase

from scrapy import Request, Spider, signals
from scrapy.core.scheduler import BaseScheduler
from scrapy.utils.defer import maybe_deferred_to_future
from scrapy.utils.test import get_crawler

from .test_spider_start import twisted_sleep


class MainTestCase(TestCase):
    @inlineCallbacks
    def test_scheduler_priority_over_seeds_simple(self):
        """Scrapy reads seeds into the scheduler while the scheduler is empty,
        but otherwise prioritizes requests already in the scheduler.

        This test shows how, given a scheduler pre-filled with a request, that
        request is sent before sending the first seed request.
        """

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
        yield crawler.crawl()
        assert crawler.stats.get_value("finish_reason") == "finished"
        expected_urls = ["data:,a", "data:,b"]
        assert actual_urls == expected_urls, f"{actual_urls=} != {expected_urls=}"

    @inlineCallbacks
    def test_scheduler_priority_over_seeds_complex(self):
        """Although Scrapy reads seeds into the scheduler while the scheduler
        is empty and otherwise prioritizes requests already in the scheduler,
        this is done in a non-blocking way.

        That is, if the scheduler reports having requests but yields none,
        requests from seeds will be scheduled.
        """

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

            async def start(self):
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
        yield crawler.crawl()
        assert crawler.stats.get_value("finish_reason") == "finished"
        expected_urls = ["data:,a", "data:,b", "data:,c"]
        assert actual_urls == expected_urls, f"{actual_urls=} != {expected_urls=}"
