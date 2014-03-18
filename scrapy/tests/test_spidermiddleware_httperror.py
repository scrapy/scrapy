from unittest import TestCase

from twisted.trial.unittest import TestCase as TrialTestCase
from twisted.internet import defer

from scrapy.utils.test import docrawl, get_testlog
from scrapy.tests.mockserver import MockServer
from scrapy.http import Response, Request
from scrapy.spider import Spider
from scrapy.contrib.spidermiddleware.httperror import HttpErrorMiddleware, HttpError
from scrapy.settings import Settings


class _HttpErrorSpider(Spider):
    name = 'httperror'
    start_urls = [
        "http://localhost:8998/status?n=200",
        "http://localhost:8998/status?n=404",
        "http://localhost:8998/status?n=402",
        "http://localhost:8998/status?n=500",
    ]
    bypass_status_codes = set()

    def __init__(self, *args, **kwargs):
        super(_HttpErrorSpider, self).__init__(*args, **kwargs)
        self.failed = set()
        self.skipped = set()
        self.parsed = set()

    def start_requests(self):
        for url in self.start_urls:
            yield Request(url, self.parse, errback=self.on_error)

    def parse(self, response):
        self.parsed.add(response.url[-3:])

    def on_error(self, failure):
        if isinstance(failure.value, HttpError):
            response = failure.value.response
            if response.status in self.bypass_status_codes:
                self.skipped.add(response.url[-3:])
                return self.parse(response)

        # it assumes there is a response attached to failure
        self.failed.add(failure.value.response.url[-3:])
        return failure


def _responses(request, status_codes):
    responses = []
    for code in status_codes:
        response = Response(request.url, status=code)
        response.request = request
        responses.append(response)
    return responses


class TestHttpErrorMiddleware(TestCase):

    def setUp(self):
        self.spider = Spider('foo')
        self.mw = HttpErrorMiddleware(Settings({}))
        self.req = Request('http://scrapytest.org')
        self.res200, self.res404 = _responses(self.req, [200, 404])

    def test_process_spider_input(self):
        self.assertEquals(None,
                self.mw.process_spider_input(self.res200, self.spider))
        self.assertRaises(HttpError,
                self.mw.process_spider_input, self.res404, self.spider)

    def test_process_spider_exception(self):
        self.assertEquals([],
                self.mw.process_spider_exception(self.res404, \
                        HttpError(self.res404), self.spider))
        self.assertEquals(None,
                self.mw.process_spider_exception(self.res404, \
                        Exception(), self.spider))

    def test_handle_httpstatus_list(self):
        res = self.res404.copy()
        res.request = Request('http://scrapytest.org',
                              meta={'handle_httpstatus_list': [404]})
        self.assertEquals(None,
            self.mw.process_spider_input(res, self.spider))

        self.spider.handle_httpstatus_list = [404]
        self.assertEquals(None,
            self.mw.process_spider_input(self.res404, self.spider))


class TestHttpErrorMiddlewareSettings(TestCase):
    """Similar test, but with settings"""

    def setUp(self):
        self.spider = Spider('foo')
        self.mw = HttpErrorMiddleware(Settings({'HTTPERROR_ALLOWED_CODES': (402,)}))
        self.req = Request('http://scrapytest.org')
        self.res200, self.res404, self.res402 = _responses(self.req, [200, 404, 402])

    def test_process_spider_input(self):
        self.assertEquals(None,
                self.mw.process_spider_input(self.res200, self.spider))
        self.assertRaises(HttpError,
                self.mw.process_spider_input, self.res404, self.spider)
        self.assertEquals(None,
                self.mw.process_spider_input(self.res402, self.spider))

    def test_meta_overrides_settings(self):
        request = Request('http://scrapytest.org',
                              meta={'handle_httpstatus_list': [404]})
        res404 = self.res404.copy()
        res404.request = request
        res402 = self.res402.copy()
        res402.request = request

        self.assertEquals(None,
            self.mw.process_spider_input(res404, self.spider))
        self.assertRaises(HttpError,
                self.mw.process_spider_input, res402, self.spider)

    def test_spider_override_settings(self):
        self.spider.handle_httpstatus_list = [404]
        self.assertEquals(None,
            self.mw.process_spider_input(self.res404, self.spider))
        self.assertRaises(HttpError,
                self.mw.process_spider_input, self.res402, self.spider)


class TestHttpErrorMiddlewareHandleAll(TestCase):

    def setUp(self):
        self.spider = Spider('foo')
        self.mw = HttpErrorMiddleware(Settings({'HTTPERROR_ALLOW_ALL': True}))
        self.req = Request('http://scrapytest.org')
        self.res200, self.res404, self.res402 = _responses(self.req, [200, 404, 402])

    def test_process_spider_input(self):
        self.assertEquals(None,
                self.mw.process_spider_input(self.res200, self.spider))
        self.assertEquals(None,
                self.mw.process_spider_input(self.res404, self.spider))

    def test_meta_overrides_settings(self):
        request = Request('http://scrapytest.org',
                              meta={'handle_httpstatus_list': [404]})
        res404 = self.res404.copy()
        res404.request = request
        res402 = self.res402.copy()
        res402.request = request

        self.assertEquals(None,
            self.mw.process_spider_input(res404, self.spider))
        self.assertRaises(HttpError,
                self.mw.process_spider_input, res402, self.spider)


class TestHttpErrorMiddlewareIntegrational(TrialTestCase):
    def setUp(self):
        self.mockserver = MockServer()
        self.mockserver.__enter__()

    def tearDown(self):
        self.mockserver.__exit__(None, None, None)

    @defer.inlineCallbacks
    def test_middleware_works(self):
        spider = _HttpErrorSpider()
        yield docrawl(spider)
        assert not spider.skipped, spider.skipped
        self.assertEqual(spider.parsed, {'200'})
        self.assertEqual(spider.failed, {'404', '402', '500'})

    @defer.inlineCallbacks
    def test_logging(self):
        spider = _HttpErrorSpider(bypass_status_codes={402})
        yield docrawl(spider)
        # print(get_testlog())
        self.assertEqual(spider.parsed, {'200', '402'})
        self.assertEqual(spider.skipped, {'402'})
        self.assertEqual(spider.failed, {'404', '500'})

        log = get_testlog()
        self.assertIn('Ignoring response <404', log)
        self.assertIn('Ignoring response <500', log)
        self.assertNotIn('Ignoring response <200', log)
        self.assertNotIn('Ignoring response <402', log)
