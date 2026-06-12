from __future__ import annotations

import email.utils
import shutil
import tempfile
import time
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import pytest

from scrapy.downloadermiddlewares.httpcache import HttpCacheMiddleware
from scrapy.exceptions import IgnoreRequest
from scrapy.extensions.httpcache import FilesystemCacheStorage
from scrapy.http import HtmlResponse, Request, Response
from scrapy.spiders import Spider
from scrapy.utils.defer import ensure_awaitable
from scrapy.utils.test import get_crawler
from tests.utils import async_sleep
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from scrapy.crawler import Crawler


class TestBase:
    """Base class with common setup and helper methods."""

    policy_class: str
    storage_class: str

    def setup_method(self):
        self.yesterday = email.utils.formatdate(time.time() - 86400)
        self.today = email.utils.formatdate()
        self.tomorrow = email.utils.formatdate(time.time() + 86400)
        self.tmpdir = tempfile.mkdtemp()
        self.request = Request("http://www.example.com", headers={"User-Agent": "test"})
        self.response = Response(
            "http://www.example.com",
            headers={"Content-Type": "text/html"},
            body=b"test body",
            status=202,
        )

    def teardown_method(self):
        shutil.rmtree(self.tmpdir)

    def _get_settings(self, **new_settings: Any) -> dict[str, Any]:
        settings = {
            "HTTPCACHE_ENABLED": True,
            "HTTPCACHE_DIR": self.tmpdir,
            "HTTPCACHE_EXPIRATION_SECS": 1,
            "HTTPCACHE_IGNORE_HTTP_CODES": [],
            "HTTPCACHE_POLICY": self.policy_class,
            "HTTPCACHE_STORAGE": self.storage_class,
        }
        settings.update(new_settings)
        return settings

    @asynccontextmanager
    async def _get_crawler(self, **new_settings: Any) -> AsyncGenerator[Crawler, None]:
        settings = self._get_settings(**new_settings)
        crawler = get_crawler(Spider, settings)
        crawler.spider = crawler._create_spider("example.com")
        assert crawler.stats
        crawler.stats.open_spider()
        try:
            yield crawler
        finally:
            crawler.stats.close_spider()

    @asynccontextmanager
    async def _storage(
        self, **new_settings: Any
    ) -> AsyncGenerator[tuple[Any, Crawler], None]:
        async with self._middleware(**new_settings) as mw:
            yield mw.storage, mw.crawler

    @asynccontextmanager
    async def _middleware(
        self, **new_settings: Any
    ) -> AsyncGenerator[HttpCacheMiddleware, None]:
        async with self._get_crawler(**new_settings) as crawler:
            assert crawler.spider
            mw = HttpCacheMiddleware.from_crawler(crawler)
            await mw.spider_opened(crawler.spider)
            try:
                yield mw
            finally:
                await mw.spider_closed(crawler.spider)

    def assertEqualResponse(self, response1, response2):
        assert response1.url == response2.url
        assert response1.status == response2.status
        assert response1.headers == response2.headers
        assert response1.body == response2.body


class StorageTestMixin:
    """Mixin containing storage-specific test methods."""

    @coroutine_test
    async def test_storage(self):
        async with self._storage() as (storage, crawler):
            request2 = self.request.copy()
            assert (
                await ensure_awaitable(
                    storage.retrieve_response(crawler.spider, request2)
                )
                is None
            )

            await ensure_awaitable(
                storage.store_response(crawler.spider, self.request, self.response)
            )
            response2 = await ensure_awaitable(
                storage.retrieve_response(crawler.spider, request2)
            )
            assert isinstance(response2, HtmlResponse)  # content-type header
            self.assertEqualResponse(self.response, response2)

            await async_sleep(2)  # wait for cache to expire
            assert (
                await ensure_awaitable(
                    storage.retrieve_response(crawler.spider, request2)
                )
                is None
            )

    @coroutine_test
    async def test_storage_never_expire(self):
        async with self._storage(HTTPCACHE_EXPIRATION_SECS=0) as (storage, crawler):
            assert (
                await ensure_awaitable(
                    storage.retrieve_response(crawler.spider, self.request)
                )
                is None
            )
            await ensure_awaitable(
                storage.store_response(crawler.spider, self.request, self.response)
            )
            await async_sleep(0.5)  # give the chance to expire
            assert await ensure_awaitable(
                storage.retrieve_response(crawler.spider, self.request)
            )

    @coroutine_test
    async def test_storage_no_content_type_header(self):
        """Test that the response body is used to get the right response class
        even if there is no Content-Type header"""
        async with self._storage() as (storage, crawler):
            assert (
                await ensure_awaitable(
                    storage.retrieve_response(crawler.spider, self.request)
                )
                is None
            )
            response = Response(
                "http://www.example.com",
                body=b"<!DOCTYPE html>\n<title>.</title>",
                status=202,
            )
            await ensure_awaitable(
                storage.store_response(crawler.spider, self.request, response)
            )
            cached_response = await ensure_awaitable(
                storage.retrieve_response(crawler.spider, self.request)
            )
            assert isinstance(cached_response, HtmlResponse)
            self.assertEqualResponse(response, cached_response)


