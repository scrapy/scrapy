from twisted.trial.unittest import TestCase
from twisted.python.failure import Failure

from scrapy.http import Request, Response
from scrapy.spider import BaseSpider
from scrapy.core.downloader.middleware import DownloaderMiddlewareManager
from scrapy.utils.test import get_crawler
from scrapy.stats import stats


class ManagerTestCase(TestCase):

    settings_dict = None

    def setUp(self):
        self.crawler = get_crawler(self.settings_dict)
        self.spider = BaseSpider('foo')
        self.spider.set_crawler(self.crawler)
        self.mwman = DownloaderMiddlewareManager.from_crawler(self.crawler)
        # some mw depends on stats collector
        stats.open_spider(self.spider)
        return self.mwman.open_spider(self.spider)

    def tearDown(self):
        stats.close_spider(self.spider, '')
        return self.mwman.close_spider(self.spider)

    def _download(self,request, response=None):
        """Executes downloader mw manager's download method and returns
        the result (Request or Response) or raise exception in case of
        failure.
        """
        if not response:
            response = Response(request.url, request=request)
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
        resp = Response(req.url, status=200, request=req)
        ret = self._download(req, resp)
        self.assertTrue(isinstance(resp, Response), "Non-response returned")


class GzippedRedirectionTest(ManagerTestCase):
    """Regression test for a failure when redirecting a compressed
    request.

    This happens when httpcompression middleware is executed before redirect
    middleware and attempts to decompress a non-compressed body.
    In particular when some website returns a 30x response with header
    'Content-Encoding: gzip' giving as result the error below:

        exceptions.IOError: Not a gzipped file

    """

    def test_gzipped_redirection(self):
        req = Request('http://example.com')
        body = '<p>You are being redirected</p>'
        resp = Response(req.url, status=302, body=body, request=req, headers={
            'Content-Length': len(body),
            'Content-Type': 'text/html',
            'Content-Encoding': 'gzip',
            'Location': 'http://example.com/login',
        })
        ret = self._download(request=req, response=resp)
        self.assertTrue(isinstance(ret, Request),
                        "Not redirected: {0!r}".format(ret))
        self.assertEqual(ret.url, resp.headers['Location'],
                         "Not redirected to location header")
