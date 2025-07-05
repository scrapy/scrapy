from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from gzip import BadGzipFile
from unittest import mock

import pytest
from twisted.internet.defer import Deferred, succeed

from scrapy.core.downloader.middleware import DownloaderMiddlewareManager
from scrapy.exceptions import _InvalidOutput
from scrapy.http import Request, Response
from scrapy.spiders import Spider
from scrapy.utils.defer import deferred_f_from_coro_f, maybe_deferred_to_future
from scrapy.utils.python import to_bytes
from scrapy.utils.test import get_crawler, get_from_asyncio_queue


class TestManagerBase:
    settings_dict = None

    # should be a fixture but async fixtures that use Futures are problematic with pytest-twisted
    @asynccontextmanager
    async def get_mwman_and_spider(self):
        crawler = get_crawler(Spider, self.settings_dict)
        spider = crawler._create_spider("foo")
        mwman = DownloaderMiddlewareManager.from_crawler(crawler)
        crawler.engine = crawler._create_engine()
        await crawler.engine.open_spider_async(spider)
        yield mwman, spider
        await maybe_deferred_to_future(crawler.engine.close_spider(spider))

    @staticmethod
    async def _download(
        mwman: DownloaderMiddlewareManager,
        spider: Spider,
        request: Request,
        response: Response | None = None,
    ) -> Response | Request:
        """Executes downloader mw manager's download method and returns
        the result (Request or Response) or raises exception in case of
        failure.
        """
        if not response:
            response = Response(request.url)

        def download_func(request: Request, spider: Spider) -> Deferred[Response]:
            return succeed(response)

        return await maybe_deferred_to_future(
            mwman.download(download_func, request, spider)
        )


class TestDefaults(TestManagerBase):
    """Tests default behavior with default settings"""

    @deferred_f_from_coro_f
    async def test_request_response(self):
        req = Request("http://example.com/index.html")
        resp = Response(req.url, status=200)
        async with self.get_mwman_and_spider() as (mwman, spider):
            ret = await self._download(mwman, spider, req, resp)
        assert isinstance(ret, Response), "Non-response returned"

    @deferred_f_from_coro_f
    async def test_3xx_and_invalid_gzipped_body_must_redirect(self):
        """Regression test for a failure when redirecting a compressed
        request.

        This happens when httpcompression middleware is executed before redirect
        middleware and attempts to decompress a non-compressed body.
        In particular when some website returns a 30x response with header
        'Content-Encoding: gzip' giving as result the error below:

            BadGzipFile: Not a gzipped file (...)

        """
        req = Request("http://example.com")
        body = b"<p>You are being redirected</p>"
        resp = Response(
            req.url,
            status=302,
            body=body,
            headers={
                "Content-Length": str(len(body)),
                "Content-Type": "text/html",
                "Content-Encoding": "gzip",
                "Location": "http://example.com/login",
            },
        )
        async with self.get_mwman_and_spider() as (mwman, spider):
            ret = await self._download(mwman, spider, req, resp)
        assert isinstance(ret, Request), f"Not redirected: {ret!r}"
        assert to_bytes(ret.url) == resp.headers["Location"], (
            "Not redirected to location header"
        )

    @deferred_f_from_coro_f
    async def test_200_and_invalid_gzipped_body_must_fail(self):
        req = Request("http://example.com")
        body = b"<p>You are being redirected</p>"
        resp = Response(
            req.url,
            status=200,
            body=body,
            headers={
                "Content-Length": str(len(body)),
                "Content-Type": "text/html",
                "Content-Encoding": "gzip",
                "Location": "http://example.com/login",
            },
        )
        with pytest.raises(BadGzipFile):
            async with self.get_mwman_and_spider() as (mwman, spider):
                await self._download(mwman, spider, req, resp)


class TestResponseFromProcessRequest(TestManagerBase):
    """Tests middleware returning a response from process_request."""

    @deferred_f_from_coro_f
    async def test_download_func_not_called(self):
        req = Request("http://example.com/index.html")
        resp = Response("http://example.com/index.html")
        download_func = mock.MagicMock()

        class ResponseMiddleware:
            def process_request(self, request, spider):
                return resp

        async with self.get_mwman_and_spider() as (mwman, spider):
            mwman._add_middleware(ResponseMiddleware())
            result = await maybe_deferred_to_future(
                mwman.download(download_func, req, spider)
            )
        assert result is resp
        assert not download_func.called