class PolicyTestMixin:
    """Mixin containing policy-specific test methods."""

    @coroutine_test
    async def test_dont_cache(self):
        async with self._middleware() as mw:
            self.request.meta["dont_cache"] = True
            await mw.process_response(self.request, self.response)
            assert (
                await ensure_awaitable(
                    mw.storage.retrieve_response(mw.crawler.spider, self.request)
                )
                is None
            )

        async with self._middleware() as mw:
            self.request.meta["dont_cache"] = False
            await mw.process_response(self.request, self.response)
            if mw.policy.should_cache_response(self.response, self.request):
                assert isinstance(
                    await ensure_awaitable(
                        mw.storage.retrieve_response(mw.crawler.spider, self.request)
                    ),
                    self.response.__class__,
                )


class DummyPolicyTestMixin(PolicyTestMixin):
    """Mixin containing dummy policy specific test methods."""

    @coroutine_test
    async def test_middleware(self):
        async with self._middleware() as mw:
            assert await mw.process_request(self.request) is None
            await mw.process_response(self.request, self.response)
            response = await mw.process_request(self.request)
            assert isinstance(response, HtmlResponse)
            self.assertEqualResponse(self.response, response)
            assert "cached" in response.flags

    @coroutine_test
    async def test_different_request_response_urls(self):
        async with self._middleware() as mw:
            req = Request("http://host.com/path")
            res = Response("http://host2.net/test.html")
            assert await mw.process_request(req) is None
            await mw.process_response(req, res)
            cached = await mw.process_request(req)
            assert isinstance(cached, Response)
            self.assertEqualResponse(res, cached)
            assert "cached" in cached.flags

    @coroutine_test
    async def test_middleware_ignore_missing(self):
        async with self._middleware(HTTPCACHE_IGNORE_MISSING=True) as mw:
            with pytest.raises(IgnoreRequest):
                await mw.process_request(self.request)
            await mw.process_response(self.request, self.response)
            response = await mw.process_request(self.request)
            assert isinstance(response, HtmlResponse)
            self.assertEqualResponse(self.response, response)
            assert "cached" in response.flags

    @coroutine_test
    async def test_middleware_ignore_schemes(self):
        # http responses are cached by default
        req, res = Request("http://test.com/"), Response("http://test.com/")
        async with self._middleware() as mw:
            assert await mw.process_request(req) is None
            await mw.process_response(req, res)

            cached = await mw.process_request(req)
            assert isinstance(cached, Response), type(cached)
            self.assertEqualResponse(res, cached)
            assert "cached" in cached.flags

        # file response is not cached by default
        req, res = Request("file:///tmp/t.txt"), Response("file:///tmp/t.txt")
        async with self._middleware() as mw:
            assert await mw.process_request(req) is None
            await mw.process_response(req, res)

            assert (
                await ensure_awaitable(
                    mw.storage.retrieve_response(mw.crawler.spider, req)
                )
                is None
            )
            assert await mw.process_request(req) is None

        # s3 scheme response is cached by default
        req, res = Request("s3://bucket/key"), Response("http://bucket/key")
        async with self._middleware() as mw:
            assert await mw.process_request(req) is None
            await mw.process_response(req, res)

            cached = await mw.process_request(req)
            assert isinstance(cached, Response), type(cached)
            self.assertEqualResponse(res, cached)
            assert "cached" in cached.flags

        # ignore s3 scheme
        req, res = Request("s3://bucket/key2"), Response("http://bucket/key2")
        async with self._middleware(HTTPCACHE_IGNORE_SCHEMES=["s3"]) as mw:
            assert await mw.process_request(req) is None
            await mw.process_response(req, res)

            assert (
                await ensure_awaitable(
                    mw.storage.retrieve_response(mw.crawler.spider, req)
                )
                is None
            )
            assert await mw.process_request(req) is None

    @coroutine_test
    async def test_middleware_ignore_http_codes(self):
        # test response is not cached
        async with self._middleware(HTTPCACHE_IGNORE_HTTP_CODES=[202]) as mw:
            assert await mw.process_request(self.request) is None
            await mw.process_response(self.request, self.response)

            assert (
                await ensure_awaitable(
                    mw.storage.retrieve_response(mw.crawler.spider, self.request)
                )
                is None
            )
            assert await mw.process_request(self.request) is None

        # test response is cached
        async with self._middleware(HTTPCACHE_IGNORE_HTTP_CODES=[203]) as mw:
            await mw.process_response(self.request, self.response)
            response = await mw.process_request(self.request)
            assert isinstance(response, HtmlResponse)
            self.assertEqualResponse(self.response, response)
            assert "cached" in response.flags


