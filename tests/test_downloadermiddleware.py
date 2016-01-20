from twisted.trial.unittest import TestCase
from twisted.python.failure import Failure

from scrapy.http import Request, Response
from scrapy.spiders import Spider
from scrapy.core.downloader.middleware import DownloaderMiddlewareManager
from scrapy.utils.test import get_crawler
from scrapy.utils.python import to_bytes
from tests import mock


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
                        "Not redirected: {0!r}".format(ret))
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

        class ResponseMiddleware(object):
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
