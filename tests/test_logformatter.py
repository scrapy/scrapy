import unittest

from testfixtures import LogCapture
from twisted.internet import defer
from twisted.python.failure import Failure
from twisted.trial.unittest import TestCase as TwistedTestCase

from scrapy.crawler import CrawlerRunner
from scrapy.exceptions import DropItem
from scrapy.http import Request, Response
from scrapy.item import Item, Field
from scrapy.logformatter import LogFormatter
from scrapy.spiders import Spider
from tests.mockserver import MockServer
from tests.spiders import ItemSpider


class CustomItem(Item):

    name = Field()

    def __str__(self):
        return "name: %s" % self['name']


class LogFormatterTestCase(unittest.TestCase):

    def setUp(self):
        self.formatter = LogFormatter()
        self.spider = Spider('default')

    def test_crawled_with_referer(self):
        req = Request("http://www.example.com")
        res = Response("http://www.example.com")
        logkws = self.formatter.crawled(req, res, self.spider)
        logline = logkws['msg'] % logkws['args']
        self.assertEqual(logline, "Crawled (200) <GET http://www.example.com> (referer: None)")

    def test_crawled_without_referer(self):
        req = Request("http://www.example.com", headers={'referer': 'http://example.com'})
        res = Response("http://www.example.com", flags=['cached'])
        logkws = self.formatter.crawled(req, res, self.spider)
        logline = logkws['msg'] % logkws['args']
        self.assertEqual(
            logline,
            "Crawled (200) <GET http://www.example.com> (referer: http://example.com) ['cached']")

    def test_flags_in_request(self):
        req = Request("http://www.example.com", flags=['test', 'flag'])
        res = Response("http://www.example.com")
        logkws = self.formatter.crawled(req, res, self.spider)
        logline = logkws['msg'] % logkws['args']
        self.assertEqual(
            logline,
            "Crawled (200) <GET http://www.example.com> ['test', 'flag'] (referer: None)")

    def test_dropped(self):
        item = {}
        exception = Exception("\u2018")
        response = Response("http://www.example.com")
        logkws = self.formatter.dropped(item, exception, response, self.spider)
        logline = logkws['msg'] % logkws['args']
        lines = logline.splitlines()
        assert all(isinstance(x, str) for x in lines)
        self.assertEqual(lines, ["Dropped: \u2018", '{}'])

    def test_item_error(self):
        # In practice, the complete traceback is shown by passing the
        # 'exc_info' argument to the logging function
        item = {'key': 'value'}
        exception = Exception()
        response = Response("http://www.example.com")
        logkws = self.formatter.item_error(item, exception, response, self.spider)
        logline = logkws['msg'] % logkws['args']
        self.assertEqual(logline, "Error processing {'key': 'value'}")

    def test_spider_error(self):
        # In practice, the complete traceback is shown by passing the
        # 'exc_info' argument to the logging function
        failure = Failure(Exception())
        request = Request("http://www.example.com", headers={'Referer': 'http://example.org'})
        response = Response("http://www.example.com", request=request)
        logkws = self.formatter.spider_error(failure, request, response, self.spider)
        logline = logkws['msg'] % logkws['args']
        self.assertEqual(
            logline,
            "Spider error processing <GET http://www.example.com> (referer: http://example.org)"
        )

    def test_download_error_short(self):
        # In practice, the complete traceback is shown by passing the
        # 'exc_info' argument to the logging function
        failure = Failure(Exception())
        request = Request("http://www.example.com")
        logkws = self.formatter.download_error(failure, request, self.spider)
        logline = logkws['msg'] % logkws['args']
        self.assertEqual(logline, "Error downloading <GET http://www.example.com>")

    def test_download_error_long(self):
        # In practice, the complete traceback is shown by passing the
        # 'exc_info' argument to the logging function
        failure = Failure(Exception())
        request = Request("http://www.example.com")
        logkws = self.formatter.download_error(failure, request, self.spider, "Some message")
        logline = logkws['msg'] % logkws['args']
        self.assertEqual(logline, "Error downloading <GET http://www.example.com>: Some message")

    def test_scraped(self):
        item = CustomItem()
        item['name'] = '\xa3'
        response = Response("http://www.example.com")
        logkws = self.formatter.scraped(item, response, self.spider)
        logline = logkws['msg'] % logkws['args']
        lines = logline.splitlines()
        assert all(isinstance(x, str) for x in lines)
        self.assertEqual(lines, ["Scraped from <200 http://www.example.com>", 'name: \xa3'])


