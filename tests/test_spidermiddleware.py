
import logging

from testfixtures import LogCapture
from twisted.trial.unittest import TestCase
from twisted.internet import defer

from scrapy.spiders import Spider
from scrapy.item import Item, Field
from scrapy.http import Request
from scrapy.utils.test import get_crawler


class TestItem(Item):
    value = Field()


# ================================================================================
# exceptions from a spider's parse method
class BaseExceptionFromParseMethodSpider(Spider):
    start_urls = ["http://example.com/"]
    custom_settings = {
        'SPIDER_MIDDLEWARES': {'tests.test_spidermiddleware.CatchExceptionMiddleware': 540}
    }


class NotAGeneratorSpider(BaseExceptionFromParseMethodSpider):
    """ return value is NOT a generator """
    name = 'not_a_generator'

    def parse(self, response):
        raise AssertionError


class GeneratorErrorBeforeItemsSpider(BaseExceptionFromParseMethodSpider):
    """ return value is a generator; the exception is raised
    before the items are yielded: no items should be scraped """
    name = 'generator_error_before_items'

    def parse(self, response):
        raise ValueError
        for i in range(3):
            yield {'value': i}


class GeneratorErrorAfterItemsSpider(BaseExceptionFromParseMethodSpider):
    """ return value is a generator; the exception is raised
    after the items are yielded: 3 items should be scraped """
    name = 'generator_error_after_items'

    def parse(self, response):
        for i in range(3):
            yield {'value': i}
        raise FloatingPointError


class CatchExceptionMiddleware(object):
    def process_spider_exception(self, response, exception, spider):
        """ catch an exception and log it """
        logging.warn('{} exception caught'.format(exception.__class__.__name__))
        return None


# ================================================================================
# exception from a previous middleware's process_spider_input method
# process_spider_input is not expected to return an iterable, so there are no
# separate tests for generator/non-generator implementations
class FromPreviousMiddlewareInputSpider(Spider):
    start_urls = ["http://example.com/"]
    name = 'not_a_generator_from_previous_middleware_input'
    custom_settings = {
        'SPIDER_MIDDLEWARES': {
            # engine side
            'tests.test_spidermiddleware.CatchExceptionMiddleware': 540,
            'tests.test_spidermiddleware.RaiseExceptionOnInputMiddleware': 545,
            # spider side
        }
    }

    def parse(self, response):
        return None


class RaiseExceptionOnInputMiddleware(object):
    def process_spider_input(self, response, spider):
        raise LookupError


# ================================================================================
# exception from a previous middleware's process_spider_output method (not a generator)
class NotAGeneratorFromPreviousMiddlewareOutputSpider(Spider):
    start_urls = ["http://example.com/"]
    name = 'not_a_generator_from_previous_middleware_output'
    custom_settings = {
        'SPIDER_MIDDLEWARES': {
            # engine side
            'tests.test_spidermiddleware.CatchExceptionMiddleware': 540,
            'tests.test_spidermiddleware.RaiseExceptionOnOutputNotAGeneratorMiddleware': 545,
            # spider side
        }
    }

    def parse(self, response):
        return [{'value': i} for i in range(3)]


class RaiseExceptionOnOutputNotAGeneratorMiddleware(object):
    def process_spider_output(self, response, result, spider):
        raise UnicodeError


# ================================================================================
# exception from a previous middleware's process_spider_output method (generator)
class GeneratorFromPreviousMiddlewareOutputSpider(Spider):
    start_urls = ["http://example.com/"]
    name = 'generator_from_previous_middleware_output'
    custom_settings = {
        'SPIDER_MIDDLEWARES': {
            # engine side
            'tests.test_spidermiddleware.CatchExceptionMiddleware': 540,
            'tests.test_spidermiddleware.RaiseExceptionOnOutputGeneratorMiddleware': 545,
            # spider side
        }
    }

    def parse(self, response):
        return [{'value': i} for i in range(10, 13)]


class RaiseExceptionOnOutputGeneratorMiddleware(object):
    def process_spider_output(self, response, result, spider):
        for r in result:
            yield r
        raise NameError


# ================================================================================
# do something useful from the exception handler
class DoSomethingSpider(Spider):
    start_urls = ["http://example.com"]
    name = 'do_something'
    custom_settings = {
        'SPIDER_MIDDLEWARES': {
            # engine side
            'tests.test_spidermiddleware.DoSomethingMiddleware': 540,
            'tests.test_spidermiddleware.CatchExceptionMiddleware': 545,
            # spider side
        }
    }

    def parse(self, response):
        yield {'value': response.url}
        raise ImportError


class DoSomethingMiddleware(object):
    def process_spider_exception(self, response, exception, spider):
        return [Request('http://example.org'), {'value': 10}, TestItem(value='asdf')]


# ================================================================================
# don't catch InvalidOutput from scrapy's spider middleware manager
class InvalidReturnValueFromPreviousMiddlewareInputSpider(Spider):
    start_urls = ["http://example.com/"]
    name = 'invalid_return_value_from_previous_middleware_input'
    custom_settings = {
        'SPIDER_MIDDLEWARES': {
            # engine side
            'tests.test_spidermiddleware.InvalidReturnValueInputMiddleware': 540,
            'tests.test_spidermiddleware.CatchExceptionMiddleware': 545,
            # spider side
        }
    }

    def parse(self, response):
        return None


class InvalidReturnValueInputMiddleware(object):
    def process_spider_input(self, response, spider):
        return 1.0  # <type 'float'>, not None


