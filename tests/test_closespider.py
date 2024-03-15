from twisted.internet import defer
from twisted.trial.unittest import TestCase

from scrapy.utils.test import get_crawler
from tests.mockserver import MockServer
from tests.spiders import (
    CloseExceptionParseSpider,
    CloseExceptionStartSpider,
    ErrorSpider,
    FollowAllSpider,
    ItemSpider,
    SlowSpider,
)


class TestCloseSpider(TestCase):
    def setUp(self):
        self.mockserver = MockServer()
        self.mockserver.__enter__()

    def tearDown(self):
        self.mockserver.__exit__(None, None, None)

    @defer.inlineCallbacks
    def test_closespider_itemcount(self):
        close_on = 5
        crawler = get_crawler(ItemSpider, {"CLOSESPIDER_ITEMCOUNT": close_on})
        yield crawler.crawl(mockserver=self.mockserver)
        reason = crawler.spider.meta["close_reason"]
        self.assertEqual(reason, "closespider_itemcount")
        itemcount = crawler.stats.get_value("item_scraped_count")
        self.assertTrue(itemcount >= close_on)

    @defer.inlineCallbacks
    def test_closespider_pagecount(self):
        close_on = 5
        crawler = get_crawler(FollowAllSpider, {"CLOSESPIDER_PAGECOUNT": close_on})
        yield crawler.crawl(mockserver=self.mockserver)
        reason = crawler.spider.meta["close_reason"]
        self.assertEqual(reason, "closespider_pagecount")
        pagecount = crawler.stats.get_value("response_received_count")
        self.assertTrue(pagecount >= close_on)

    @defer.inlineCallbacks
    def test_closespider_errorcount(self):
        close_on = 5
        crawler = get_crawler(ErrorSpider, {"CLOSESPIDER_ERRORCOUNT": close_on})
        yield crawler.crawl(total=1000000, mockserver=self.mockserver)
        reason = crawler.spider.meta["close_reason"]
        self.assertEqual(reason, "closespider_errorcount")
        key = f"spider_exceptions/{crawler.spider.exception_cls.__name__}"
        errorcount = crawler.stats.get_value(key)
        self.assertTrue(errorcount >= close_on)

    @defer.inlineCallbacks
    def test_closespider_timeout(self):
        close_on = 0.1
        crawler = get_crawler(FollowAllSpider, {"CLOSESPIDER_TIMEOUT": close_on})
        yield crawler.crawl(total=1000000, mockserver=self.mockserver)
        reason = crawler.spider.meta["close_reason"]
        self.assertEqual(reason, "closespider_timeout")
        total_seconds = crawler.stats.get_value("elapsed_time_seconds")
        self.assertTrue(total_seconds >= close_on)

    @defer.inlineCallbacks
    def test_closespider_timeout_no_item(self):
        timeout = 1
        crawler = get_crawler(SlowSpider, {"CLOSESPIDER_TIMEOUT_NO_ITEM": timeout})
        yield crawler.crawl(n=3, mockserver=self.mockserver)
        reason = crawler.spider.meta["close_reason"]
        self.assertEqual(reason, "closespider_timeout_no_item")
        total_seconds = crawler.stats.get_value("elapsed_time_seconds")
        self.assertTrue(total_seconds >= timeout)

    @defer.inlineCallbacks
    def test_closespider_exception_handler(self):
        expected_message_parse = "Raised on parse."
        crawler_parse = get_crawler(CloseExceptionParseSpider)
        yield crawler_parse.crawl(
            mockserver=self.mockserver, expected_message=expected_message_parse
        )
        reason_parse = crawler_parse.spider.meta["close_reason"]
        self.assertEqual(reason_parse, expected_message_parse)

        expected_message_start = "Raised on start."
        crawler_start = get_crawler(CloseExceptionStartSpider)
        yield crawler_start.crawl(
            mockserver=self.mockserver, expected_message=expected_message_start
        )
        reason_start = crawler_start.spider.meta["close_reason"]
        self.assertEqual(reason_start, expected_message_start)
