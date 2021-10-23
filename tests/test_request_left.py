from twisted.internet import defer
from twisted.trial.unittest import TestCase
from scrapy.signals import request_left_downloader
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler
from tests.mockserver import MockServer


class SignalCatcherSpider(Spider):
    name = 'signal_catcher'

    def __init__(self, crawler, url, *args, **kwargs):
        super().__init__(*args, **kwargs)
        crawler.signals.connect(self.on_request_left,
                                signal=request_left_downloader)
        self.caught_times = 0
        self.start_urls = [url]

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = cls(crawler, *args, **kwargs)
        return spider

    def on_request_left(self, request, spider):
        self.caught_times = self.caught_times + 1


class TestCatching(TestCase):

    def setUp(self):
        self.mockserver = MockServer()
        self.mockserver.__enter__()

    def tearDown(self):
        self.mockserver.__exit__(None, None, None)

    @defer.inlineCallbacks
    def test_success(self):
        crawler = get_crawler(SignalCatcherSpider)
        yield crawler.crawl(self.mockserver.url("/status?n=200"))
        self.assertEqual(crawler.spider.caught_times, 1)

    @defer.inlineCallbacks
    def test_timeout(self):
        crawler = get_crawler(SignalCatcherSpider,
                              {'DOWNLOAD_TIMEOUT': 0.1})
        yield crawler.crawl(self.mockserver.url("/delay?n=0.2"))
        self.assertEqual(crawler.spider.caught_times, 1)

    @defer.inlineCallbacks
    def test_disconnect(self):
        crawler = get_crawler(SignalCatcherSpider)
        yield crawler.crawl(self.mockserver.url("/drop"))
        self.assertEqual(crawler.spider.caught_times, 1)

    @defer.inlineCallbacks
    def test_noconnect(self):
        crawler = get_crawler(SignalCatcherSpider)
        yield crawler.crawl('http://thereisdefinetelynosuchdomain.com')
        self.assertEqual(crawler.spider.caught_times, 1)