class TestResponseFromProcessException(TestManagerBase):
    """Tests middleware returning a response from process_exception."""

    @deferred_f_from_coro_f
    async def test_process_response_called(self):
        req = Request("http://example.com/index.html")
        resp = Response("http://example.com/index.html")
        calls = []

        def download_func(request, spider):
            raise ValueError("test")

        class ResponseMiddleware:
            def process_response(self, request, response, spider):
                calls.append("process_response")
                return resp

            def process_exception(self, request, exception, spider):
                calls.append("process_exception")
                return resp

        async with self.get_mwman_and_spider() as (mwman, spider):
            mwman._add_middleware(ResponseMiddleware())
            result = await maybe_deferred_to_future(
                mwman.download(download_func, req, spider)
            )
        assert result is resp
        assert calls == [
            "process_exception",
            "process_response",
        ]


class TestInvalidOutput(TestManagerBase):
    @deferred_f_from_coro_f
    async def test_invalid_process_request(self):
        """Invalid return value for process_request method should raise an exception"""
        req = Request("http://example.com/index.html")

        class InvalidProcessRequestMiddleware:
            def process_request(self, request, spider):
                return 1

        async with self.get_mwman_and_spider() as (mwman, spider):
            mwman._add_middleware(InvalidProcessRequestMiddleware())
            with pytest.raises(_InvalidOutput):
                await self._download(mwman, spider, req)

    @deferred_f_from_coro_f
    async def test_invalid_process_response(self):
        """Invalid return value for process_response method should raise an exception"""
        req = Request("http://example.com/index.html")

        class InvalidProcessResponseMiddleware:
            def process_response(self, request, response, spider):
                return 1

        async with self.get_mwman_and_spider() as (mwman, spider):
            mwman._add_middleware(InvalidProcessResponseMiddleware())
            with pytest.raises(_InvalidOutput):
                await self._download(mwman, spider, req)

    @deferred_f_from_coro_f
    async def test_invalid_process_exception(self):
        """Invalid return value for process_exception method should raise an exception"""
        req = Request("http://example.com/index.html")

        class InvalidProcessExceptionMiddleware:
            def process_request(self, request, spider):
                raise RuntimeError

            def process_exception(self, request, exception, spider):
                return 1

        async with self.get_mwman_and_spider() as (mwman, spider):
            mwman._add_middleware(InvalidProcessExceptionMiddleware())
            with pytest.raises(_InvalidOutput):
                await self._download(mwman, spider, req)


class TestMiddlewareUsingDeferreds(TestManagerBase):
    """Middlewares using Deferreds should work"""

    @deferred_f_from_coro_f
    async def test_deferred(self):
        req = Request("http://example.com/index.html")
        resp = Response("http://example.com/index.html")
        download_func = mock.MagicMock()

        class DeferredMiddleware:
            def cb(self, result):
                return result

            def process_request(self, request, spider):
                d = Deferred()
                d.addCallback(self.cb)
                d.callback(resp)
                return d

        async with self.get_mwman_and_spider() as (mwman, spider):
            mwman._add_middleware(DeferredMiddleware())
            result = await maybe_deferred_to_future(
                mwman.download(download_func, req, spider)
            )
        assert result is resp
        assert not download_func.called


class TestMiddlewareUsingCoro(TestManagerBase):
    """Middlewares using asyncio coroutines should work"""

    @deferred_f_from_coro_f
    async def test_asyncdef(self):
        req = Request("http://example.com/index.html")
        resp = Response("http://example.com/index.html")
        download_func = mock.MagicMock()

        class CoroMiddleware:
            async def process_request(self, request, spider):
                await succeed(42)
                return resp

        async with self.get_mwman_and_spider() as (mwman, spider):
            mwman._add_middleware(CoroMiddleware())
            result = await maybe_deferred_to_future(
                mwman.download(download_func, req, spider)
            )
        assert result is resp
        assert not download_func.called

    @pytest.mark.only_asyncio
    @deferred_f_from_coro_f
    async def test_asyncdef_asyncio(self):
        req = Request("http://example.com/index.html")
        resp = Response("http://example.com/index.html")
        download_func = mock.MagicMock()

        class CoroMiddleware:
            async def process_request(self, request, spider):
                await asyncio.sleep(0.1)
                return await get_from_asyncio_queue(resp)

        async with self.get_mwman_and_spider() as (mwman, spider):
            mwman._add_middleware(CoroMiddleware())
            result = await maybe_deferred_to_future(
                mwman.download(download_func, req, spider)
            )
        assert result is resp
        assert not download_func.called
