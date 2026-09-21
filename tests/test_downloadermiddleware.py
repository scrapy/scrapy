from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from gzip import compress
from typing import TYPE_CHECKING, Any
from unittest import mock

import pytest
from twisted.internet.defer import Deferred, succeed

from scrapy.core.downloader.middleware import DownloaderMiddlewareManager
from scrapy.exceptions import (
    CloseSpider,
    DecompressionError,
    IgnoreRequest,
    ScrapyDeprecationWarning,
    _InvalidOutput,
)
from scrapy.http import Request, Response
from scrapy.spiders import Spider
from scrapy.utils.defer import maybe_deferred_to_future
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.python import to_bytes
from scrapy.utils.test import get_crawler, get_from_asyncio_queue
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


def _invalid_gzipped_response(request: Request) -> Response:
    body = b"<p>You are being redirected</p>"
    return Response(
        request.url,
        status=200,
        body=body,
        headers={
            "Content-Length": str(len(body)),
            "Content-Type": "text/html",
            "Content-Encoding": "gzip",
            "Location": "http://example.com/login",
        },
    )


def _truncated_gzipped_response(request: Request) -> Response:
    body = compress(b"<p>You are being redirected</p>")[:10]
    return Response(
        request.url,
        status=200,
        body=body,
        headers={
            "Content-Length": str(len(body)),
            "Content-Type": "text/html",
            "Content-Encoding": "gzip",
        },
    )


class TestManagerBase:
    settings_dict: dict[str, Any] | None = None

    # should be a fixture but async fixtures that use Futures are problematic with pytest-twisted
    @asynccontextmanager
    async def get_mwman(self) -> AsyncGenerator[DownloaderMiddlewareManager]:
        crawler = get_crawler(Spider, self.settings_dict)
        crawler.spider = crawler._create_spider("foo")
        mwman = build_from_crawler(DownloaderMiddlewareManager, crawler)
        crawler.engine = crawler._create_engine()
        await crawler.engine.open_spider_async()
        try:
            yield mwman
        finally:
            await crawler.engine.close_spider_async()

    @staticmethod
    async def _download(
        mwman: DownloaderMiddlewareManager,
        request: Request,
        response: Response | None = None,
    ) -> Response | Request:
        """Executes downloader mw manager's download method and returns
        the result (Request or Response) or raises exception in case of
        failure.
        """
        if not response:
            response = Response(request.url)

        async def download_func(request: Request) -> Response:
            return response

        return await mwman.download_async(download_func, request)


class TestDefaults(TestManagerBase):
    """Tests default behavior with default settings"""

    @coroutine_test
    async def test_request_response(self):
        req = Request("http://example.com/index.html")
        resp = Response(req.url, status=200)
        async with self.get_mwman() as mwman:
            ret = await self._download(mwman, req, resp)
        assert isinstance(ret, Response), "Non-response returned"

    @coroutine_test
    async def test_none_from_download_func(self):
        async def download_func(request: Request) -> None:
            return None

        async with self.get_mwman() as mwman:
            with pytest.raises(TypeError, match="Received None in process_response"):
                await mwman.download_async(
                    download_func,  # type: ignore[arg-type]
                    Request("http://example.com/index.html"),
                )

    @coroutine_test
    async def test_3xx_and_invalid_gzipped_body_fails(self):
        # Without DOWNLOADER_MIDDLEWARE_RESPONSE_EXCEPTIONS,
        # RedirectMiddleware.process_exception() is never consulted, even
        # though the response has a usable Location header.
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
        with pytest.raises(DecompressionError):
            async with self.get_mwman() as mwman:
                await self._download(mwman, req, resp)

    @coroutine_test
    async def test_200_and_invalid_gzipped_body_must_fail(self):
        req = Request("http://example.com")
        resp = _invalid_gzipped_response(req)
        with pytest.raises(DecompressionError):
            async with self.get_mwman() as mwman:
                await self._download(mwman, req, resp)


class TestResponseFromProcessRequest(TestManagerBase):
    """Tests middleware returning a response from process_request."""

    @coroutine_test
    async def test_download_func_not_called(self):
        req = Request("http://example.com/index.html")
        resp = Response("http://example.com/index.html")
        download_func = mock.MagicMock()

        class ResponseMiddleware:
            def process_request(self, request):
                return resp

        async with self.get_mwman() as mwman:
            mwman._add_middleware(ResponseMiddleware())
            result = await mwman.download_async(download_func, req)
        assert result is resp
        assert not download_func.called


