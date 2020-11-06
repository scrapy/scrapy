from twisted.internet import defer
from twisted.trial.unittest import TestCase

from scrapy import Request, signals
from scrapy.crawler import CrawlerRunner
from scrapy.http.response import Response

from testfixtures import LogCapture

from tests.mockserver import MockServer
from tests.spiders import SingleRequestSpider


OVERRIDEN_URL = "https://example.org"


class ProcessResponseMiddleware:
    def process_response(self, request, response, spider):
        return response.replace(request=Request(OVERRIDEN_URL))


class RaiseExceptionRequestMiddleware:
    def process_request(self, request, spider):
        1 / 0
        return request


class CatchExceptionOverrideRequestMiddleware:
    def process_exception(self, request, exception, spider):
        return Response(
            url="http://localhost/",
            body=b"Caught " + exception.__class__.__name__.encode("utf-8"),
            request=Request(OVERRIDEN_URL),
        )


class CatchExceptionDoNotOverrideRequestMiddleware:
    def process_exception(self, request, exception, spider):
        return Response(
            url="http://localhost/",
            body=b"Caught " + exception.__class__.__name__.encode("utf-8"),
        )


class AlternativeCallbacksSpider(SingleRequestSpider):
    name = "alternative_callbacks_spider"

    def alt_callback(self, response, foo=None):
        self.logger.info("alt_callback was invoked with foo=%s", foo)


class AlternativeCallbacksMiddleware:
    def process_response(self, request, response, spider):
        new_request = request.replace(
            url=OVERRIDEN_URL,
            callback=spider.alt_callback,
            cb_kwargs={"foo": "bar"},
        )
        return response.replace(request=new_request)


class CrawlTestCase(TestCase):

    def setUp(self):
        self.mockserver = MockServer()
        self.mockserver.__enter__()

    def tearDown(self):
        self.mockserver.__exit__(None, None, None)

    @defer.inlineCallbacks
    def test_response_200(self):
        url = self.mockserver.url("/status?n=200")
        crawler = CrawlerRunner().create_crawler(SingleRequestSpider)
        yield crawler.crawl(seed=url, mockserver=self.mockserver)
        response = crawler.spider.meta["responses"][0]
        self.assertEqual(response.request.url, url)

    @defer.inlineCallbacks
    def test_response_error(self):
        for status in ("404", "500"):
            url = self.mockserver.url(f"/status?n={status}")
            crawler = CrawlerRunner().create_crawler(SingleRequestSpider)
            yield crawler.crawl(seed=url, mockserver=self.mockserver)
            failure = crawler.spider.meta["failure"]
            response = failure.value.response
            self.assertEqual(failure.request.url, url)
            self.assertEqual(response.request.url, url)

    @defer.inlineCallbacks
    def test_downloader_middleware_raise_exception(self):
        url = self.mockserver.url("/status?n=200")
        runner = CrawlerRunner(settings={
            "DOWNLOADER_MIDDLEWARES": {
                RaiseExceptionRequestMiddleware: 590,
            },
        })
        crawler = runner.create_crawler(SingleRequestSpider)
        yield crawler.crawl(seed=url, mockserver=self.mockserver)
        failure = crawler.spider.meta["failure"]
        self.assertEqual(failure.request.url, url)
        self.assertIsInstance(failure.value, ZeroDivisionError)

    @defer.inlineCallbacks
    def test_downloader_middleware_override_request_in_process_response(self):
        """
        Downloader middleware which returns a response with an specific 'request' attribute.

        * The spider callback should receive the overriden response.request
        * Handlers listening to the response_received signal should receive the overriden response.request
        * The "crawled" log message should show the overriden response.request
        """
        signal_params = {}

        def signal_handler(response, request, spider):
            signal_params["response"] = response
            signal_params["request"] = request

        url = self.mockserver.url("/status?n=200")
        runner = CrawlerRunner(settings={
            "DOWNLOADER_MIDDLEWARES": {
                ProcessResponseMiddleware: 595,
            }
        })
        crawler = runner.create_crawler(SingleRequestSpider)
        crawler.signals.connect(signal_handler, signal=signals.response_received)

        with LogCapture() as log:
            yield crawler.crawl(seed=url, mockserver=self.mockserver)

        response = crawler.spider.meta["responses"][0]
        self.assertEqual(response.request.url, OVERRIDEN_URL)

        self.assertEqual(signal_params["response"].url, url)
        self.assertEqual(signal_params["request"].url, OVERRIDEN_URL)

        log.check_present(
            ("scrapy.core.engine", "DEBUG", f"Crawled (200) <GET {OVERRIDEN_URL}> (referer: None)"),
        )

    @defer.inlineCallbacks
    def test_downloader_middleware_override_in_process_exception(self):
        """
        An exception is raised but caught by the next middleware, which
        returns a Response with a specific 'request' attribute.

        The spider callback should receive the overriden response.request
        """
        url = self.mockserver.url("/status?n=200")
        runner = CrawlerRunner(settings={
            "DOWNLOADER_MIDDLEWARES": {
                RaiseExceptionRequestMiddleware: 590,
                CatchExceptionOverrideRequestMiddleware: 595,
            },
        })
        crawler = runner.create_crawler(SingleRequestSpider)
        yield crawler.crawl(seed=url, mockserver=self.mockserver)
        response = crawler.spider.meta["responses"][0]
        self.assertEqual(response.body, b"Caught ZeroDivisionError")
        self.assertEqual(response.request.url, OVERRIDEN_URL)

    @defer.inlineCallbacks
    def test_downloader_middleware_do_not_override_in_process_exception(self):
        """
        An exception is raised but caught by the next middleware, which
        returns a Response without a specific 'request' attribute.

        The spider callback should receive the original response.request
        """
        url = self.mockserver.url("/status?n=200")
        runner = CrawlerRunner(settings={
            "DOWNLOADER_MIDDLEWARES": {
                RaiseExceptionRequestMiddleware: 590,
                CatchExceptionDoNotOverrideRequestMiddleware: 595,
            },
        })
        crawler = runner.create_crawler(SingleRequestSpider)
        yield crawler.crawl(seed=url, mockserver=self.mockserver)
        response = crawler.spider.meta["responses"][0]
        self.assertEqual(response.body, b"Caught ZeroDivisionError")
        self.assertEqual(response.request.url, url)

    @defer.inlineCallbacks
    def test_downloader_middleware_alternative_callback(self):
        """
        Downloader middleware which returns a response with a
        specific 'request' attribute, with an alternative callback
        """
        runner = CrawlerRunner(settings={
            "DOWNLOADER_MIDDLEWARES": {
                AlternativeCallbacksMiddleware: 595,
            }
        })
        crawler = runner.create_crawler(AlternativeCallbacksSpider)

        with LogCapture() as log:
            url = self.mockserver.url("/status?n=200")
            yield crawler.crawl(seed=url, mockserver=self.mockserver)

        log.check_present(
            ("alternative_callbacks_spider", "INFO", "alt_callback was invoked with foo=bar"),
        )
