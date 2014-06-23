from __future__ import print_function
import time
import tempfile
import shutil
import unittest
import email.utils
from contextlib import contextmanager
import pytest

from scrapy.http import Response, HtmlResponse, Request
from scrapy.spider import Spider
from scrapy.settings import Settings
from scrapy.exceptions import IgnoreRequest
from scrapy.utils.test import get_crawler
from scrapy.contrib.downloadermiddleware.httpcache import HttpCacheMiddleware


class _BaseTest(unittest.TestCase):

    storage_class = 'scrapy.contrib.httpcache.DbmCacheStorage'
    policy_class = 'scrapy.contrib.httpcache.RFC2616Policy'

    def setUp(self):
        self.yesterday = email.utils.formatdate(time.time() - 86400)
        self.today = email.utils.formatdate()
        self.tomorrow = email.utils.formatdate(time.time() + 86400)
        self.crawler = get_crawler()
        self.spider = Spider('example.com')
        self.tmpdir = tempfile.mkdtemp()
        self.request = Request('http://www.example.com',
                               headers={'User-Agent': 'test'})
        self.response = Response('http://www.example.com',
                                 headers={'Content-Type': 'text/html'},
                                 body='test body',
                                 status=202)
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
            'HTTPCACHE_POLICY': self.policy_class,
            'HTTPCACHE_STORAGE': self.storage_class,
        }
        settings.update(new_settings)
        return Settings(settings)

    @contextmanager
    def _storage(self, **new_settings):
        with self._middleware(**new_settings) as mw:
            yield mw.storage

    @contextmanager
    def _policy(self, **new_settings):
        with self._middleware(**new_settings) as mw:
            yield mw.policy

    @contextmanager
    def _middleware(self, **new_settings):
        settings = self._get_settings(**new_settings)
        mw = HttpCacheMiddleware(settings, self.crawler.stats)
        mw.spider_opened(self.spider)
        try:
            yield mw
        finally:
            mw.spider_closed(self.spider)

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
        assert not 'If-None-Match' in request1.headers
        assert not 'If-Modified-Since' in request1.headers
        assert any(h in request2.headers for h in ('If-None-Match', 'If-Modified-Since'))
        self.assertEqual(request1.body, request2.body)


class DefaultStorageTest(_BaseTest):

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


class DbmStorageTest(DefaultStorageTest):

    storage_class = 'scrapy.contrib.httpcache.DbmCacheStorage'


class DbmStorageWithCustomDbmModuleTest(DbmStorageTest):

    dbm_module = 'scrapy.tests.mocks.dummydbm'

    def _get_settings(self, **new_settings):
        new_settings.setdefault('HTTPCACHE_DBM_MODULE', self.dbm_module)
        return super(DbmStorageWithCustomDbmModuleTest, self)._get_settings(**new_settings)

    def test_custom_dbm_module_loaded(self):
        # make sure our dbm module has been loaded
        with self._storage() as storage:
            self.assertEqual(storage.dbmodule.__name__, self.dbm_module)


class FilesystemStorageTest(DefaultStorageTest):

    storage_class = 'scrapy.contrib.httpcache.FilesystemCacheStorage'


class LeveldbStorageTest(DefaultStorageTest):

    pytest.importorskip('leveldb')
    storage_class = 'scrapy.contrib.httpcache.LeveldbCacheStorage'


class DummyPolicyTest(_BaseTest):

    policy_class = 'scrapy.contrib.httpcache.DummyPolicy'

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