class TestResponseFromProcessException(TestManagerBase):
    """Tests middleware returning a response from process_exception."""

    @coroutine_test
    async def test_process_response_called(self):
        req = Request("http://example.com/index.html")
        resp = Response("http://example.com/index.html")
        calls = []

        def download_func(request):
            raise ValueError("test")

        class ResponseMiddleware:
            def process_response(self, request, response):
                calls.append("process_response")
                return resp

            def process_exception(self, request, exception):
                calls.append("process_exception")
                return resp

        async with self.get_mwman() as mwman:
            mwman._add_middleware(ResponseMiddleware())
            result = await mwman.download_async(download_func, req)
        assert result is resp
        assert calls == [
            "process_exception",
            "process_response",
        ]


class TestResponseExceptions(TestManagerBase):
    """Tests exceptions from process_response reaching process_exception."""

    settings_dict = {"DOWNLOADER_MIDDLEWARE_RESPONSE_EXCEPTIONS": True}

    @coroutine_test
    async def test_request_from_process_exception(self):
        req = Request("http://example.com/index.html")
        retry_req = Request("http://example.com/index.html")
        calls = []

        class OuterMiddleware:
            def process_response(self, request, response):
                calls.append("outer.process_response")
                return response

            def process_exception(self, request, exception):
                calls.append("outer.process_exception")
                return retry_req

        class InnerMiddleware:
            def process_response(self, request, response):
                calls.append("inner.process_response")
                raise ValueError("test")

            def process_exception(self, request, exception):
                calls.append("inner.process_exception")

        async with self.get_mwman() as mwman:
            mwman._add_middleware(OuterMiddleware())
            mwman._add_middleware(InnerMiddleware())
            result = await self._download(mwman, req)
        assert result is retry_req
        assert calls == ["inner.process_response", "outer.process_exception"]

    @coroutine_test
    async def test_response_from_process_exception(self):
        req = Request("http://example.com/index.html")
        recovered = Response("http://example.com/index.html")
        calls = []

        class OuterMiddleware:
            def process_response(self, request, response):
                calls.append("outer.process_response")
                return response

        class MiddleMiddleware:
            def process_response(self, request, response):
                calls.append("middle.process_response")
                return response

            def process_exception(self, request, exception):
                calls.append("middle.process_exception")
                return recovered

        class InnerMiddleware:
            def process_response(self, request, response):
                calls.append("inner.process_response")
                raise ValueError("test")

        async with self.get_mwman() as mwman:
            mwman._add_middleware(OuterMiddleware())
            mwman._add_middleware(MiddleMiddleware())
            mwman._add_middleware(InnerMiddleware())
            result = await self._download(mwman, req)
        assert result is recovered
        assert calls == [
            "inner.process_response",
            "middle.process_exception",
            "outer.process_response",
        ]

    @coroutine_test
    async def test_processed_middleware_not_called(self):
        req = Request("http://example.com/index.html")
        calls = []

        class RaisingMiddleware:
            def process_response(self, request, response):
                calls.append("raising.process_response")
                raise ValueError("test")

        class InnerMiddleware:
            def process_response(self, request, response):
                calls.append("inner.process_response")
                return response

            def process_exception(self, request, exception):
                calls.append("inner.process_exception")

        async with self.get_mwman() as mwman:
            mwman._add_middleware(RaisingMiddleware())
            mwman._add_middleware(InnerMiddleware())
            with pytest.raises(ValueError, match="test"):
                await self._download(mwman, req)
        assert calls == ["inner.process_response", "raising.process_response"]

    @coroutine_test
    async def test_unhandled(self):
        req = Request("http://example.com/index.html")

        class RaisingMiddleware:
            def process_response(self, request, response):
                raise ValueError("test")

        async with self.get_mwman() as mwman:
            mwman._add_middleware(RaisingMiddleware())
            with pytest.raises(ValueError, match="test"):
                await self._download(mwman, req)

    @pytest.mark.parametrize(
        "response_func", [_invalid_gzipped_response, _truncated_gzipped_response]
    )
    @coroutine_test
    async def test_retry(self, response_func):
        """Decompression failures are retried, as RETRY_EXCEPTIONS promises."""
        req = Request("http://example.com")
        async with self.get_mwman() as mwman:
            result = await self._download(mwman, req, response_func(req))
        assert isinstance(result, Request)
        assert result.url == req.url

    @coroutine_test
    async def test_3xx_and_invalid_gzipped_body_must_redirect(self):
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
        async with self.get_mwman() as mwman:
            ret = await self._download(mwman, req, resp)
        assert isinstance(ret, Request), f"Not redirected: {ret!r}"
        assert to_bytes(ret.url) == resp.headers["Location"], (
            "Not redirected to location header"
        )

    @coroutine_test
    async def test_close_spider(self):
        req = Request("http://example.com/index.html")
        calls = []

        class OuterMiddleware:
            def process_exception(self, request, exception):
                calls.append("outer.process_exception")

        class InnerMiddleware:
            def process_response(self, request, response):
                raise CloseSpider("test")

        async with self.get_mwman() as mwman:
            mwman._add_middleware(OuterMiddleware())
            mwman._add_middleware(InnerMiddleware())
            with pytest.raises(CloseSpider):
                await self._download(mwman, req)
        assert not calls

    @coroutine_test
    async def test_close_spider_from_process_request(self):
        req = Request("http://example.com/index.html")
        calls = []

        class Middleware:
            def process_request(self, request):
                raise CloseSpider("test")

            def process_exception(self, request, exception):
                calls.append("process_exception")

        async with self.get_mwman() as mwman:
            mwman._add_middleware(Middleware())
            with pytest.raises(CloseSpider):
                await self._download(mwman, req)
        assert not calls


