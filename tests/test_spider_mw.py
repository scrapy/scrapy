
import logging

from testfixtures import LogCapture
from twisted.trial.unittest import TestCase
from twisted.internet import defer

from scrapy import Spider, Request
from scrapy.utils.test import get_crawler
from tests.mockserver import MockServer


# TEST_URL = 'http://example.org'
TEST_URL = 'http://localhost:8998'


class LogExceptionMiddleware(object):
    def process_spider_exception(self, response, exception, spider):
        logging.warn('Middleware: %s exception caught', exception.__class__.__name__)
        return None


# ================================================================================
# recover from an exception on a spider callback
class RecoverySpider(Spider):
    name = 'RecoverySpider'
    start_urls = [TEST_URL]
    custom_settings = {
        'SPIDER_MIDDLEWARES': {
            __name__ + '.RecoveryMiddleware': 10,
        },
    }

    def parse(self, response):
        yield {'test': 1}
        self.logger.warn('DONT_FAIL: %s', response.meta.get('dont_fail'))
        if not response.meta.get('dont_fail'):
            raise ModuleNotFoundError()

class RecoveryMiddleware(object):
    def process_spider_exception(self, response, exception, spider):
        logging.warn('Middleware: %s exception caught', exception.__class__.__name__)
        return [
            {'from': 'process_spider_exception'},
            Request(response.url, meta={'dont_fail': True}, dont_filter=True),
        ]


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
        yield Request(TEST_URL, callback=self.parse, errback=self.errback)

    def parse(self, response):
        return [{'test': 1}, {'test': 2}]

    def errback(self, failure):
        self.logger.warn('Got a Failure on the Request errback')


class FailProcessSpiderInputMiddleware:
    def process_spider_input(self, response, spider):
        logging.warn('Middleware: will raise IndexError')
        raise IndexError()


# ================================================================================
# (2) exceptions from a spider callback (generator)
class GeneratorCallbackSpider(Spider):
    name = 'GeneratorCallbackSpider'
    start_urls = [TEST_URL]
    custom_settings = {
        'SPIDER_MIDDLEWARES': {
            __name__ + '.LogExceptionMiddleware': 10,
        },
    }

    def parse(self, response):
        yield {'test': 1}
        yield {'test': 2}
        raise ImportError()


# ================================================================================
# (3) exceptions from a spider callback (not a generator)
class NotAGeneratorCallbackSpider(Spider):
    name = 'NotAGeneratorCallbackSpider'
    start_urls = [TEST_URL]
    custom_settings = {
        'SPIDER_MIDDLEWARES': {
            __name__ + '.LogExceptionMiddleware': 10,
        },
    }

    def parse(self, response):
        return [{'test': 1}, {'test': 1/0}]


# ================================================================================
class TestSpiderMiddleware(TestCase):
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

    # @defer.inlineCallbacks
    # def test_recovery(self):
    #     """
    #     Recover from an exception from a spider's callback. The final item count should be 3
    #     (one from the spider before raising the exception, one from the middleware and one
    #     from the spider when processing the response that was enqueued from the middleware)
    #     """
    #     log = yield self.crawl_log(RecoverySpider)
    #     self.assertIn("Middleware: ModuleNotFoundError exception caught", str(log))
    #     self.assertEqual(str(log).count("Middleware: ModuleNotFoundError exception caught"), 1)
    #     self.assertIn("'item_scraped_count': 3", str(log))

    @defer.inlineCallbacks
    def test_process_spider_input_errback(self):
        """
        (1) An exception from the process_spider_input chain should not be caught by the
        process_spider_exception chain, it should go directly to the Request errback
        """
        log1 = yield self.crawl_log(ProcessSpiderInputSpider)
        self.assertNotIn("Middleware: IndexError exception caught", str(log1))
        self.assertIn("Middleware: will raise IndexError", str(log1))
        self.assertIn("Got a Failure on the Request errback", str(log1))
    
    @defer.inlineCallbacks
    def test_generator_callback(self):
        """
        (2) An exception from a spider's callback should
        be caught by the process_spider_exception chain
        """
        log2 = yield self.crawl_log(GeneratorCallbackSpider)
        self.assertIn("Middleware: ImportError exception caught", str(log2))
        self.assertIn("'item_scraped_count': 2", str(log2))
    
    @defer.inlineCallbacks
    def test_not_a_generator_callback(self):
        """
        (3) An exception from a spider's callback should
        be caught by the process_spider_exception chain
        """
        log3 = yield self.crawl_log(NotAGeneratorCallbackSpider)
        self.assertIn("Middleware: ZeroDivisionError exception caught", str(log3))
        self.assertNotIn("item_scraped_count", str(log3))
