from __future__ import annotations

from unittest.mock import Mock, call

import pytest
from twisted.internet import defer

from scrapy.core.engine import ExecutionEngine
from scrapy.http import Request, Response
from scrapy.utils.defer import maybe_deferred_to_future
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler
from tests.utils.decorators import coroutine_test


class TestEngineDownloadAsync:
    """Test cases for ExecutionEngine.download_async()."""

    @pytest.fixture
    def engine(self) -> ExecutionEngine:
        # crawler = get_crawler(MySpider)
        crawler = get_crawler(DefaultSpider)
        engine = ExecutionEngine(crawler, lambda _: None)
        engine.downloader.close()
        engine.downloader = Mock()
        engine._slot = Mock()
        engine._slot.inprogress = set()
        return engine

    @staticmethod
    async def _download(engine: ExecutionEngine, request: Request) -> Response:
        return await engine.download_async(request)

    @coroutine_test
    async def test_download_async_success(self, engine):
        """Test basic successful async download of a request."""
        request = Request("http://example.com")
        response = Response("http://example.com", body=b"test body")
        engine.spider = Mock()
        engine.downloader.fetch.return_value = defer.succeed(response)
        engine._slot.add_request = Mock()
        engine._slot.remove_request = Mock()

        result = await self._download(engine, request)
        assert result == response
        engine._slot.add_request.assert_called_once_with(request)
        engine._slot.remove_request.assert_called_once_with(request)
        engine.downloader.fetch.assert_called_once_with(request)

    @coroutine_test
    async def test_download_async_redirect(self, engine):
        """Test async download with a redirect request."""
        original_request = Request("http://example.com")
        redirect_request = Request("http://example.com/redirect")
        final_response = Response("http://example.com/redirect", body=b"redirected")

        # First call returns redirect request, second call returns final response
        engine.downloader.fetch.side_effect = [
            defer.succeed(redirect_request),
            defer.succeed(final_response),
        ]
        engine.spider = Mock()
        engine._slot.add_request = Mock()
        engine._slot.remove_request = Mock()

        result = await self._download(engine, original_request)
        assert result == final_response
        assert engine.downloader.fetch.call_count == 2
        engine._slot.add_request.assert_has_calls(
            [call(original_request), call(redirect_request)]
        )
        engine._slot.remove_request.assert_has_calls(
            [call(original_request), call(redirect_request)]
        )

    @coroutine_test
    async def test_download_async_no_spider(self, engine):
        """Test async download attempt when no spider is available."""
        request = Request("http://example.com")
        engine.spider = None
        with pytest.raises(RuntimeError, match="No open spider to crawl:"):
            await self._download(engine, request)

    @coroutine_test
    async def test_download_async_failure(self, engine):
        """Test async download when the downloader raises an exception."""
        request = Request("http://example.com")
        error = RuntimeError("Download failed")
        engine.spider = Mock()
        engine.downloader.fetch.return_value = defer.fail(error)
        engine._slot.add_request = Mock()
        engine._slot.remove_request = Mock()

        with pytest.raises(RuntimeError, match="Download failed"):
            await self._download(engine, request)
        engine._slot.add_request.assert_called_once_with(request)
        engine._slot.remove_request.assert_called_once_with(request)


@pytest.mark.filterwarnings("ignore::scrapy.exceptions.ScrapyDeprecationWarning")
class TestEngineDownload(TestEngineDownloadAsync):
    """Test cases for ExecutionEngine.download()."""

    @staticmethod
    async def _download(engine: ExecutionEngine, request: Request) -> Response:
        return await maybe_deferred_to_future(engine.download(request))