class TestResponseExceptionsDisabled(TestManagerBase):
    """Tests the deprecated behavior, which the default value still gives."""

    @pytest.mark.parametrize("exception", [ValueError, IgnoreRequest])
    @coroutine_test
    async def test_not_passed_to_process_exception(self, exception):
        req = Request("http://example.com/index.html")
        calls = []

        class OuterMiddleware:
            def process_exception(self, request, exception):
                calls.append("outer.process_exception")

        class InnerMiddleware:
            def process_response(self, request, response):
                raise exception("test")

        async with self.get_mwman() as mwman:
            mwman._add_middleware(OuterMiddleware())
            mwman._add_middleware(InnerMiddleware())
            with (
                pytest.raises(exception, match="test"),
                pytest.warns(
                    ScrapyDeprecationWarning,
                    match="OuterMiddleware.process_exception",
                ),
            ):
                await self._download(mwman, req)
        assert not calls

    @coroutine_test
    async def test_only_built_in_process_exception(self):
        """Nothing is warned about when only Scrapy's own process_exception()
        methods would get the exception."""
        req = Request("http://example.com/index.html")

        class RaisingMiddleware:
            def process_response(self, request, response):
                raise ValueError("test")

        async with self.get_mwman() as mwman:
            mwman._add_middleware(RaisingMiddleware())
            with pytest.raises(ValueError, match="test"):
                await self._download(mwman, req)


class TestResponseExceptionsDisabledExplicitly(TestResponseExceptionsDisabled):
    """Asking for the deprecated behavior does not silence the warning."""

    settings_dict = {"DOWNLOADER_MIDDLEWARE_RESPONSE_EXCEPTIONS": False}


class TestInvalidOutput(TestManagerBase):
    @coroutine_test
    async def test_invalid_process_request(self):
        """Invalid return value for process_request method should raise an exception"""
        req = Request("http://example.com/index.html")

        class InvalidProcessRequestMiddleware:
            def process_request(self, request):
                return 1

        async with self.get_mwman() as mwman:
            mwman._add_middleware(InvalidProcessRequestMiddleware())
            with pytest.raises(_InvalidOutput):
                await self._download(mwman, req)

    @coroutine_test
    async def test_invalid_process_response(self):
        """Invalid return value for process_response method should raise an exception"""
        req = Request("http://example.com/index.html")

        class InvalidProcessResponseMiddleware:
            def process_response(self, request, response):
                return 1

        async with self.get_mwman() as mwman:
            mwman._add_middleware(InvalidProcessResponseMiddleware())
            with pytest.raises(_InvalidOutput):
                await self._download(mwman, req)

    @coroutine_test
    async def test_invalid_process_exception(self):
        """Invalid return value for process_exception method should raise an exception"""
        req = Request("http://example.com/index.html")

        class InvalidProcessExceptionMiddleware:
            def process_request(self, request):
                raise RuntimeError

            def process_exception(self, request, exception):
                return 1

        async with self.get_mwman() as mwman:
            mwman._add_middleware(InvalidProcessExceptionMiddleware())
            with pytest.raises(_InvalidOutput):
                await self._download(mwman, req)


