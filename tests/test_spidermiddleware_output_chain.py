from testfixtures import LogCapture
from twisted.internet import defer
from twisted.trial.unittest import TestCase

from scrapy import Request, Spider
from scrapy.utils.test import get_crawler

from tests.mockserver import MockServer


class LogExceptionMiddleware:
    def process_spider_exception(self, response, exception, spider):
        spider.logger.info('Middleware: %s exception caught', exception.__class__.__name__)
        return None


# ================================================================================
# (0) recover from an exception on a spider callback
class RecoveryMiddleware:
    def process_spider_exception(self, response, exception, spider):
        spider.logger.info('Middleware: %s exception caught', exception.__class__.__name__)
        return [
            {'from': 'process_spider_exception'},
            Request(response.url, meta={'dont_fail': True}, dont_filter=True),
        ]


class RecoverySpider(Spider):
    name = 'RecoverySpider'
    custom_settings = {
        'SPIDER_MIDDLEWARES': {
            RecoveryMiddleware: 10,
        },
    }

    def start_requests(self):
        yield Request(self.mockserver.url('/status?n=200'))

    def parse(self, response):
        yield {'test': 1}
        self.logger.info('DONT_FAIL: %s', response.meta.get('dont_fail'))
        if not response.meta.get('dont_fail'):
            raise TabError()


# ================================================================================
# (1) exceptions from a spider middleware's process_spider_input method
class FailProcessSpiderInputMiddleware:
    def process_spider_input(self, response, spider):
        spider.logger.info('Middleware: will raise IndexError')
        raise IndexError()


class ProcessSpiderInputSpiderWithoutErrback(Spider):
    name = 'ProcessSpiderInputSpiderWithoutErrback'
    custom_settings = {
        'SPIDER_MIDDLEWARES': {
            # spider
            FailProcessSpiderInputMiddleware: 8,
            LogExceptionMiddleware: 6,
            # engine
        }
    }

    def start_requests(self):
        yield Request(url=self.mockserver.url('/status?n=200'), callback=self.parse)

    def parse(self, response):
        return {'from': 'callback'}


class ProcessSpiderInputSpiderWithErrback(ProcessSpiderInputSpiderWithoutErrback):
    name = 'ProcessSpiderInputSpiderWithErrback'

    def start_requests(self):
        yield Request(self.mockserver.url('/status?n=200'), self.parse, errback=self.errback)

    def errback(self, failure):
        self.logger.info('Got a Failure on the Request errback')
        return {'from': 'errback'}


# ================================================================================
# (2) exceptions from a spider callback (generator)
class GeneratorCallbackSpider(Spider):
    name = 'GeneratorCallbackSpider'
    custom_settings = {
        'SPIDER_MIDDLEWARES': {
            LogExceptionMiddleware: 10,
        },
    }

    def start_requests(self):
        yield Request(self.mockserver.url('/status?n=200'))

    def parse(self, response):
        yield {'test': 1}
        yield {'test': 2}
        raise ImportError()


# ================================================================================
# (2.1) exceptions from a spider callback (generator, middleware right after callback)
class GeneratorCallbackSpiderMiddlewareRightAfterSpider(GeneratorCallbackSpider):
    name = 'GeneratorCallbackSpiderMiddlewareRightAfterSpider'
    custom_settings = {
        'SPIDER_MIDDLEWARES': {
            LogExceptionMiddleware: 100000,
        },
    }


# ================================================================================
# (3) exceptions from a spider callback (not a generator)
class NotGeneratorCallbackSpider(Spider):
    name = 'NotGeneratorCallbackSpider'
    custom_settings = {
        'SPIDER_MIDDLEWARES': {
            LogExceptionMiddleware: 10,
        },
    }

    def start_requests(self):
        yield Request(self.mockserver.url('/status?n=200'))

    def parse(self, response):
        return [{'test': 1}, {'test': 1 / 0}]