class RFC2616PolicyTestMixin(PolicyTestMixin):
    """Mixin containing RFC2616 policy specific test methods."""

    @staticmethod
    async def _process_requestresponse(
        mw: HttpCacheMiddleware, request: Request, response: Response | None
    ) -> Response | Request:
        result = None
        try:
            result = await mw.process_request(request)
            if result:
                assert isinstance(result, (Request, Response))
                return result
            assert response is not None
            result = await mw.process_response(request, response)
            assert isinstance(result, Response)
            return result
        except Exception:
            print("Request", request)
            print("Response", response)
            print("Result", result)
            raise

    @coroutine_test
    async def test_request_cacheability(self):
        res0 = Response(
            self.request.url, status=200, headers={"Expires": self.tomorrow}
        )
        req0 = Request("http://example.com")
        req1 = req0.replace(headers={"Cache-Control": "no-store"})
        req2 = req0.replace(headers={"Cache-Control": "no-cache"})
        async with self._middleware() as mw:
            # response for a request with no-store must not be cached
            res1 = await self._process_requestresponse(mw, req1, res0)
            self.assertEqualResponse(res1, res0)
            assert (
                await ensure_awaitable(
                    mw.storage.retrieve_response(mw.crawler.spider, req1)
                )
                is None
            )
            # Re-do request without no-store and expect it to be cached
            res2 = await self._process_requestresponse(mw, req0, res0)
            assert "cached" not in res2.flags
            res3 = await mw.process_request(req0)
            assert "cached" in res3.flags
            self.assertEqualResponse(res2, res3)
            # request with no-cache directive must not return cached response
            # but it allows new response to be stored
            res0b = res0.replace(body=b"foo")
            res4 = await self._process_requestresponse(mw, req2, res0b)
            self.assertEqualResponse(res4, res0b)
            assert "cached" not in res4.flags
            res5 = await self._process_requestresponse(mw, req0, None)
            self.assertEqualResponse(res5, res0b)
            assert "cached" in res5.flags

    @coroutine_test
    async def test_response_cacheability(self):
        responses = [
            # 304 is not cacheable no matter what servers sends
            (False, 304, {}),
            (False, 304, {"Last-Modified": self.yesterday}),
            (False, 304, {"Expires": self.tomorrow}),
            (False, 304, {"Etag": "bar"}),
            (False, 304, {"Cache-Control": "max-age=3600"}),
            # Always obey no-store cache control
            (False, 200, {"Cache-Control": "no-store"}),
            (False, 200, {"Cache-Control": "no-store, max-age=300"}),  # invalid
            (
                False,
                200,
                {"Cache-Control": "no-store", "Expires": self.tomorrow},
            ),  # invalid
            # Ignore responses missing expiration and/or validation headers
            (False, 200, {}),
            (False, 302, {}),
            (False, 307, {}),
            (False, 404, {}),
            # Cache responses with expiration and/or validation headers
            (True, 200, {"Last-Modified": self.yesterday}),
            (True, 203, {"Last-Modified": self.yesterday}),
            (True, 300, {"Last-Modified": self.yesterday}),
            (True, 301, {"Last-Modified": self.yesterday}),
            (True, 308, {"Last-Modified": self.yesterday}),
            (True, 401, {"Last-Modified": self.yesterday}),
            (True, 404, {"Cache-Control": "public, max-age=600"}),
            (True, 302, {"Expires": self.tomorrow}),
            (True, 200, {"Etag": "foo"}),
        ]
        async with self._middleware() as mw:
            for idx, (shouldcache, status, headers) in enumerate(responses):
                req0 = Request(f"http://example-{idx}.com")
                res0 = Response(req0.url, status=status, headers=headers)
                res1 = await self._process_requestresponse(mw, req0, res0)
                res304 = res0.replace(status=304)
                res2 = await self._process_requestresponse(
                    mw, req0, res304 if shouldcache else res0
                )
                self.assertEqualResponse(res1, res0)
                self.assertEqualResponse(res2, res0)
                resc = await ensure_awaitable(
                    mw.storage.retrieve_response(mw.crawler.spider, req0)
                )
                if shouldcache:
                    self.assertEqualResponse(resc, res1)
                    assert "cached" in res2.flags
                    assert res2.status != 304
                else:
                    assert not resc
                    assert "cached" not in res2.flags

        # cache unconditionally unless response contains no-store or is a 304
        async with self._middleware(HTTPCACHE_ALWAYS_STORE=True) as mw:
            for idx, (_, status, headers) in enumerate(responses):
                shouldcache = (
                    "no-store" not in headers.get("Cache-Control", "") and status != 304
                )
                req0 = Request(f"http://example2-{idx}.com")
                res0 = Response(req0.url, status=status, headers=headers)
                res1 = await self._process_requestresponse(mw, req0, res0)
                res304 = res0.replace(status=304)
                res2 = await self._process_requestresponse(
                    mw, req0, res304 if shouldcache else res0
                )
                self.assertEqualResponse(res1, res0)
                self.assertEqualResponse(res2, res0)
                resc = mw.storage.retrieve_response(mw.crawler.spider, req0)
                if shouldcache:
                    self.assertEqualResponse(resc, res1)
                    assert "cached" in res2.flags
                    assert res2.status != 304
                else:
                    assert not resc
                    assert "cached" not in res2.flags

    @coroutine_test
    async def test_cached_and_fresh(self):
        sampledata = [
            (200, {"Date": self.yesterday, "Expires": self.tomorrow}),
            (200, {"Date": self.yesterday, "Cache-Control": "max-age=86405"}),
            (200, {"Age": "299", "Cache-Control": "max-age=300"}),
            # Obey max-age if present over any others
            (
                200,
                {
                    "Date": self.today,
                    "Age": "86405",
                    "Cache-Control": "max-age=" + str(86400 * 3),
                    "Expires": self.yesterday,
                    "Last-Modified": self.yesterday,
                },
            ),
            # obey Expires if max-age is not present
            (
                200,
                {
                    "Date": self.yesterday,
                    "Age": "86400",
                    "Cache-Control": "public",
                    "Expires": self.tomorrow,
                    "Last-Modified": self.yesterday,
                },
            ),
            # Default missing Date header to right now
            (200, {"Expires": self.tomorrow}),
            # Firefox - Expires if age is greater than 10% of (Date - Last-Modified)
            (
                200,
                {
                    "Date": self.today,
                    "Last-Modified": self.yesterday,
                    "Age": str(86400 / 10 - 1),
                },
            ),
            # Firefox - Set one year maxage to permanent redirects missing expiration info
            (300, {}),
            (301, {}),
            (308, {}),
        ]
        async with self._middleware() as mw:
            for idx, (status, headers) in enumerate(sampledata):
                req0 = Request(f"http://example-{idx}.com")
                res0 = Response(req0.url, status=status, headers=headers)
                # cache fresh response
                res1 = await self._process_requestresponse(mw, req0, res0)
                self.assertEqualResponse(res1, res0)
                assert "cached" not in res1.flags
                # return fresh cached response without network interaction
                res2 = await self._process_requestresponse(mw, req0, None)
                self.assertEqualResponse(res1, res2)
                assert "cached" in res2.flags
                # validate cached response if request max-age set as 0
                req1 = req0.replace(headers={"Cache-Control": "max-age=0"})
                res304 = res0.replace(status=304)
                assert await mw.process_request(req1) is None
                res3 = await self._process_requestresponse(mw, req1, res304)
                self.assertEqualResponse(res1, res3)
                assert "cached" in res3.flags

    @coroutine_test
    async def test_cached_and_stale(self):
        sampledata = [
            (200, {"Date": self.today, "Expires": self.yesterday}),
            (
                200,
                {
                    "Date": self.today,
                    "Expires": self.yesterday,
                    "Last-Modified": self.yesterday,
                },
            ),
            (200, {"Expires": self.yesterday}),
            (200, {"Expires": self.yesterday, "ETag": "foo"}),
            (200, {"Expires": self.yesterday, "Last-Modified": self.yesterday}),
            (200, {"Expires": self.tomorrow, "Age": "86405"}),
            (200, {"Cache-Control": "max-age=86400", "Age": "86405"}),
            # no-cache forces expiration, also revalidation if validators exists
            (200, {"Cache-Control": "no-cache"}),
            (200, {"Cache-Control": "no-cache", "ETag": "foo"}),
            (200, {"Cache-Control": "no-cache", "Last-Modified": self.yesterday}),
            (
                200,
                {
                    "Cache-Control": "no-cache,must-revalidate",
                    "Last-Modified": self.yesterday,
                },
            ),
            (
                200,
                {
                    "Cache-Control": "must-revalidate",
                    "Expires": self.yesterday,
                    "Last-Modified": self.yesterday,
                },
            ),
            (200, {"Cache-Control": "max-age=86400,must-revalidate", "Age": "86405"}),
        ]
        async with self._middleware() as mw:
            for idx, (status, headers) in enumerate(sampledata):
                req0 = Request(f"http://example-{idx}.com")
                res0a = Response(req0.url, status=status, headers=headers)
                # cache expired response
                res1 = await self._process_requestresponse(mw, req0, res0a)
                self.assertEqualResponse(res1, res0a)
                assert "cached" not in res1.flags
                # Same request but as cached response is stale a new response must
                # be returned
                res0b = res0a.replace(body=b"bar")
                res2 = await self._process_requestresponse(mw, req0, res0b)
                self.assertEqualResponse(res2, res0b)
                assert "cached" not in res2.flags
                cc = headers.get("Cache-Control", "")
                # Previous response expired too, subsequent request to same
                # resource must revalidate and succeed on 304 if validators
                # are present
                if "ETag" in headers or "Last-Modified" in headers:
                    res0c = res0b.replace(status=304)
                    res3 = await self._process_requestresponse(mw, req0, res0c)
                    self.assertEqualResponse(res3, res0b)
                    assert "cached" in res3.flags
                    # get cached response on server errors unless must-revalidate
                    # in cached response
                    res0d = res0b.replace(status=500)
                    res4 = await self._process_requestresponse(mw, req0, res0d)
                    if "must-revalidate" in cc:
                        assert "cached" not in res4.flags
                        self.assertEqualResponse(res4, res0d)
                    else:
                        assert "cached" in res4.flags
                        self.assertEqualResponse(res4, res0b)
                # Requests with max-stale can fetch expired cached responses
                # unless cached response has must-revalidate
                req1 = req0.replace(headers={"Cache-Control": "max-stale"})
                res5 = await self._process_requestresponse(mw, req1, res0b)
                self.assertEqualResponse(res5, res0b)
                if "no-cache" in cc or "must-revalidate" in cc:
                    assert "cached" not in res5.flags
                else:
                    assert "cached" in res5.flags

    @coroutine_test
    async def test_process_exception(self):
        async with self._middleware() as mw:
            res0 = Response(self.request.url, headers={"Expires": self.yesterday})
            req0 = Request(self.request.url)
            await self._process_requestresponse(mw, req0, res0)
            for e in mw.DOWNLOAD_EXCEPTIONS:
                # Simulate encountering an error on download attempts
                assert await mw.process_request(req0) is None
                res1 = mw.process_exception(req0, e("foo"))
                # Use cached response as recovery
                assert "cached" in res1.flags
                self.assertEqualResponse(res0, res1)
            # Do not use cached response for unhandled exceptions
            await mw.process_request(req0)
            assert mw.process_exception(req0, Exception("foo")) is None

    @coroutine_test
    async def test_ignore_response_cache_controls(self):
        sampledata = [
            (200, {"Date": self.yesterday, "Expires": self.tomorrow}),
            (200, {"Date": self.yesterday, "Cache-Control": "no-store,max-age=86405"}),
            (200, {"Age": "299", "Cache-Control": "max-age=300,no-cache"}),
            (300, {"Cache-Control": "no-cache"}),
            (200, {"Expires": self.tomorrow, "Cache-Control": "no-store"}),
        ]
        async with self._middleware(
            HTTPCACHE_IGNORE_RESPONSE_CACHE_CONTROLS=["no-cache", "no-store"]
        ) as mw:
            for idx, (status, headers) in enumerate(sampledata):
                req0 = Request(f"http://example-{idx}.com")
                res0 = Response(req0.url, status=status, headers=headers)
                # cache fresh response
                res1 = await self._process_requestresponse(mw, req0, res0)
                self.assertEqualResponse(res1, res0)
                assert "cached" not in res1.flags
                # return fresh cached response without network interaction
                res2 = await self._process_requestresponse(mw, req0, None)
                self.assertEqualResponse(res1, res2)
                assert "cached" in res2.flags


