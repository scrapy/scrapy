import time
import tempfile
import shutil
import unittest
import email.utils
from contextlib import contextmanager

from scrapy.http import Response, HtmlResponse, Request
from scrapy.spider import BaseSpider
from scrapy.settings import Settings
from scrapy.exceptions import IgnoreRequest
from scrapy.utils.test import get_crawler
from scrapy.contrib.downloadermiddleware.httpcache import \
    FilesystemCacheStorage, HttpCacheMiddleware
from scrapy.contrib.httpcache import DbmRealCacheStorage


class HttpCacheMiddlewareTest(unittest.TestCase):

    storage_class = FilesystemCacheStorage
    realcache_storage_class = DbmRealCacheStorage

    yesterday = email.utils.formatdate(time.time() - 1 * 24 * 60 * 60)
    now = email.utils.formatdate()
    tomorrow = email.utils.formatdate(time.time() + 1 * 24 * 60 * 60)

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
            'HTTPCACHE_USE_DUMMY': True,
            'HTTPCACHE_DIR': self.tmpdir,
            'HTTPCACHE_EXPIRATION_SECS': 1,
            'HTTPCACHE_IGNORE_HTTP_CODES': [],
        }
        settings.update(new_settings)
        return Settings(settings)

    @contextmanager
    def _storage(self, **new_settings):
        settings = self._get_settings(**new_settings)
        if settings.getbool('HTTPCACHE_USE_DUMMY'):
            storage = self.storage_class(settings)
        else:
            storage = self.realcache_storage_class(settings)
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

    def test_real_http_cache_middleware_response304_not_cached(self):
        # test response is not cached because the status is 304 Not Modified
        # (so it should be cached already)
        with self._middleware(HTTPCACHE_USE_DUMMY=False) as mw:
            assert mw.process_request(self.request, self.spider) is None
            response = Response('http://www.example.com', status=304)
            mw.process_response(self.request, response, self.spider)

            assert 'cached' in response.flags
            assert mw.storage.retrieve_response(self.spider, self.request) is None
            assert mw.process_request(self.request, self.spider) is None

    def test_real_http_cache_middleware_response_nostore_not_cached(self):
        # test response is not cached because of the Cache-Control 'no-store' directive
        # http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html#sec14.9.2
        with self._middleware(HTTPCACHE_USE_DUMMY=False) as mw:
            assert mw.process_request(self.request, self.spider) is None
            response = Response('http://www.example.com', headers=
                {'Content-Type': 'text/html', 'Cache-Control': 'no-store'},
                body='test body', status=200)
            mw.process_response(self.request, response, self.spider)

            assert mw.storage.retrieve_response(self.spider, self.request) is None
            assert mw.process_request(self.request, self.spider) is None

    def test_real_http_cache_middleware_request_nostore_not_cached(self):
        # test response is not cached because of the request's Cache-Control 'no-store' directive
        # http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html#sec14.9.2
        with self._middleware(HTTPCACHE_USE_DUMMY=False) as mw:
            request = Request('http://www.example.com',
                headers={'User-Agent': 'test', 'Cache-Control': 'no-store'})
            assert mw.process_request(request, self.spider) is None
            mw.process_response(request, self.response, self.spider)

            assert mw.storage.retrieve_response(self.spider, request) is None
            assert mw.process_request(request, self.spider) is None

    def test_real_http_cache_middleware_response_cached_and_fresh(self):
        # test response cached and fresh
        with self._middleware(HTTPCACHE_USE_DUMMY=False) as mw:
            response = mw.process_response(self.request, self.response, self.spider)
            self.assertRaises(IgnoreRequest, mw.process_request, self.request, self.spider)
            assert 'cached' not in response.flags

    def test_real_http_cache_middleware_response_cached_and_stale(self):
        # test response cached but stale
        with self._middleware(HTTPCACHE_USE_DUMMY=False,
            HTTPCACHE_STORAGE = 'scrapy.contrib.httpcache.DbmRealCacheStorage') as mw:
            response = Response('http://www.example.com', headers=
                {'Content-Type': 'text/html', 'Cache-Control': 'no-cache'},
                body='test body', status=200)
            mw.process_response(self.request, response, self.spider)
            assert mw.process_request(self.request, self.spider) is None

            response = mw.storage.retrieve_response(self.spider, self.request)
            assert isinstance(response, Request)

    def test_real_http_cache_storage_response_cached_and_fresh(self):
        # test response is cached and is fresh
        # (response requested should be same as response received)
        with self._storage(HTTPCACHE_USE_DUMMY=False) as storage:
            assert storage.retrieve_response(self.spider, self.request) is None

            response = Response('http://www.example.com', headers=
                {'Content-Type': 'text/html', 'Date': self.yesterday, 'Expires': self.tomorrow},
                body='test body', status=200)
            storage.store_response(self.spider, self.request, response)
            response2 = storage.retrieve_response(self.spider, self.request)
            self.assertEqualResponse(response, response2)

    def test_real_http_cache_storage_response403_cached_and_further_requests_ignored(self):
        # test response is cached but further requests are ignored
        # because response status is 403 (as per the RFC)
        with self._storage(HTTPCACHE_USE_DUMMY=False) as storage:
            assert storage.retrieve_response(self.spider, self.request) is None

            response = Response('http://www.example.com', headers=
                {'Content-Type': 'text/html', 'Date': self.yesterday, 'Expires': self.tomorrow},
                body='test body', status=403)
            storage.store_response(self.spider, self.request, response)
            self.assertRaises(IgnoreRequest, storage.retrieve_response,
                self.spider, self.request)

    def test_real_http_cache_storage_response_cached_and_stale(self):
        # test response is cached and is stale (no cache validators inserted)
        # (request should be same as response received)
        with self._storage(HTTPCACHE_USE_DUMMY=False) as storage:
            assert storage.retrieve_response(self.spider, self.request) is None

            response = Response('http://www.example.com', headers=
                {'Content-Type': 'text/html', 'Date': self.now, 'Expires': self.yesterday},
                body='test body', status=200)
            storage.store_response(self.spider, self.request, response)
            response2 = storage.retrieve_response(self.spider, self.request)
            assert isinstance(response2, Request)
            self.assertEqualRequest(self.request, response2)

    def test_real_http_cache_storage_response_cached_and_stale_with_cache_validators(self):
        # test response is cached and is stale and cache validators are inserted
        with self._storage(HTTPCACHE_USE_DUMMY=False) as storage:
            assert storage.retrieve_response(self.spider, self.request) is None

            response = Response('http://www.example.com', headers=
                {'Content-Type': 'text/html', 'Date': self.now, 'Expires': self.yesterday,
                'Last-Modified': self.yesterday}, body='test body', status=200)
            storage.store_response(self.spider, self.request, response)
            response2 = storage.retrieve_response(self.spider, self.request)
            assert isinstance(response2, Request)
            self.assertEqualRequestButWithCacheValidators(self.request, response2)

    def test_real_http_cache_storage_response_cached_and_transparent(self):
        # test response is not cached because of the request's Cache-Control 'no-cache' directive
        # http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html#sec14.9.2
        with self._storage(HTTPCACHE_USE_DUMMY=False) as storage:
            request = Request('http://www.example.com',
                headers={'User-Agent': 'test', 'Cache-Control': 'no-cache'})
            assert storage.retrieve_response(self.spider, request) is None
            storage.store_response(self.spider, request, self.response)
            response = storage.retrieve_response(self.spider, request)
            assert isinstance(response, Request)
            self.assertEqualRequest(request, response)

    def assertEqualResponse(self, response1, response2):
        self.assertEqual(response1.url, response2.url)
        self.assertEqual(response1.status, response2.status)
        self.assertEqual(response1.headers, response2.headers)
        self.assertEqual(response1.body, response2.body)

    def assertEqualRequest(self, request1, request2):
        self.assertEqual(request1.url, request2.url)
        self.assertEqual(request1.headers, request2.headers)
        self.assertEqual(request1.body, request2.body)

    def assertEqualRequestButWithCacheValidators(self, request1, request2):
        self.assertEqual(request1.url, request2.url)
        assert not request1.headers.has_key('If-None-Match')
        assert not request1.headers.has_key('If-Modified-Since')
        assert (request2.headers.has_key('If-None-Match') or \
            request2.headers.has_key('If-Modified-Since'))
        self.assertEqual(request1.body, request2.body)

if __name__ == '__main__':
    unittest.main()