# ================================================================================
# (3.1) exceptions from a spider callback (not a generator, middleware right after callback)
class NotGeneratorCallbackSpiderMiddlewareRightAfterSpider(NotGeneratorCallbackSpider):
    name = 'NotGeneratorCallbackSpiderMiddlewareRightAfterSpider'
    custom_settings = {
        'SPIDER_MIDDLEWARES': {
            LogExceptionMiddleware: 100000,
        },
    }


# ================================================================================
# (4) exceptions from a middleware process_spider_output method (generator)
class _GeneratorDoNothingMiddleware:
    def process_spider_output(self, response, result, spider):
        for r in result:
            r['processed'].append(f'{self.__class__.__name__}.process_spider_output')
            yield r

    def process_spider_exception(self, response, exception, spider):
        method = f'{self.__class__.__name__}.process_spider_exception'
        spider.logger.info('%s: %s caught', method, exception.__class__.__name__)
        return None


class GeneratorFailMiddleware:
    def process_spider_output(self, response, result, spider):
        for r in result:
            r['processed'].append(f'{self.__class__.__name__}.process_spider_output')
            yield r
            raise LookupError()

    def process_spider_exception(self, response, exception, spider):
        method = f'{self.__class__.__name__}.process_spider_exception'
        spider.logger.info('%s: %s caught', method, exception.__class__.__name__)
        yield {'processed': [method]}


class GeneratorDoNothingAfterFailureMiddleware(_GeneratorDoNothingMiddleware):
    pass


class GeneratorRecoverMiddleware:
    def process_spider_output(self, response, result, spider):
        for r in result:
            r['processed'].append(f'{self.__class__.__name__}.process_spider_output')
            yield r

    def process_spider_exception(self, response, exception, spider):
        method = f'{self.__class__.__name__}.process_spider_exception'
        spider.logger.info('%s: %s caught', method, exception.__class__.__name__)
        yield {'processed': [method]}


class GeneratorDoNothingAfterRecoveryMiddleware(_GeneratorDoNothingMiddleware):
    pass


class GeneratorOutputChainSpider(Spider):
    name = 'GeneratorOutputChainSpider'
    custom_settings = {
        'SPIDER_MIDDLEWARES': {
            GeneratorFailMiddleware: 10,
            GeneratorDoNothingAfterFailureMiddleware: 8,
            GeneratorRecoverMiddleware: 5,
            GeneratorDoNothingAfterRecoveryMiddleware: 3,
        },
    }

    def start_requests(self):
        yield Request(self.mockserver.url('/status?n=200'))

    def parse(self, response):
        yield {'processed': ['parse-first-item']}
        yield {'processed': ['parse-second-item']}


# ================================================================================
# (5) exceptions from a middleware process_spider_output method (not generator)

class _NotGeneratorDoNothingMiddleware:
    def process_spider_output(self, response, result, spider):
        out = []
        for r in result:
            r['processed'].append(f'{self.__class__.__name__}.process_spider_output')
            out.append(r)
        return out

    def process_spider_exception(self, response, exception, spider):
        method = f'{self.__class__.__name__}.process_spider_exception'
        spider.logger.info('%s: %s caught', method, exception.__class__.__name__)
        return None


class NotGeneratorFailMiddleware:
    def process_spider_output(self, response, result, spider):
        out = []
        for r in result:
            r['processed'].append(f'{self.__class__.__name__}.process_spider_output')
            out.append(r)
        raise ReferenceError()
        return out

    def process_spider_exception(self, response, exception, spider):
        method = f'{self.__class__.__name__}.process_spider_exception'
        spider.logger.info('%s: %s caught', method, exception.__class__.__name__)
        return [{'processed': [method]}]


class NotGeneratorDoNothingAfterFailureMiddleware(_NotGeneratorDoNothingMiddleware):
    pass


