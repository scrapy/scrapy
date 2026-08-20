from __future__ import annotations

import json
from ipaddress import IPv4Address
from typing import TYPE_CHECKING, Any, TypeAlias

import pytest

from scrapy import Request, Spider, signals
from scrapy.core.downloader.handlers.websocket import WebSocketDownloadHandler
from scrapy.exceptions import DownloadFailedError, NotConfigured
from scrapy.http import WebSocketResponse
from scrapy.spidermiddlewares.httperror import HttpError
from scrapy.utils.defer import maybe_deferred_to_future
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.test import get_crawler
from tests.mockserver.websocket import WebSocketMockServer
from tests.spiders import SingleRequestSpider
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Generator

    from scrapy.crawler import Crawler

    _Callback: TypeAlias = Callable[[WebSocketResponse], AsyncIterator[Any]]


pytestmark = pytest.mark.only_asyncio


@pytest.fixture(scope="module")
def ws_server() -> Generator[WebSocketMockServer]:
    with WebSocketMockServer() as server:
        yield server


async def _crawl(
    url: str, callback: _Callback | None = None, **settings: Any
) -> tuple[list[Any], Crawler]:
    """Crawl *url* with *callback* and return the scraped items and the crawler."""
    items: list[Any] = []

    def collect(item: Any, **kwargs: Any) -> None:
        items.append(item)

    crawler = get_crawler(SingleRequestSpider, settings)
    crawler.signals.connect(collect, signal=signals.item_scraped)
    await maybe_deferred_to_future(
        crawler.crawl(seed=Request(url), callback_func=callback)
    )
    return items, crawler


async def _close(response: WebSocketResponse) -> AsyncIterator[Any]:
    await response.close()
    return
    yield