class AsyncDummyCacheStorage(FilesystemCacheStorage):
    """A simple async storage that wraps FilesystemCacheStorage for testing."""

    async def open_spider(self, spider):
        await async_sleep(0.01)
        super().open_spider(spider)

    async def close_spider(self, spider):
        await async_sleep(0.01)
        super().close_spider(spider)

    async def retrieve_response(self, spider, request):
        await async_sleep(0.01)
        return super().retrieve_response(spider, request)

    async def store_response(self, spider, request, response):
        await async_sleep(0.01)
        super().store_response(spider, request, response)


# Concrete test classes that combine storage and policy mixins


class TestFilesystemStorageWithDummyPolicy(
    TestBase, StorageTestMixin, DummyPolicyTestMixin
):
    storage_class = "scrapy.extensions.httpcache.FilesystemCacheStorage"
    policy_class = "scrapy.extensions.httpcache.DummyPolicy"


class TestFilesystemStorageWithRFC2616Policy(
    TestBase, StorageTestMixin, RFC2616PolicyTestMixin
):
    storage_class = "scrapy.extensions.httpcache.FilesystemCacheStorage"
    policy_class = "scrapy.extensions.httpcache.RFC2616Policy"


class TestDbmStorageWithDummyPolicy(TestBase, StorageTestMixin, DummyPolicyTestMixin):
    storage_class = "scrapy.extensions.httpcache.DbmCacheStorage"
    policy_class = "scrapy.extensions.httpcache.DummyPolicy"


