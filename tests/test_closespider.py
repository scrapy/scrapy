from twisted.internet import defer
from twisted.trial.unittest import TestCase

from scrapy import Spider, signals
from scrapy.exceptions import CloseSpider
from scrapy.utils.defer import deferred_f_from_coro_f, maybe_deferred_to_future
from scrapy.utils.test import get_crawler
from tests.mockserver import MockServer
from tests.spiders import (
    ErrorSpider,
    FollowAllSpider,
    ItemSpider,
    MaxItemsAndRequestsSpider,
    SlowSpider,
)


class TestCloseSpider(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mockserver = MockServer()
        cls.mockserver.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.mockserver.__exit__(None, None, None)

    @defer.inlineCallbacks
    def test_closespider_itemcount(self):
        close_on = 5
        crawler = get_crawler(ItemSpider, {"CLOSESPIDER_ITEMCOUNT": close_on})
        yield crawler.crawl(mockserver=self.mockserver)
        reason = crawler.spider.meta["close_reason"]
        assert reason == "closespider_itemcount"
        itemcount = crawler.stats.get_value("item_scraped_count")
        assert itemcount >= close_on

    @defer.inlineCallbacks
    def test_closespider_pagecount(self):
        close_on = 5
        crawler = get_crawler(FollowAllSpider, {"CLOSESPIDER_PAGECOUNT": close_on})
        yield crawler.crawl(mockserver=self.mockserver)
        reason = crawler.spider.meta["close_reason"]
        assert reason == "closespider_pagecount"
        pagecount = crawler.stats.get_value("response_received_count")
        assert pagecount >= close_on

    @defer.inlineCallbacks
    def test_closespider_pagecount_no_item(self):
        close_on = 5
        max_items = 5
        max_requests = close_on + max_items
        crawler = get_crawler(
            MaxItemsAndRequestsSpider,
            {
                "CLOSESPIDER_PAGECOUNT_NO_ITEM": close_on,
            },
        )
        yield crawler.crawl(
            max_items=max_items, max_requests=max_requests, mockserver=self.mockserver
        )
        reason = crawler.spider.meta["close_reason"]
        assert reason == "closespider_pagecount_no_item"
        pagecount = crawler.stats.get_value("response_received_count")
        itemcount = crawler.stats.get_value("item_scraped_count")
        assert pagecount <= close_on + itemcount

    @defer.inlineCallbacks
    def test_closespider_pagecount_no_item_with_pagecount(self):
        close_on_pagecount_no_item = 5
        close_on_pagecount = 20
        crawler = get_crawler(
            FollowAllSpider,
            {
                "CLOSESPIDER_PAGECOUNT_NO_ITEM": close_on_pagecount_no_item,
                "CLOSESPIDER_PAGECOUNT": close_on_pagecount,
            },
        )
        yield crawler.crawl(mockserver=self.mockserver)
        reason = crawler.spider.meta["close_reason"]
        assert reason == "closespider_pagecount_no_item"
        pagecount = crawler.stats.get_value("response_received_count")
        assert pagecount < close_on_pagecount

    @defer.inlineCallbacks
    def test_closespider_errorcount(self):
        close_on = 5
        crawler = get_crawler(ErrorSpider, {"CLOSESPIDER_ERRORCOUNT": close_on})
        yield crawler.crawl(total=1000000, mockserver=self.mockserver)
        reason = crawler.spider.meta["close_reason"]
        assert reason == "closespider_errorcount"
        key = f"spider_exceptions/{crawler.spider.exception_cls.__name__}"
        errorcount = crawler.stats.get_value(key)
        assert errorcount >= close_on

    @defer.inlineCallbacks
    def test_closespider_timeout(self):
        close_on = 0.1
        crawler = get_crawler(FollowAllSpider, {"CLOSESPIDER_TIMEOUT": close_on})
        yield crawler.crawl(total=1000000, mockserver=self.mockserver)
        reason = crawler.spider.meta["close_reason"]
        assert reason == "closespider_timeout"
        total_seconds = crawler.stats.get_value("elapsed_time_seconds")
        assert total_seconds >= close_on

    @defer.inlineCallbacks
    def test_closespider_timeout_no_item(self):
        timeout = 1
        crawler = get_crawler(SlowSpider, {"CLOSESPIDER_TIMEOUT_NO_ITEM": timeout})
        yield crawler.crawl(n=3, mockserver=self.mockserver)
        reason = crawler.spider.meta["close_reason"]
        assert reason == "closespider_timeout_no_item"
        total_seconds = crawler.stats.get_value("elapsed_time_seconds")
        assert total_seconds >= timeout

    @deferred_f_from_coro_f
    async def test_yield_seeds(self):
        class TestSpider(Spider):
            name = "test"

            async def yield_seeds(self):
                raise CloseSpider("foo")
                yield  # pylint: disable=unreachable

        close_reasons = []

        def track_close_reason(spider, reason):
            close_reasons.append(reason)

        crawler = get_crawler(TestSpider)
        crawler.signals.connect(track_close_reason, signal=signals.spider_closed)
        await maybe_deferred_to_future(crawler.crawl())
        assert len(close_reasons) == 1
        assert close_reasons[0] == "foo"

    @deferred_f_from_coro_f
    async def test_callback(self):
        class TestSpider(Spider):
            name = "test"
            start_urls = ["data:,"]

            def parse(self, response):
                raise CloseSpider("foo")

        close_reasons = []

        def track_close_reason(spider, reason):
            close_reasons.append(reason)

        crawler = get_crawler(TestSpider)
        crawler.signals.connect(track_close_reason, signal=signals.spider_closed)
        await maybe_deferred_to_future(crawler.crawl())
        assert len(close_reasons) == 1
        assert close_reasons[0] == "foo"