class TestWebSocketDownloadHandler:
    @coroutine_test
    @pytest.mark.parametrize("is_secure", [False, True])
    async def test_echo(self, ws_server: WebSocketMockServer, is_secure: bool) -> None:
        async def callback(response: WebSocketResponse) -> AsyncIterator[Any]:
            assert isinstance(response, WebSocketResponse)
            async with response:
                await response.send("ping")
                yield {"message": await response.receive()}

        items, _ = await _crawl(
            ws_server.url("/echo", is_secure=is_secure),
            callback,
            DOWNLOAD_VERIFY_CERTIFICATES=False,
        )
        assert items == [{"message": "ping"}]

    @coroutine_test
    async def test_iteration_over_server_push(
        self, ws_server: WebSocketMockServer
    ) -> None:
        async def callback(response: WebSocketResponse) -> AsyncIterator[Any]:
            async for message in response:
                yield {"message": message}

        items, _ = await _crawl(ws_server.url("/push"), callback)
        assert items == [{"message": f"push {index}"} for index in range(3)]

    @coroutine_test
    async def test_binary_message(self, ws_server: WebSocketMockServer) -> None:
        async def callback(response: WebSocketResponse) -> AsyncIterator[Any]:
            async with response:
                yield {"message": await response.receive()}

        items, _ = await _crawl(ws_server.url("/binary"), callback)
        assert items == [{"message": b"\x00\x01\x02"}]

    @coroutine_test
    async def test_handshake_response(self, ws_server: WebSocketMockServer) -> None:
        _, crawler = await _crawl(ws_server.url("/echo"), _close)
        assert crawler.spider
        response = crawler.spider.meta["responses"][0]  # type: ignore[attr-defined]
        assert response.status == 101
        assert response.protocol == "http/1.1"
        assert response.ip_address == IPv4Address("127.0.0.1")
        assert response.certificate is None
        assert b"Sec-WebSocket-Accept" in response.headers

    @coroutine_test
    async def test_certificate(self, ws_server: WebSocketMockServer) -> None:
        _, crawler = await _crawl(
            ws_server.url("/echo", is_secure=True),
            _close,
            DOWNLOAD_VERIFY_CERTIFICATES=False,
        )
        assert crawler.spider
        response = crawler.spider.meta["responses"][0]  # type: ignore[attr-defined]
        assert isinstance(response.certificate, bytes)

    @coroutine_test
    async def test_request_headers(self, ws_server: WebSocketMockServer) -> None:
        async def callback(response: WebSocketResponse) -> AsyncIterator[Any]:
            async with response:
                yield json.loads(await response.receive())

        items, _ = await _crawl(
            ws_server.url("/headers"), callback, USER_AGENT="scrapy-ws-test"
        )
        assert items[0]["User-Agent"] == "scrapy-ws-test"

    @coroutine_test
    async def test_rejected_handshake_is_an_http_error(
        self, ws_server: WebSocketMockServer
    ) -> None:
        _, crawler = await _crawl(
            ws_server.url("/unavailable"), _close, RETRY_ENABLED=False
        )
        assert crawler.spider
        failure = crawler.spider.meta["failure"]  # type: ignore[attr-defined]
        assert isinstance(failure.value, HttpError)
        assert failure.value.response.status == 503

    @coroutine_test
    async def test_rejected_handshake_is_retried(
        self, ws_server: WebSocketMockServer
    ) -> None:
        _, crawler = await _crawl(ws_server.url("/unavailable"), _close, RETRY_TIMES=1)
        assert crawler.stats.get_value("retry/count") == 1

    @coroutine_test
    async def test_rejected_handshake_is_redirected(
        self, ws_server: WebSocketMockServer
    ) -> None:
        async def callback(response: WebSocketResponse) -> AsyncIterator[Any]:
            async with response:
                await response.send("ping")
                yield {"message": await response.receive()}

        items, crawler = await _crawl(ws_server.url("/redirect"), callback)
        assert items == [{"message": "ping"}]
        assert crawler.stats.get_value("downloader/request_count") == 2

    @coroutine_test
    async def test_download_maxsize(self, ws_server: WebSocketMockServer) -> None:
        async def callback(response: WebSocketResponse) -> AsyncIterator[Any]:
            async with response:
                with pytest.raises(DownloadFailedError):
                    await response.receive()
            yield {"closed": True}

        items, _ = await _crawl(ws_server.url("/large"), callback, DOWNLOAD_MAXSIZE=100)
        assert items == [{"closed": True}]

    @coroutine_test
    async def test_download_maxsize_while_iterating(
        self, ws_server: WebSocketMockServer
    ) -> None:
        async def callback(response: WebSocketResponse) -> AsyncIterator[Any]:
            async with response:
                with pytest.raises(DownloadFailedError):
                    async for _ in response:
                        pass
            yield {"closed": True}

        items, _ = await _crawl(ws_server.url("/large"), callback, DOWNLOAD_MAXSIZE=100)
        assert items == [{"closed": True}]

    @coroutine_test
    async def test_open_connection_occupies_a_slot(
        self, ws_server: WebSocketMockServer
    ) -> None:
        """A request waits for the connection of the previous one to close,
        because an open connection keeps occupying its downloader slot."""

        class TwoRequestSpider(Spider):
            name = "two"
            custom_settings = {"CONCURRENT_REQUESTS": 1}
            order: list[str] = []

            async def start(self) -> AsyncIterator[Any]:
                for index in range(2):
                    yield Request(
                        ws_server.url("/echo"),
                        cb_kwargs={"index": index},
                        dont_filter=True,
                    )

            async def parse(  # type: ignore[override]
                self, response: WebSocketResponse, index: int
            ) -> AsyncIterator[Any]:
                self.order.append(f"open {index}")
                async with response:
                    await response.send("ping")
                    await response.receive()
                self.order.append(f"close {index}")
                return
                yield

        crawler = get_crawler(TwoRequestSpider)
        await maybe_deferred_to_future(crawler.crawl())
        assert TwoRequestSpider.order == ["open 0", "close 0", "open 1", "close 1"]

    @coroutine_test
    async def test_abandoned_connection_does_not_block_the_shutdown(
        self, ws_server: WebSocketMockServer
    ) -> None:
        """A connection that the spider leaves open is closed along with the
        download handler."""

        async def callback(response: WebSocketResponse) -> AsyncIterator[Any]:
            yield {"abandoned": True}

        items, _ = await _crawl(
            ws_server.url("/echo"), callback, CLOSESPIDER_ITEMCOUNT=1
        )
        assert items == [{"abandoned": True}]

    def test_no_websockets_library(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "scrapy.core.downloader.handlers.websocket.HAS_WEBSOCKETS", False
        )
        with pytest.raises(NotConfigured, match="websockets library"):
            build_from_crawler(WebSocketDownloadHandler, get_crawler())