class RFC2616PolicyTest(DefaultStorageTest):

    policy_class = 'scrapy.contrib.httpcache.RFC2616Policy'

    def _process_requestresponse(self, mw, request, response):
        try:
            result = mw.process_request(request, self.spider)
            if result:
                assert isinstance(result, (Request, Response))
                return result
            else:
                result = mw.process_response(request, response, self.spider)
                assert isinstance(result, Response)
                return result
        except Exception:
            print('Request', request)
            print('Response', response)
            print('Result', result)
            raise

    def test_request_cacheability(self):
        res0 = Response(self.request.url, status=200,
                        headers={'Expires': self.tomorrow})
        req0 = Request('http://example.com')
        req1 = req0.replace(headers={'Cache-Control': 'no-store'})
        req2 = req0.replace(headers={'Cache-Control': 'no-cache'})
        with self._middleware() as mw:
            # response for a request with no-store must not be cached
            res1 = self._process_requestresponse(mw, req1, res0)
            self.assertEqualResponse(res1, res0)
            assert mw.storage.retrieve_response(self.spider, req1) is None
            # Re-do request without no-store and expect it to be cached
            res2 = self._process_requestresponse(mw, req0, res0)
            assert 'cached' not in res2.flags
            res3 = mw.process_request(req0, self.spider)
            assert 'cached' in res3.flags
            self.assertEqualResponse(res2, res3)
            # request with no-cache directive must not return cached response
            # but it allows new response to be stored
            res0b = res0.replace(body='foo')
            res4 = self._process_requestresponse(mw, req2, res0b)
            self.assertEqualResponse(res4, res0b)
            assert 'cached' not in res4.flags
            res5 = self._process_requestresponse(mw, req0, None)
            self.assertEqualResponse(res5, res0b)
            assert 'cached' in res5.flags

    def test_response_cacheability(self):
        responses = [
            # 304 is not cacheable no matter what servers sends
            (False, 304, {}),
            (False, 304, {'Last-Modified': self.yesterday}),
            (False, 304, {'Expires': self.tomorrow}),
            (False, 304, {'Etag': 'bar'}),
            (False, 304, {'Cache-Control': 'max-age=3600'}),
            # Always obey no-store cache control
            (False, 200, {'Cache-Control': 'no-store'}),
            (False, 200, {'Cache-Control': 'no-store, max-age=300'}),  # invalid
            (False, 200, {'Cache-Control': 'no-store', 'Expires': self.tomorrow}),  # invalid
            # Ignore responses missing expiration and/or validation headers
            (False, 200, {}),
            (False, 302, {}),
            (False, 307, {}),
            (False, 404, {}),
            # Cache responses with expiration and/or validation headers
            (True, 200, {'Last-Modified': self.yesterday}),
            (True, 203, {'Last-Modified': self.yesterday}),
            (True, 300, {'Last-Modified': self.yesterday}),
            (True, 301, {'Last-Modified': self.yesterday}),
            (True, 401, {'Last-Modified': self.yesterday}),
            (True, 404, {'Cache-Control': 'public, max-age=600'}),
            (True, 302, {'Expires': self.tomorrow}),
            (True, 200, {'Etag': 'foo'}),
        ]
        with self._middleware() as mw:
            for idx, (shouldcache, status, headers) in enumerate(responses):
                req0 = Request('http://example-%d.com' % idx)
                res0 = Response(req0.url, status=status, headers=headers)
                res1 = self._process_requestresponse(mw, req0, res0)
                res304 = res0.replace(status=304)
                res2 = self._process_requestresponse(mw, req0, res304 if shouldcache else res0)
                self.assertEqualResponse(res1, res0)
                self.assertEqualResponse(res2, res0)
                resc = mw.storage.retrieve_response(self.spider, req0)
                if shouldcache:
                    self.assertEqualResponse(resc, res1)
                    assert 'cached' in res2.flags and res2.status != 304
                else:
                    self.assertFalse(resc)
                    assert 'cached' not in res2.flags

    def test_cached_and_fresh(self):
        sampledata = [
            (200, {'Date': self.yesterday, 'Expires': self.tomorrow}),
            (200, {'Date': self.yesterday, 'Cache-Control': 'max-age=86405'}),
            (200, {'Age': '299', 'Cache-Control': 'max-age=300'}),
            # Obey max-age if present over any others
            (200, {'Date': self.today,
                   'Age': '86405',
                   'Cache-Control': 'max-age=' + str(86400 * 3),
                   'Expires': self.yesterday,
                   'Last-Modified': self.yesterday,
                   }),
            # obey Expires if max-age is not present
            (200, {'Date': self.yesterday,
                   'Age': '86400',
                   'Cache-Control': 'public',
                   'Expires': self.tomorrow,
                   'Last-Modified': self.yesterday,
                   }),
            # Default missing Date header to right now
            (200, {'Expires': self.tomorrow}),
            # Firefox - Expires if age is greater than 10% of (Date - Last-Modified)
            (200, {'Date': self.today, 'Last-Modified': self.yesterday, 'Age': str(86400 / 10 - 1)}),
            # Firefox - Set one year maxage to permanent redirects missing expiration info
            (300, {}), (301, {}), (308, {}),
        ]
        with self._middleware() as mw:
            for idx, (status, headers) in enumerate(sampledata):
                req0 = Request('http://example-%d.com' % idx)
                res0 = Response(req0.url, status=status, headers=headers)
                # cache fresh response
                res1 = self._process_requestresponse(mw, req0, res0)
                self.assertEqualResponse(res1, res0)
                assert 'cached' not in res1.flags
                # return fresh cached response without network interaction
                res2 = self._process_requestresponse(mw, req0, None)
                self.assertEqualResponse(res1, res2)
                assert 'cached' in res2.flags

    def test_cached_and_stale(self):
        sampledata = [
            (200, {'Date': self.today, 'Expires': self.yesterday}),
            (200, {'Date': self.today, 'Expires': self.yesterday, 'Last-Modified': self.yesterday}),
            (200, {'Expires': self.yesterday}),
            (200, {'Expires': self.yesterday, 'ETag': 'foo'}),
            (200, {'Expires': self.yesterday, 'Last-Modified': self.yesterday}),
            (200, {'Expires': self.tomorrow, 'Age': '86405'}),
            (200, {'Cache-Control': 'max-age=86400', 'Age': '86405'}),
            # no-cache forces expiration, also revalidation if validators exists
            (200, {'Cache-Control': 'no-cache'}),
            (200, {'Cache-Control': 'no-cache', 'ETag': 'foo'}),
            (200, {'Cache-Control': 'no-cache', 'Last-Modified': self.yesterday}),
        ]
        with self._middleware() as mw:
            for idx, (status, headers) in enumerate(sampledata):
                req0 = Request('http://example-%d.com' % idx)
                res0a = Response(req0.url, status=status, headers=headers)
                # cache expired response
                res1 = self._process_requestresponse(mw, req0, res0a)
                self.assertEqualResponse(res1, res0a)
                assert 'cached' not in res1.flags
                # Same request but as cached response is stale a new response must
                # be returned
                res0b = res0a.replace(body='bar')
                res2 = self._process_requestresponse(mw, req0, res0b)
                self.assertEqualResponse(res2, res0b)
                assert 'cached' not in res2.flags
                # Previous response expired too, subsequent request to same
                # resource must revalidate and succeed on 304 if validators
                # are present
                if 'ETag' in headers or 'Last-Modified' in headers:
                    res0c = res0b.replace(status=304)
                    res3 = self._process_requestresponse(mw, req0, res0c)
                    self.assertEqualResponse(res3, res0b)
                    assert 'cached' in res3.flags


if __name__ == '__main__':
    unittest.main()
