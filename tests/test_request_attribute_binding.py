from twisted.internet import defer
from twisted.trial.unittest import TestCase

from scrapy import Request
from scrapy.crawler import CrawlerRunner
from scrapy.http.response import Response

from tests.mockserver import MockServer
from tests.spiders import SingleRequestSpider


class ProcessResponseMiddleware:
    def process_response(self, request, response, spider):
        return response.replace(request=Request("https://example.org"))


class RaiseExceptionMiddleware:
    def process_request(self, request, spider):
        1 / 0
        return request


class CatchExceptionOverrideRequestMiddleware:
    def process_exception(self, request, exception, spider):
        return Response(
            url="http://localhost/",
            body=b"Caught " + exception.__class__.__name__.encode("utf-8"),
            request=Request("https://example.org"),
        )


class CatchExceptionDoNotOverrideRequestMiddleware:
    def process_exception(self, request, exception, spider):
        return Response(
            url="http://localhost/",
            body=b"Caught " + exception.__class__.__name__.encode("utf-8"),
        )


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
            url = self.mockserver.url("/status?n={}".format(status))
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
                __name__ + ".RaiseExceptionMiddleware": 590,
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

        The spider callback should receive the overriden response.request
        """
        url = self.mockserver.url("/status?n=200")
        runner = CrawlerRunner(settings={
            "DOWNLOADER_MIDDLEWARES": {
                __name__ + ".ProcessResponseMiddleware": 595,
            }
        })
        crawler = runner.create_crawler(SingleRequestSpider)
        yield crawler.crawl(seed=url, mockserver=self.mockserver)
        response = crawler.spider.meta["responses"][0]
        self.assertEqual(response.request.url, "https://example.org")

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
                __name__ + ".RaiseExceptionMiddleware": 590,
                __name__ + ".CatchExceptionOverrideRequestMiddleware": 595,
            },
        })
        crawler = runner.create_crawler(SingleRequestSpider)
        yield crawler.crawl(seed=url, mockserver=self.mockserver)
        response = crawler.spider.meta["responses"][0]
        self.assertEqual(response.body, b"Caught ZeroDivisionError")
        self.assertEqual(response.request.url, "https://example.org")

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
                __name__ + ".RaiseExceptionMiddleware": 590,
                __name__ + ".CatchExceptionDoNotOverrideRequestMiddleware": 595,
            },
        })
        crawler = runner.create_crawler(SingleRequestSpider)
        yield crawler.crawl(seed=url, mockserver=self.mockserver)
        response = crawler.spider.meta["responses"][0]
        self.assertEqual(response.body, b"Caught ZeroDivisionError")
        self.assertEqual(response.request.url, url)
