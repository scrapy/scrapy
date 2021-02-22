import asyncio
from unittest import mock, SkipTest

from pytest import mark
from twisted import version as twisted_version
from twisted.internet import defer
from twisted.internet.defer import Deferred
from twisted.trial.unittest import TestCase
from twisted.python.failure import Failure
from twisted.python.versions import Version

from scrapy.http import Request, Response
from scrapy.spiders import Spider
from scrapy.exceptions import _InvalidOutput
from scrapy.core.downloader.middleware import DownloaderMiddlewareManager
from scrapy.utils.test import get_crawler, get_from_asyncio_queue
from scrapy.utils.python import to_bytes


class ManagerTestCase(TestCase):

    settings_dict = None

    def setUp(self):
        self.crawler = get_crawler(Spider, self.settings_dict)
        self.spider = self.crawler._create_spider('foo')
        self.mwman = DownloaderMiddlewareManager.from_crawler(self.crawler)
        # some mw depends on stats collector
        self.crawler.stats.open_spider(self.spider)
        return self.mwman.open_spider(self.spider)

    def tearDown(self):
        self.crawler.stats.close_spider(self.spider, '')
        return self.mwman.close_spider(self.spider)

    def _download(self, request, response=None):
        """Executes downloader mw manager's download method and returns
        the result (Request or Response) or raise exception in case of
        failure.
        """
        if not response:
            response = Response(request.url)

        def download_func(**kwargs):
            return response

        dfd = self.mwman.download(download_func, request, self.spider)
        # catch deferred result and return the value
        results = []
        dfd.addBoth(results.append)
        self._wait(dfd)
        ret = results[0]
        if isinstance(ret, Failure):
            ret.raiseException()
        return ret


class DefaultsTest(ManagerTestCase):
    """Tests default behavior with default settings"""

    def test_request_response(self):
        req = Request('http://example.com/index.html')
        resp = Response(req.url, status=200)
        ret = self._download(req, resp)
        self.assertTrue(isinstance(ret, Response), "Non-response returned")

    def test_3xx_and_invalid_gzipped_body_must_redirect(self):
        """Regression test for a failure when redirecting a compressed
        request.

        This happens when httpcompression middleware is executed before redirect
        middleware and attempts to decompress a non-compressed body.
        In particular when some website returns a 30x response with header
        'Content-Encoding: gzip' giving as result the error below:

            exceptions.IOError: Not a gzipped file

        """
        req = Request('http://example.com')
        body = b'<p>You are being redirected</p>'
        resp = Response(req.url, status=302, body=body, headers={
            'Content-Length': str(len(body)),
            'Content-Type': 'text/html',
            'Content-Encoding': 'gzip',
            'Location': 'http://example.com/login',
        })
        ret = self._download(request=req, response=resp)
        self.assertTrue(isinstance(ret, Request),
                        f"Not redirected: {ret!r}")
        self.assertEqual(to_bytes(ret.url), resp.headers['Location'],
                         "Not redirected to location header")

    def test_200_and_invalid_gzipped_body_must_fail(self):
        req = Request('http://example.com')
        body = b'<p>You are being redirected</p>'
        resp = Response(req.url, status=200, body=body, headers={
            'Content-Length': str(len(body)),
            'Content-Type': 'text/html',
            'Content-Encoding': 'gzip',
            'Location': 'http://example.com/login',
        })
        self.assertRaises(IOError, self._download, request=req, response=resp)


class ResponseFromProcessRequestTest(ManagerTestCase):
    """Tests middleware returning a response from process_request."""

    def test_download_func_not_called(self):
        resp = Response('http://example.com/index.html')

        class ResponseMiddleware:
            def process_request(self, request, spider):
                return resp

        self.mwman._add_middleware(ResponseMiddleware())

        req = Request('http://example.com/index.html')
        download_func = mock.MagicMock()
        dfd = self.mwman.download(download_func, req, self.spider)
        results = []
        dfd.addBoth(results.append)
        self._wait(dfd)

        self.assertIs(results[0], resp)
        self.assertFalse(download_func.called)


