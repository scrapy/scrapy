"""
Temporary test cases to understand the binding of the
'request' attribute in responses and failures

See https://github.com/scrapy/scrapy/issues/4529
"""

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


class CatchExceptionSetRequestMiddleware:
    def process_exception(self, request, exception, spider):
        return Response(
            url="http://localhost/",
            body=exception.__class__.__name__.encode("utf-8"),
            request=Request("https://example.org"),
        )


class CatchExceptionDoNotSetRequestMiddleware:
    def process_exception(self, request, exception, spider):
        return Response(
            url="http://localhost/",
            body=exception.__class__.__name__.encode("utf-8"),
        )


class CrawlTestCase(TestCase):

    def setUp(self):
        self.mockserver = MockServer()
        self.mockserver.__enter__()

    def tearDown(self):
        self.mockserver.__exit__(None, None, None)

    @defer.inlineCallbacks
    def test_response_200(self):
        """
        A successful response, the 'request' attribute is set by the engine
        and checked but not modified by the scraper.
        """
        url = self.mockserver.url("/status?n=200")
        crawler = CrawlerRunner().create_crawler(SingleRequestSpider)
        yield crawler.crawl(seed=url, mockserver=self.mockserver)
        response = crawler.spider.meta["responses"][0]
        self.assertTrue(response._request_set_in_engine)
        self.assertFalse(response._request_set_in_scraper)

    @defer.inlineCallbacks
    def test_response_error(self):
        """
        The 'failure.request' attribute is set by the scraper, not checked by the engine.
        The 'failure.value.response.request' attribute is set by the engine, not checked by the scraper.
        """
        for status in ("404", "500"):
            url = self.mockserver.url("/status?n={}".format(status))
            crawler = CrawlerRunner().create_crawler(SingleRequestSpider)
            yield crawler.crawl(seed=url, mockserver=self.mockserver)

            # failure is only processed by the scraper
            failure = crawler.spider.meta["failure"]
            self.assertFalse(hasattr(failure, "_request_set_in_engine"))
            self.assertTrue(failure._request_set_in_scraper)

            # failure.value.response is only processed by the engine
            response = failure.value.response
            self.assertTrue(response._request_set_in_engine)
            self.assertFalse(hasattr(response, "_request_set_in_scraper"))

    @defer.inlineCallbacks
    def test_downloader_middleware_process_response(self):
        """
        process_response returns a response with an specific 'request' attribute,
        it is processed but not altered by the engine and the scraper
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
        self.assertFalse(response._request_set_in_engine)
        self.assertFalse(response._request_set_in_scraper)
        self.assertEqual(response.request.url, "https://example.org")

    @defer.inlineCallbacks
    def test_downloader_middleware_raise_exception(self):
        """
        process_response raises an exception, the 'failure.request' attribute
        is set only by the scraper (not processed by the engine)
        """
        url = self.mockserver.url("/status?n=200")
        runner = CrawlerRunner(settings={
            "DOWNLOADER_MIDDLEWARES": {
                __name__ + ".RaiseExceptionMiddleware": 590,
            },
        })
        crawler = runner.create_crawler(SingleRequestSpider)
        yield crawler.crawl(seed=url, mockserver=self.mockserver)
        # failure is only processed by the scraper
        failure = crawler.spider.meta["failure"]
        self.assertFalse(hasattr(failure, "_request_set_in_engine"))
        self.assertTrue(failure._request_set_in_scraper)

        # failure.value.response is not set
        self.assertIsInstance(failure.value, ZeroDivisionError)
        self.assertFalse(hasattr(failure.value, "response"))

    @defer.inlineCallbacks
    def test_downloader_middleware_process_exception_set_request(self):
        """
        An exception is raised but caught by the next middleware, which
        returns a Response with a specific 'request' attribute.
        Both the engine and the scraper process the response, but neither
        of them modifies it.
        """
        url = self.mockserver.url("/status?n=200")
        runner = CrawlerRunner(settings={
            "DOWNLOADER_MIDDLEWARES": {
                __name__ + ".RaiseExceptionMiddleware": 590,
                __name__ + ".CatchExceptionSetRequestMiddleware": 595,
            },
        })
        crawler = runner.create_crawler(SingleRequestSpider)
        yield crawler.crawl(seed=url, mockserver=self.mockserver)
        response = crawler.spider.meta["responses"][0]
        self.assertFalse(response._request_set_in_engine)
        self.assertFalse(response._request_set_in_scraper)
        self.assertEqual(response.body, b"ZeroDivisionError")
        self.assertEqual(response.request.url, "https://example.org")

    @defer.inlineCallbacks
    def test_downloader_middleware_process_exception_do_not_set_request(self):
        """
        An exception is raised but caught by the next middleware, which
        returns a Response without a specific 'request' attribute.
        Both the engine and the scraper process the response, the original
        request is set by the engine and not modified by the scraper.
        """
        url = self.mockserver.url("/status?n=200")
        runner = CrawlerRunner(settings={
            "DOWNLOADER_MIDDLEWARES": {
                __name__ + ".RaiseExceptionMiddleware": 590,
                __name__ + ".CatchExceptionDoNotSetRequestMiddleware": 595,
            },
        })
        crawler = runner.create_crawler(SingleRequestSpider)
        yield crawler.crawl(seed=url, mockserver=self.mockserver)
        response = crawler.spider.meta["responses"][0]
        self.assertTrue(response._request_set_in_engine)
        self.assertFalse(response._request_set_in_scraper)
        self.assertEqual(response.body, b"ZeroDivisionError")
        self.assertEqual(response.request.url, url)