class TestDbmStorageWithRFC2616Policy(
    TestBase, StorageTestMixin, RFC2616PolicyTestMixin
):
    storage_class = "scrapy.extensions.httpcache.DbmCacheStorage"
    policy_class = "scrapy.extensions.httpcache.RFC2616Policy"


class TestDbmStorageWithCustomDbmModule(TestDbmStorageWithDummyPolicy):
    dbm_module = "tests.mocks.dummydbm"

    def _get_settings(self, **new_settings) -> dict[str, Any]:
        new_settings.setdefault("HTTPCACHE_DBM_MODULE", self.dbm_module)
        return super()._get_settings(**new_settings)

    @coroutine_test
    async def test_custom_dbm_module_loaded(self):
        # make sure our dbm module has been loaded
        async with self._storage() as (storage, _):
            assert storage.dbmodule.__name__ == self.dbm_module


class TestFilesystemStorageGzipWithDummyPolicy(TestFilesystemStorageWithDummyPolicy):
    def _get_settings(self, **new_settings) -> dict[str, Any]:
        new_settings.setdefault("HTTPCACHE_GZIP", True)
        return super()._get_settings(**new_settings)


class TestAsyncStorageWithDummyPolicy(TestBase, StorageTestMixin, DummyPolicyTestMixin):
    storage_class = f"{__name__}.AsyncDummyCacheStorage"
    policy_class = "scrapy.extensions.httpcache.DummyPolicy"