class NotGeneratorRecoverMiddleware:
    def process_spider_output(self, response, result, spider):
        out = []
        for r in result:
            r['processed'].append(f'{self.__class__.__name__}.process_spider_output')
            out.append(r)
        return out

    def process_spider_exception(self, response, exception, spider):
        method = f'{self.__class__.__name__}.process_spider_exception'
        spider.logger.info('%s: %s caught', method, exception.__class__.__name__)
        return [{'processed': [method]}]


class NotGeneratorDoNothingAfterRecoveryMiddleware(_NotGeneratorDoNothingMiddleware):
    pass


class NotGeneratorOutputChainSpider(Spider):
    name = 'NotGeneratorOutputChainSpider'
    custom_settings = {
        'SPIDER_MIDDLEWARES': {
            NotGeneratorFailMiddleware: 10,
            NotGeneratorDoNothingAfterFailureMiddleware: 8,
            NotGeneratorRecoverMiddleware: 5,
            NotGeneratorDoNothingAfterRecoveryMiddleware: 3,
        },
    }

    def start_requests(self):
        return [Request(self.mockserver.url('/status?n=200'))]

    def parse(self, response):
        return [{'processed': ['parse-first-item']}, {'processed': ['parse-second-item']}]


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
            yield crawler.crawl(mockserver=self.mockserver)
        return log

    @defer.inlineCallbacks
    def test_recovery(self):
        """
        (0) Recover from an exception in a spider callback. The final item count should be 3
        (one yielded from the callback method before the exception is raised, one directly
        from the recovery middleware and one from the spider when processing the request that
        was enqueued from the recovery middleware)
        """
        log = yield self.crawl_log(RecoverySpider)
        self.assertIn("Middleware: TabError exception caught", str(log))
        self.assertEqual(str(log).count("Middleware: TabError exception caught"), 1)
        self.assertIn("'item_scraped_count': 3", str(log))

    @defer.inlineCallbacks
    def test_process_spider_input_without_errback(self):
        """
        (1.1) An exception from the process_spider_input chain should be caught by the
        process_spider_exception chain from the start if the Request has no errback
        """
        log1 = yield self.crawl_log(ProcessSpiderInputSpiderWithoutErrback)
        self.assertIn("Middleware: will raise IndexError", str(log1))
        self.assertIn("Middleware: IndexError exception caught", str(log1))

    @defer.inlineCallbacks
    def test_process_spider_input_with_errback(self):
        """
        (1.2) An exception from the process_spider_input chain should not be caught by the
        process_spider_exception chain if the Request has an errback
        """
        log1 = yield self.crawl_log(ProcessSpiderInputSpiderWithErrback)
        self.assertNotIn("Middleware: IndexError exception caught", str(log1))
        self.assertIn("Middleware: will raise IndexError", str(log1))
        self.assertIn("Got a Failure on the Request errback", str(log1))
        self.assertIn("{'from': 'errback'}", str(log1))
        self.assertNotIn("{'from': 'callback'}", str(log1))
        self.assertIn("'item_scraped_count': 1", str(log1))

    @defer.inlineCallbacks
    def test_generator_callback(self):
        """
        (2) An exception from a spider callback (returning a generator) should
        be caught by the process_spider_exception chain. Items yielded before the
        exception is raised should be processed normally.
        """
        log2 = yield self.crawl_log(GeneratorCallbackSpider)
        self.assertIn("Middleware: ImportError exception caught", str(log2))
        self.assertIn("'item_scraped_count': 2", str(log2))

    @defer.inlineCallbacks
    def test_generator_callback_right_after_callback(self):
        """
        (2.1) Special case of (2): Exceptions should be caught
        even if the middleware is placed right after the spider
        """
        log21 = yield self.crawl_log(GeneratorCallbackSpiderMiddlewareRightAfterSpider)
        self.assertIn("Middleware: ImportError exception caught", str(log21))
        self.assertIn("'item_scraped_count': 2", str(log21))

    @defer.inlineCallbacks
    def test_not_a_generator_callback(self):
        """
        (3) An exception from a spider callback (returning a list) should
        be caught by the process_spider_exception chain. No items should be processed.
        """
        log3 = yield self.crawl_log(NotGeneratorCallbackSpider)
        self.assertIn("Middleware: ZeroDivisionError exception caught", str(log3))
        self.assertNotIn("item_scraped_count", str(log3))

    @defer.inlineCallbacks
    def test_not_a_generator_callback_right_after_callback(self):
        """
        (3.1) Special case of (3): Exceptions should be caught
        even if the middleware is placed right after the spider
        """
        log31 = yield self.crawl_log(NotGeneratorCallbackSpiderMiddlewareRightAfterSpider)
        self.assertIn("Middleware: ZeroDivisionError exception caught", str(log31))
        self.assertNotIn("item_scraped_count", str(log31))

    @defer.inlineCallbacks
    def test_generator_output_chain(self):
        """
        (4) An exception from a middleware's process_spider_output method should be sent
        to the process_spider_exception method from the next middleware in the chain.
        The result of the recovery by the process_spider_exception method should be handled
        by the process_spider_output method from the next middleware.
        The final item count should be 2 (one from the spider callback and one from the
        process_spider_exception chain)
        """
        log4 = yield self.crawl_log(GeneratorOutputChainSpider)
        self.assertIn("'item_scraped_count': 2", str(log4))
        self.assertIn("GeneratorRecoverMiddleware.process_spider_exception: LookupError caught", str(log4))
        self.assertIn(
            "GeneratorDoNothingAfterFailureMiddleware.process_spider_exception: LookupError caught",
            str(log4))
        self.assertNotIn(
            "GeneratorFailMiddleware.process_spider_exception: LookupError caught",
            str(log4))
        self.assertNotIn(
            "GeneratorDoNothingAfterRecoveryMiddleware.process_spider_exception: LookupError caught",
            str(log4))
        item_from_callback = {'processed': [
            'parse-first-item',
            'GeneratorFailMiddleware.process_spider_output',
            'GeneratorDoNothingAfterFailureMiddleware.process_spider_output',
            'GeneratorRecoverMiddleware.process_spider_output',
            'GeneratorDoNothingAfterRecoveryMiddleware.process_spider_output']}
        item_recovered = {'processed': [
            'GeneratorRecoverMiddleware.process_spider_exception',
            'GeneratorDoNothingAfterRecoveryMiddleware.process_spider_output']}
        self.assertIn(str(item_from_callback), str(log4))
        self.assertIn(str(item_recovered), str(log4))
        self.assertNotIn('parse-second-item', str(log4))

    @defer.inlineCallbacks
    def test_not_a_generator_output_chain(self):
        """
        (5) An exception from a middleware's process_spider_output method should be sent
        to the process_spider_exception method from the next middleware in the chain.
        The result of the recovery by the process_spider_exception method should be handled
        by the process_spider_output method from the next middleware.
        The final item count should be 1 (from the process_spider_exception chain, the items
        from the spider callback are lost)
        """
        log5 = yield self.crawl_log(NotGeneratorOutputChainSpider)
        self.assertIn("'item_scraped_count': 1", str(log5))
        self.assertIn("GeneratorRecoverMiddleware.process_spider_exception: ReferenceError caught", str(log5))
        self.assertIn(
            "GeneratorDoNothingAfterFailureMiddleware.process_spider_exception: ReferenceError caught",
            str(log5))
        self.assertNotIn("GeneratorFailMiddleware.process_spider_exception: ReferenceError caught", str(log5))
        self.assertNotIn(
            "GeneratorDoNothingAfterRecoveryMiddleware.process_spider_exception: ReferenceError caught",
            str(log5))
        item_recovered = {'processed': [
            'NotGeneratorRecoverMiddleware.process_spider_exception',
            'NotGeneratorDoNothingAfterRecoveryMiddleware.process_spider_output']}
        self.assertIn(str(item_recovered), str(log5))
        self.assertNotIn('parse-first-item', str(log5))
        self.assertNotIn('parse-second-item', str(log5))