class InvalidReturnValueFromPreviousMiddlewareOutputSpider(Spider):
    start_urls = ["http://example.com/"]
    name = 'invalid_return_value_from_previous_middleware_output'
    custom_settings = {
        'SPIDER_MIDDLEWARES': {
            # engine side
            'tests.test_spidermiddleware.CatchExceptionMiddleware': 540,
            'tests.test_spidermiddleware.InvalidReturnValueOutputMiddleware': 545,
            # spider side
        }
    }

    def parse(self, response):
        return None


class InvalidReturnValueOutputMiddleware(object):
    def process_spider_output(self, response, result, spider):
        return 1  # <type 'int'>, not an iterable


# ================================================================================
# make sure only non already called process_spider_output methods
# are called if process_spider_exception returns an iterable
class ExecutionChainSpider(Spider):
    start_urls = ["http://example.com"]
    name = 'execution_chain'
    custom_settings = {
        'SPIDER_MIDDLEWARES': {
            # engine side
            'tests.test_spidermiddleware.ThirdMiddleware': 540,
            'tests.test_spidermiddleware.SecondMiddleware': 541,
            'tests.test_spidermiddleware.FirstMiddleware': 542
            # spider side
        },
    }

    def parse(self, response):
        return None


class FirstMiddleware(object):
    def process_spider_output(self, response, result, spider):
        for r in result:
            if isinstance(r, dict):
                r['handled_by_first_middleware'] = True
            yield r

    def process_spider_exception(self, response, exception, spider):
        # log exception, handle control to the next middleware's process_spider_exception
        logging.warn('{} exception caught'.format(exception.__class__.__name__))
        return None


class SecondMiddleware(object):
    def process_spider_output(self, response, result, spider):
        for r in result:
            if isinstance(r, dict):
                r['handled_by_second_middleware'] = True
            yield r
        raise MemoryError


class ThirdMiddleware(object):
    def process_spider_output(self, response, result, spider):
        for r in result:
            if isinstance(r, dict):
                r['handled_by_third_middleware'] = True
            yield r

    def process_spider_exception(self, response, exception, spider):
        # handle control to the next middleware's process_spider_output
        return [{'item': i} for i in range(3)]


class TestSpiderMiddleware(TestCase):

    @defer.inlineCallbacks
    def test_process_spider_exception_from_parse_method(self):
        # non-generator return value
        crawler = get_crawler(NotAGeneratorSpider)
        with LogCapture() as log:
            yield crawler.crawl()
        self.assertIn("AssertionError exception caught", str(log))
        self.assertIn("spider_exceptions/AssertionError", str(log))
        # generator return value, no items before the error
        crawler = get_crawler(GeneratorErrorBeforeItemsSpider)
        with LogCapture() as log:
            yield crawler.crawl()
        self.assertIn("ValueError exception caught", str(log))
        self.assertIn("spider_exceptions/ValueError", str(log))
        # generator return value, 3 items before the error
        crawler = get_crawler(GeneratorErrorAfterItemsSpider)
        with LogCapture() as log:
            yield crawler.crawl()
        self.assertIn("'item_scraped_count': 3", str(log))
        self.assertIn("FloatingPointError exception caught", str(log))
        self.assertIn("spider_exceptions/FloatingPointError", str(log))

    @defer.inlineCallbacks
    def test_process_spider_exception_from_previous_middleware_input(self):
        crawler = get_crawler(FromPreviousMiddlewareInputSpider)
        with LogCapture() as log:
            yield crawler.crawl()
        self.assertIn("LookupError exception caught", str(log))

    @defer.inlineCallbacks
    def test_process_spider_exception_from_previous_middleware_output(self):
        # non-generator output value
        crawler = get_crawler(NotAGeneratorFromPreviousMiddlewareOutputSpider)
        with LogCapture() as log:
            yield crawler.crawl()
        self.assertNotIn("UnicodeError exception caught", str(log))
        # generator output value
        crawler = get_crawler(GeneratorFromPreviousMiddlewareOutputSpider)
        with LogCapture() as log:
            yield crawler.crawl()
        self.assertIn("'item_scraped_count': 3", str(log))
        self.assertIn("NameError exception caught", str(log))

    @defer.inlineCallbacks
    def test_process_spider_exception_do_something(self):
        crawler = get_crawler(DoSomethingSpider)
        with LogCapture() as log:
            yield crawler.crawl()
        self.assertIn("ImportError exception caught", str(log))
        self.assertIn("{'value': 10}", str(log))
        self.assertIn("{'value': 'asdf'}", str(log))
        self.assertIn("{'value': 'http://example.com'}", str(log))
        self.assertIn("{'value': 'http://example.org'}", str(log))

    @defer.inlineCallbacks
    def test_process_spider_exception_invalid_return_value_previous_middleware(self):
        """ don't catch InvalidOutput from middleware """
        # on middleware's input
        crawler1 = get_crawler(InvalidReturnValueFromPreviousMiddlewareInputSpider)
        with LogCapture() as log1:
            yield crawler1.crawl()
        self.assertNotIn("InvalidOutput exception caught", str(log1))
        self.assertIn("'spider_exceptions/InvalidOutput'", str(log1))
        # on middleware's output
        crawler2 = get_crawler(InvalidReturnValueFromPreviousMiddlewareOutputSpider)
        with LogCapture() as log2:
            yield crawler2.crawl()
        self.assertNotIn("InvalidOutput exception caught", str(log2))
        self.assertIn("'spider_exceptions/InvalidOutput'", str(log2))

    @defer.inlineCallbacks
    def test_process_spider_exception_execution_chain(self):
        # on middleware's input
        crawler1 = get_crawler(ExecutionChainSpider)
        with LogCapture() as log1:
            yield crawler1.crawl()
        self.assertNotIn("handled_by_first_middleware", str(log1))
        self.assertNotIn("handled_by_second_middleware", str(log1))
        self.assertIn("MemoryError exception caught", str(log1))
        self.assertIn("handled_by_third_middleware", str(log1))