class ProcessRequestInvalidOutput(ManagerTestCase):
    """Invalid return value for process_request method should raise an exception"""

    def test_invalid_process_request(self):
        req = Request('http://example.com/index.html')

        class InvalidProcessRequestMiddleware:
            def process_request(self, request, spider):
                return 1

        self.mwman._add_middleware(InvalidProcessRequestMiddleware())
        download_func = mock.MagicMock()
        dfd = self.mwman.download(download_func, req, self.spider)
        results = []
        dfd.addBoth(results.append)
        self.assertIsInstance(results[0], Failure)
        self.assertIsInstance(results[0].value, _InvalidOutput)


class ProcessResponseInvalidOutput(ManagerTestCase):
    """Invalid return value for process_response method should raise an exception"""

    def test_invalid_process_response(self):
        req = Request('http://example.com/index.html')

        class InvalidProcessResponseMiddleware:
            def process_response(self, request, response, spider):
                return 1

        self.mwman._add_middleware(InvalidProcessResponseMiddleware())
        download_func = mock.MagicMock()
        dfd = self.mwman.download(download_func, req, self.spider)
        results = []
        dfd.addBoth(results.append)
        self.assertIsInstance(results[0], Failure)
        self.assertIsInstance(results[0].value, _InvalidOutput)


class ProcessExceptionInvalidOutput(ManagerTestCase):
    """Invalid return value for process_exception method should raise an exception"""

    def test_invalid_process_exception(self):
        req = Request('http://example.com/index.html')

        class InvalidProcessExceptionMiddleware:
            def process_request(self, request, spider):
                raise Exception()

            def process_exception(self, request, exception, spider):
                return 1

        self.mwman._add_middleware(InvalidProcessExceptionMiddleware())
        download_func = mock.MagicMock()
        dfd = self.mwman.download(download_func, req, self.spider)
        results = []
        dfd.addBoth(results.append)
        self.assertIsInstance(results[0], Failure)
        self.assertIsInstance(results[0].value, _InvalidOutput)


class MiddlewareUsingDeferreds(ManagerTestCase):
    """Middlewares using Deferreds should work"""

    def test_deferred(self):
        resp = Response('http://example.com/index.html')

        class DeferredMiddleware:
            def cb(self, result):
                return result

            def process_request(self, request, spider):
                d = Deferred()
                d.addCallback(self.cb)
                d.callback(resp)
                return d

        self.mwman._add_middleware(DeferredMiddleware())
        req = Request('http://example.com/index.html')
        download_func = mock.MagicMock()
        dfd = self.mwman.download(download_func, req, self.spider)
        results = []
        dfd.addBoth(results.append)
        self._wait(dfd)

        self.assertIs(results[0], resp)
        self.assertFalse(download_func.called)


@mark.usefixtures('reactor_pytest')
class MiddlewareUsingCoro(ManagerTestCase):
    """Middlewares using asyncio coroutines should work"""

    def test_asyncdef(self):
        if (
            self.reactor_pytest == 'asyncio'
            and twisted_version < Version('twisted', 18, 4, 0)
        ):
            raise SkipTest(
                'Due to https://twistedmatrix.com/trac/ticket/9390, this test '
                'hangs when using AsyncIO and Twisted versions lower than '
                '18.4.0'
            )

        resp = Response('http://example.com/index.html')

        class CoroMiddleware:
            async def process_request(self, request, spider):
                await defer.succeed(42)
                return resp

        self.mwman._add_middleware(CoroMiddleware())
        req = Request('http://example.com/index.html')
        download_func = mock.MagicMock()
        dfd = self.mwman.download(download_func, req, self.spider)
        results = []
        dfd.addBoth(results.append)
        self._wait(dfd)

        self.assertIs(results[0], resp)
        self.assertFalse(download_func.called)

    @mark.only_asyncio()
    def test_asyncdef_asyncio(self):
        if twisted_version < Version('twisted', 18, 4, 0):
            raise SkipTest(
                'Due to https://twistedmatrix.com/trac/ticket/9390, this test '
                'hangs when using Twisted versions lower than 18.4.0'
            )

        resp = Response('http://example.com/index.html')

        class CoroMiddleware:
            async def process_request(self, request, spider):
                await asyncio.sleep(0.1)
                result = await get_from_asyncio_queue(resp)
                return result

        self.mwman._add_middleware(CoroMiddleware())
        req = Request('http://example.com/index.html')
        download_func = mock.MagicMock()
        dfd = self.mwman.download(download_func, req, self.spider)
        results = []
        dfd.addBoth(results.append)
        self._wait(dfd)

        self.assertIs(results[0], resp)
        self.assertFalse(download_func.called)