class TestMiddlewareUsingDeferreds(TestManagerBase):
    """Middlewares using Deferreds (deprecated) should work"""

    @coroutine_test
    async def test_deferred(self):
        req = Request("http://example.com/index.html")
        resp = Response("http://example.com/index.html")
        download_func = mock.MagicMock()

        class DeferredMiddleware:
            def cb(self, result):
                return result

            def process_request(self, request):
                d: Deferred[Response] = Deferred()
                d.addCallback(self.cb)
                d.callback(resp)
                return d

        async with self.get_mwman() as mwman:
            mwman._add_middleware(DeferredMiddleware())
            with pytest.warns(
                ScrapyDeprecationWarning,
                match="returned a Deferred, this is deprecated",
            ):
                result = await mwman.download_async(download_func, req)
        assert result is resp
        assert not download_func.called


class TestMiddlewareUsingCoro(TestManagerBase):
    """Middlewares using asyncio coroutines should work"""

    @coroutine_test
    async def test_asyncdef(self):
        req = Request("http://example.com/index.html")
        resp = Response("http://example.com/index.html")
        download_func = mock.MagicMock()

        class CoroMiddleware:
            async def process_request(self, request):
                await succeed(42)
                return resp

        async with self.get_mwman() as mwman:
            mwman._add_middleware(CoroMiddleware())
            result = await mwman.download_async(download_func, req)
        assert result is resp
        assert not download_func.called

    @pytest.mark.only_asyncio
    @coroutine_test
    async def test_asyncdef_asyncio(self):
        req = Request("http://example.com/index.html")
        resp = Response("http://example.com/index.html")
        download_func = mock.MagicMock()

        class CoroMiddleware:
            async def process_request(self, request):
                await asyncio.sleep(0.1)
                return await get_from_asyncio_queue(resp)

        async with self.get_mwman() as mwman:
            mwman._add_middleware(CoroMiddleware())
            result = await mwman.download_async(download_func, req)
        assert result is resp
        assert not download_func.called


class TestDownloadDeprecated(TestManagerBase):
    @coroutine_test
    async def test_mwman_download(self):
        req = Request("http://example.com/index.html")
        resp = Response(req.url, status=200)

        def download_func(request: Request, spider: Spider) -> Deferred[Response]:
            return succeed(resp)

        async with self.get_mwman() as mwman:
            assert mwman.crawler
            assert mwman.crawler.spider
            with pytest.warns(
                ScrapyDeprecationWarning,
                match=r"DownloaderMiddlewareManager.download\(\) is deprecated, use download_async\(\) instead",
            ):
                ret = await maybe_deferred_to_future(
                    mwman.download(download_func, req, mwman.crawler.spider)
                )
        assert isinstance(ret, Response)


class TestDeprecatedSpiderArg(TestManagerBase):
    @coroutine_test
    async def test_deprecated_spider_arg(self):
        req = Request("http://example.com/index.html")
        resp = Response("http://example.com/index.html")
        download_func = mock.MagicMock()

        class DeprecatedSpiderArgMiddleware:
            def process_request(self, request, spider):
                1 / 0

            def process_response(self, request, response, spider):
                return response

            def process_exception(self, request, exception, spider):
                return resp

        async with self.get_mwman() as mwman:
            with (
                pytest.warns(
                    ScrapyDeprecationWarning,
                    match=r"process_request\(\) requires a spider argument",
                ),
                pytest.warns(
                    ScrapyDeprecationWarning,
                    match=r"process_response\(\) requires a spider argument",
                ),
                pytest.warns(
                    ScrapyDeprecationWarning,
                    match=r"process_exception\(\) requires a spider argument",
                ),
            ):
                mwman._add_middleware(DeprecatedSpiderArgMiddleware())
            result = await mwman.download_async(download_func, req)
        assert result is resp
        assert not download_func.called
