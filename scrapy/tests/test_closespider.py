from twisted.internet import defer
from twisted.trial.unittest import TestCase
from scrapy.utils.test import docrawl
from scrapy.tests.spiders import FollowAllSpider, ItemSpider, ErrorSpider
from scrapy.tests.mockserver import MockServer


class TestCloseSpider(TestCase):

    def setUp(self):
        self.mockserver = MockServer()
        self.mockserver.__enter__()

    def tearDown(self):
        self.mockserver.__exit__(None, None, None)

    @defer.inlineCallbacks
    def test_closespider_itemcount(self):
        spider = ItemSpider()
        close_on = 5
        yield docrawl(spider, {'CLOSESPIDER_ITEMCOUNT': close_on})
        reason = spider.meta['close_reason']
        self.assertEqual(reason, 'closespider_itemcount')
        itemcount = spider.crawler.stats.get_value('item_scraped_count')
        self.assertTrue(itemcount >= close_on)

    @defer.inlineCallbacks
    def test_closespider_pagecount(self):
        spider = FollowAllSpider()
        close_on = 5
        yield docrawl(spider, {'CLOSESPIDER_PAGECOUNT': close_on})
        reason = spider.meta['close_reason']
        self.assertEqual(reason, 'closespider_pagecount')
        pagecount = spider.crawler.stats.get_value('response_received_count')
        self.assertTrue(pagecount >= close_on)

    @defer.inlineCallbacks
    def test_closespider_errorcount(self):
        spider = ErrorSpider(total=1000000)
        close_on = 5
        yield docrawl(spider, {'CLOSESPIDER_ERRORCOUNT': close_on})
        self.flushLoggedErrors(spider.exception_cls)
        reason = spider.meta['close_reason']
        self.assertEqual(reason, 'closespider_errorcount')
        key = 'spider_exceptions/{name}'\
                .format(name=spider.exception_cls.__name__)
        errorcount = spider.crawler.stats.get_value(key)
        self.assertTrue(errorcount >= close_on)

    @defer.inlineCallbacks
    def test_closespider_timeout(self):
        spider = FollowAllSpider(total=1000000)
        close_on = 0.1
        yield docrawl(spider, {'CLOSESPIDER_TIMEOUT': close_on})
        reason = spider.meta['close_reason']
        self.assertEqual(reason, 'closespider_timeout')
        stats = spider.crawler.stats
        start = stats.get_value('start_time')
        stop = stats.get_value('finish_time')
        diff = stop - start
        total_seconds = diff.seconds + diff.microseconds
        self.assertTrue(total_seconds >= close_on)