class LogFormatterSubclass(LogFormatter):
    def crawled(self, request, response, spider):
        kwargs = super(LogFormatterSubclass, self).crawled(request, response, spider)
        CRAWLEDMSG = (
            "Crawled (%(status)s) %(request)s (referer: %(referer)s) %(flags)s"
        )
        log_args = kwargs['args']
        log_args['flags'] = str(request.flags)
        return {
            'level': kwargs['level'],
            'msg': CRAWLEDMSG,
            'args': log_args,
        }


class LogformatterSubclassTest(LogFormatterTestCase):
    def setUp(self):
        self.formatter = LogFormatterSubclass()
        self.spider = Spider('default')

    def test_crawled_with_referer(self):
        req = Request("http://www.example.com")
        res = Response("http://www.example.com")
        logkws = self.formatter.crawled(req, res, self.spider)
        logline = logkws['msg'] % logkws['args']
        self.assertEqual(
            logline,
            "Crawled (200) <GET http://www.example.com> (referer: None) []")

    def test_crawled_without_referer(self):
        req = Request("http://www.example.com", headers={'referer': 'http://example.com'}, flags=['cached'])
        res = Response("http://www.example.com")
        logkws = self.formatter.crawled(req, res, self.spider)
        logline = logkws['msg'] % logkws['args']
        self.assertEqual(
            logline,
            "Crawled (200) <GET http://www.example.com> (referer: http://example.com) ['cached']")

    def test_flags_in_request(self):
        req = Request("http://www.example.com", flags=['test', 'flag'])
        res = Response("http://www.example.com")
        logkws = self.formatter.crawled(req, res, self.spider)
        logline = logkws['msg'] % logkws['args']
        self.assertEqual(
            logline,
            "Crawled (200) <GET http://www.example.com> (referer: None) ['test', 'flag']")


class SkipMessagesLogFormatter(LogFormatter):
    def crawled(self, *args, **kwargs):
        return None

    def scraped(self, *args, **kwargs):
        return None

    def dropped(self, *args, **kwargs):
        return None


class DropSomeItemsPipeline:
    drop = True

    def process_item(self, item, spider):
        if self.drop:
            self.drop = False
            raise DropItem("Ignoring item")
        else:
            self.drop = True


class ShowOrSkipMessagesTestCase(TwistedTestCase):
    def setUp(self):
        self.mockserver = MockServer()
        self.mockserver.__enter__()
        self.base_settings = {
            'LOG_LEVEL': 'DEBUG',
            'ITEM_PIPELINES': {
                __name__ + '.DropSomeItemsPipeline': 300,
            },
        }

    def tearDown(self):
        self.mockserver.__exit__(None, None, None)

    @defer.inlineCallbacks
    def test_show_messages(self):
        crawler = CrawlerRunner(self.base_settings).create_crawler(ItemSpider)
        with LogCapture() as lc:
            yield crawler.crawl(mockserver=self.mockserver)
        self.assertIn("Scraped from <200 http://127.0.0.1:", str(lc))
        self.assertIn("Crawled (200) <GET http://127.0.0.1:", str(lc))
        self.assertIn("Dropped: Ignoring item", str(lc))

    @defer.inlineCallbacks
    def test_skip_messages(self):
        settings = self.base_settings.copy()
        settings['LOG_FORMATTER'] = __name__ + '.SkipMessagesLogFormatter'
        crawler = CrawlerRunner(settings).create_crawler(ItemSpider)
        with LogCapture() as lc:
            yield crawler.crawl(mockserver=self.mockserver)
        self.assertNotIn("Scraped from <200 http://127.0.0.1:", str(lc))
        self.assertNotIn("Crawled (200) <GET http://127.0.0.1:", str(lc))
        self.assertNotIn("Dropped: Ignoring item", str(lc))


if __name__ == "__main__":
    unittest.main()
