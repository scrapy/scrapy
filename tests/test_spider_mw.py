
import logging

from testfixtures import LogCapture
from twisted.trial.unittest import TestCase
from twisted.internet import defer

from scrapy import Spider, Request
from scrapy.utils.test import get_crawler
from tests.mockserver import MockServer


class CommonTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mockserver = MockServer()
        cls.mockserver.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.mockserver.__exit__(None, None, None)

    @defer.inlineCallbacks
    def crawl_log(self, spider):
        crawler = get_crawler(spider)
        with LogCapture() as log:
            yield crawler.crawl()
        raise defer.returnValue(log)


class LogExceptionMiddleware(object):
    def process_spider_exception(self, response, exception, spider):
        logging.warn('Middleware: %s exception caught', exception.__class__.__name__)
        return None


# ================================================================================
# (1) exceptions from a spider middleware's process_spider_input method
class ProcessSpiderInputSpider(Spider):
    name = 'ProcessSpiderInputSpider'
    custom_settings = {
        'SPIDER_MIDDLEWARES': {
            # spider
            __name__ + '.LogExceptionMiddleware': 10,
            __name__ + '.FailProcessSpiderInputMiddleware': 8,
            __name__ + '.LogExceptionMiddleware': 6,
            # engine
        }
    }

    def start_requests(self):
        yield Request('http://localhost:8998', callback=self.parse, errback=self.errback)

    def parse(self, response):
        return [{'test': 1}, {'test': 2}]

    def errback(self, failure):
        self.logger.warn('Got a Failure on the Request errback')


class FailProcessSpiderInputMiddleware:
    def process_spider_input(self, response, spider):
        logging.warn('Middleware: will raise IndexError')
        raise IndexError()


class TestProcessSpiderInput(CommonTestCase):
    @defer.inlineCallbacks
    def test_process_spider_input_errback(self):
        """
        (1) An exception from the process_spider_input chain should not be caught by the
        process_spider_exception chain, it should go directly to the Request errback
        """
        log = yield self.crawl_log(ProcessSpiderInputSpider)
        self.assertNotIn("Middleware: IndexError exception caught", str(log))
        self.assertIn("Middleware: will raise IndexError", str(log))
        self.assertIn("Got a Failure on the Request errback", str(log))


# ================================================================================
# (2) exceptions from a spider callback (generator)
class GeneratorCallbackSpider(Spider):
    name = 'GeneratorCallbackSpider'
    start_urls = ['http://localhost:8998']
    custom_settings = {
        'SPIDER_MIDDLEWARES': {
            # spider
            __name__ + '.LogExceptionMiddleware': 10,
            # engine
        },
    }

    def parse(self, response):
        yield {'test': 1}
        yield {'test': 2}
        raise ImportError()


class TestGeneratorCallback(CommonTestCase):
    @defer.inlineCallbacks
    def test_generator_callback(self):
        """
        (2) An exception from a spider's callback should
        be caught by the process_spider_exception chain
        """
        log = yield self.crawl_log(GeneratorCallbackSpider)
        self.assertIn("Middleware: ImportError exception caught", str(log))
        self.assertIn("'item_scraped_count': 2", str(log))


# ================================================================================
# (3) exceptions from a spider callback (not a generator)
class NotAGeneratorCallbackSpider(Spider):
    name = 'NotAGeneratorCallbackSpider'
    start_urls = ['http://localhost:8998']
    custom_settings = {
        'SPIDER_MIDDLEWARES': {
            # spider
            __name__ + '.LogExceptionMiddleware': 10,
            # engine
        },
    }

    def parse(self, response):
        return [{'test': 1}, {'test': 1/0}]


class TestNotAGeneratorCallback(CommonTestCase):
    @defer.inlineCallbacks
    def test_not_a_generator_callback(self):
        """
        (3) An exception from a spider's callback should
        be caught by the process_spider_exception chain
        """
        log = yield self.crawl_log(NotAGeneratorCallbackSpider)
        self.assertIn("Middleware: ZeroDivisionError exception caught", str(log))
        self.assertNotIn("item_scraped_count", str(log))
