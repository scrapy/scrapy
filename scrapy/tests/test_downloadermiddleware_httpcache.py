import unittest, tempfile, shutil, time

from scrapy.http import Response, HtmlResponse, Request
from scrapy.spider import BaseSpider
from scrapy.contrib.downloadermiddleware.httpcache import FilesystemCacheStorage, HttpCacheMiddleware
from scrapy.conf import Settings
from scrapy.core.exceptions import IgnoreRequest


class HttpCacheMiddlewareTest(unittest.TestCase):

    storage_class = FilesystemCacheStorage

    def setUp(self):
        self.spider = BaseSpider('example.com')
        self.tmpdir = tempfile.mkdtemp()
        self.request = Request('http://www.example.com', headers={'User-Agent': 'test'})
        self.response = Response('http://www.example.com', headers={'Content-Type': 'text/html'}, body='test body', status=202)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    def _get_settings(self, **new_settings):
        settings = {
            'HTTPCACHE_DIR': self.tmpdir,
            'HTTPCACHE_EXPIRATION_SECS': 1,
            'HTTPCACHE_IGNORE_HTTP_CODES': [],
        }
        settings.update(new_settings)
        return Settings(settings)

    def _get_storage(self, **new_settings):
        return self.storage_class(self._get_settings(**new_settings))

    def _get_middleware(self, **new_settings):
        return HttpCacheMiddleware(self._get_settings(**new_settings))

    def test_storage(self):
        storage = self._get_storage()
        request2 = self.request.copy()
        assert storage.retrieve_response(self.spider, request2) is None
        storage.store_response(self.spider, self.request, self.response)
        response2 = storage.retrieve_response(self.spider, request2)
        assert isinstance(response2, HtmlResponse) # inferred from content-type header
        self.assertEqualResponse(self.response, response2)
        time.sleep(2) # wait for cache to expire
        assert storage.retrieve_response(self.spider, request2) is None

    def test_storage_expire_immediately(self):
        storage = self._get_storage(HTTPCACHE_EXPIRATION_SECS=0)
        assert storage.retrieve_response(self.spider, self.request) is None
        storage.store_response(self.spider, self.request, self.response)
        time.sleep(0.1) # required for win32
        assert storage.retrieve_response(self.spider, self.request) is None

    def test_storage_never_expire(self):
        storage = self._get_storage(HTTPCACHE_EXPIRATION_SECS=-1)
        assert storage.retrieve_response(self.spider, self.request) is None
        storage.store_response(self.spider, self.request, self.response)
        assert storage.retrieve_response(self.spider, self.request)

    def test_middleware(self):
        mw = HttpCacheMiddleware(self._get_settings())
        assert mw.process_request(self.request, self.spider) is None
        mw.process_response(self.request, self.response, self.spider)
        response = mw.process_request(self.request, self.spider)
        assert isinstance(response, HtmlResponse)
        self.assertEqualResponse(self.response, response)
        assert 'cached' in response.flags

    def test_middleware_ignore_missing(self):
        mw = self._get_middleware(HTTPCACHE_IGNORE_MISSING=True)
        self.assertRaises(IgnoreRequest, mw.process_request, self.request, self.spider)
        mw.process_response(self.request, self.response, self.spider)
        response = mw.process_request(self.request, self.spider)
        assert isinstance(response, HtmlResponse)
        self.assertEqualResponse(self.response, response)
        assert 'cached' in response.flags

    def test_middleware_ignore_http_codes(self):
        # test response is not cached
        mw = self._get_middleware(HTTPCACHE_IGNORE_HTTP_CODES=[202])
        assert mw.process_request(self.request, self.spider) is None
        mw.process_response(self.request, self.response, self.spider)
        assert mw.storage.retrieve_response(self.spider, self.request) is None
        assert mw.process_request(self.request, self.spider) is None

        # test response is cached
        mw = self._get_middleware(HTTPCACHE_IGNORE_HTTP_CODES=[203])
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

