from twisted.internet import defer
from twisted.trial.unittest import TestCase
from scrapy.utils.test import get_crawler
from tests.spiders import FollowAllSpider, ItemSpider, ErrorSpider
from tests.mockserver import MockServer


class TestCloseSpider(TestCase):

    def setUp(self):
        self.mockserver = MockServer()
        self.mockserver.__enter__()

    def tearDown(self):
        self.mockserver.__exit__(None, None, None)

    @defer.inlineCallbacks
    def test_closespider_itemcount(self):
        close_on = 5
        crawler = get_crawler(ItemSpider, {'CLOSESPIDER_ITEMCOUNT': close_on})
        yield crawler.crawl()
        reason = crawler.spider.meta['close_reason']
        self.assertEqual(reason, 'closespider_itemcount')
        itemcount = crawler.stats.get_value('item_scraped_count')
        self.assertTrue(itemcount >= close_on)

    @defer.inlineCallbacks
    def test_closespider_pagecount(self):
        close_on = 5
        crawler = get_crawler(FollowAllSpider, {'CLOSESPIDER_PAGECOUNT': close_on})
        yield crawler.crawl()
        reason = crawler.spider.meta['close_reason']
        self.assertEqual(reason, 'closespider_pagecount')
        pagecount = crawler.stats.get_value('response_received_count')
        self.assertTrue(pagecount >= close_on)

    @defer.inlineCallbacks
    def test_closespider_errorcount(self):
        close_on = 5
        crawler = get_crawler(ErrorSpider, {'CLOSESPIDER_ERRORCOUNT': close_on})
        yield crawler.crawl(total=1000000)
        self.flushLoggedErrors(crawler.spider.exception_cls)
        reason = crawler.spider.meta['close_reason']
        self.assertEqual(reason, 'closespider_errorcount')
        key = 'spider_exceptions/{name}'\
                .format(name=crawler.spider.exception_cls.__name__)
        errorcount = crawler.stats.get_value(key)
        self.assertTrue(errorcount >= close_on)

    @defer.inlineCallbacks
    def test_closespider_timeout(self):
        close_on = 0.1
        crawler = get_crawler(FollowAllSpider, {'CLOSESPIDER_TIMEOUT': close_on})
        yield crawler.crawl(total=1000000)
        reason = crawler.spider.meta['close_reason']
        self.assertEqual(reason, 'closespider_timeout')
        stats = crawler.stats
        start = stats.get_value('start_time')
        stop = stats.get_value('finish_time')
        diff = stop - start
        total_seconds = diff.seconds + diff.microseconds
        self.assertTrue(total_seconds >= close_on)
