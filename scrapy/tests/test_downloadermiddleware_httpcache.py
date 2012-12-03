import time
import tempfile
import shutil
import unittest
from contextlib import contextmanager

from scrapy.http import Response, HtmlResponse, Request
from scrapy.spider import BaseSpider
from scrapy.settings import Settings
from scrapy.exceptions import IgnoreRequest
from scrapy.utils.test import get_crawler
from scrapy.contrib.downloadermiddleware.httpcache import \
    FilesystemCacheStorage, HttpCacheMiddleware


class HttpCacheMiddlewareTest(unittest.TestCase):

    storage_class = FilesystemCacheStorage

    def setUp(self):
        self.crawler = get_crawler()
        self.spider = BaseSpider('example.com')
        self.tmpdir = tempfile.mkdtemp()
        self.request = Request('http://www.example.com',
            headers={'User-Agent': 'test'})
        self.response = Response('http://www.example.com', headers=
            {'Content-Type': 'text/html'}, body='test body', status=202)
        self.crawler.stats.open_spider(self.spider)

    def tearDown(self):
        self.crawler.stats.close_spider(self.spider, '')
        shutil.rmtree(self.tmpdir)

    def _get_settings(self, **new_settings):
        settings = {
            'HTTPCACHE_ENABLED': True,
            'HTTPCACHE_DIR': self.tmpdir,
            'HTTPCACHE_EXPIRATION_SECS': 1,
            'HTTPCACHE_IGNORE_HTTP_CODES': [],
        }
        settings.update(new_settings)
        return Settings(settings)

    @contextmanager
    def _storage(self, **new_settings):
        settings = self._get_settings(**new_settings)
        storage = self.storage_class(settings)
        storage.open_spider(self.spider)
        try:
            yield storage
        finally:
            storage.close_spider(self.spider)

    @contextmanager
    def _middleware(self, **new_settings):
        settings = self._get_settings(**new_settings)
        mw = HttpCacheMiddleware(settings, self.crawler.stats)
        mw.spider_opened(self.spider)
        try:
            yield mw
        finally:
            mw.spider_closed(self.spider)

    def test_storage(self):
        with self._storage() as storage:
            request2 = self.request.copy()
            assert storage.retrieve_response(self.spider, request2) is None

            storage.store_response(self.spider, self.request, self.response)
            response2 = storage.retrieve_response(self.spider, request2)
            assert isinstance(response2, HtmlResponse)  # content-type header
            self.assertEqualResponse(self.response, response2)

            time.sleep(2)  # wait for cache to expire
            assert storage.retrieve_response(self.spider, request2) is None

    def test_storage_never_expire(self):
        with self._storage(HTTPCACHE_EXPIRATION_SECS=0) as storage:
            assert storage.retrieve_response(self.spider, self.request) is None
            storage.store_response(self.spider, self.request, self.response)
            time.sleep(0.5)  # give the chance to expire
            assert storage.retrieve_response(self.spider, self.request)

    def test_middleware(self):
        with self._middleware() as mw:
            assert mw.process_request(self.request, self.spider) is None
            mw.process_response(self.request, self.response, self.spider)

            response = mw.process_request(self.request, self.spider)
            assert isinstance(response, HtmlResponse)
            self.assertEqualResponse(self.response, response)
            assert 'cached' in response.flags

    def test_different_request_response_urls(self):
        with self._middleware() as mw:
            req = Request('http://host.com/path')
            res = Response('http://host2.net/test.html')

            assert mw.process_request(req, self.spider) is None
            mw.process_response(req, res, self.spider)

            cached = mw.process_request(req, self.spider)
            assert isinstance(cached, Response)
            self.assertEqualResponse(res, cached)
            assert 'cached' in cached.flags

    def test_middleware_ignore_missing(self):
        with self._middleware(HTTPCACHE_IGNORE_MISSING=True) as mw:
            self.assertRaises(IgnoreRequest, mw.process_request, self.request, self.spider)
            mw.process_response(self.request, self.response, self.spider)
            response = mw.process_request(self.request, self.spider)
            assert isinstance(response, HtmlResponse)
            self.assertEqualResponse(self.response, response)
            assert 'cached' in response.flags

    def test_middleware_ignore_schemes(self):
        # http responses are cached by default
        req, res = Request('http://test.com/'), Response('http://test.com/')
        with self._middleware() as mw:
            assert mw.process_request(req, self.spider) is None
            mw.process_response(req, res, self.spider)

            cached = mw.process_request(req, self.spider)
            assert isinstance(cached, Response), type(cached)
            self.assertEqualResponse(res, cached)
            assert 'cached' in cached.flags

        # file response is not cached by default
        req, res = Request('file:///tmp/t.txt'), Response('file:///tmp/t.txt')
        with self._middleware() as mw:
            assert mw.process_request(req, self.spider) is None
            mw.process_response(req, res, self.spider)

            assert mw.storage.retrieve_response(self.spider, req) is None
            assert mw.process_request(req, self.spider) is None

        # s3 scheme response is cached by default
        req, res = Request('s3://bucket/key'), Response('http://bucket/key')
        with self._middleware() as mw:
            assert mw.process_request(req, self.spider) is None
            mw.process_response(req, res, self.spider)

            cached = mw.process_request(req, self.spider)
            assert isinstance(cached, Response), type(cached)
            self.assertEqualResponse(res, cached)
            assert 'cached' in cached.flags

        # ignore s3 scheme
        req, res = Request('s3://bucket/key2'), Response('http://bucket/key2')
        with self._middleware(HTTPCACHE_IGNORE_SCHEMES=['s3']) as mw:
            assert mw.process_request(req, self.spider) is None
            mw.process_response(req, res, self.spider)

            assert mw.storage.retrieve_response(self.spider, req) is None
            assert mw.process_request(req, self.spider) is None

    def test_middleware_ignore_http_codes(self):
        # test response is not cached
        with self._middleware(HTTPCACHE_IGNORE_HTTP_CODES=[202]) as mw:
            assert mw.process_request(self.request, self.spider) is None
            mw.process_response(self.request, self.response, self.spider)

            assert mw.storage.retrieve_response(self.spider, self.request) is None
            assert mw.process_request(self.request, self.spider) is None

        # test response is cached
        with self._middleware(HTTPCACHE_IGNORE_HTTP_CODES=[203]) as mw:
            mw.process_response(self.request, self.response, self.spider)
            response = mw.process_request(self.request, self.spider)
            assert isinstance(response, HtmlResponse)
            self.assertEqualResponse(self.response, response)
            assert 'cached' in response.flags

    def assertEqualResponse(self, response1, response2):
        self.assertEqual(response1.url, response2.url)
        self.assertEqual(response1.status, response2.status)
        self.assertEqual(response1.headers, response2.headers)
        self.assertEqual(response1.body, response2.body)

if __name__ == '__main__':
    unittest.main()
