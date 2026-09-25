from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from scrapy.http import Request, Response
from scrapy.spidermiddlewares.sessions import SessionsSpiderMiddleware
from scrapy.spiders import Spider
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.test import get_crawler
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from tests.mockserver.http import MockServer

UNSET = object()


@pytest.fixture
def mw() -> SessionsSpiderMiddleware:
    return build_from_crawler(SessionsSpiderMiddleware, get_crawler(Spider))


def process(mw: SessionsSpiderMiddleware, source_meta: dict[str, Any] | None) -> Any:
    response = None
    if source_meta is not None:
        response = Response("https://example.com")
        response.request = Request("https://example.com", meta=source_meta)
    request = Request("https://example.com/next")
    assert list(mw.process_spider_output(response, [request])) == [request]
    return request.meta.get("session", UNSET)


def test_inherit(mw: SessionsSpiderMiddleware) -> None:
    assert process(mw, {"session": "store1"}) == "store1"


def test_inherit_none(mw: SessionsSpiderMiddleware) -> None:
    assert process(mw, {"session": None}) is None


def test_unset_source(mw: SessionsSpiderMiddleware) -> None:
    assert process(mw, {}) is UNSET


def test_start_request(mw: SessionsSpiderMiddleware) -> None:
    assert process(mw, None) is UNSET


def test_own_session_wins(mw: SessionsSpiderMiddleware) -> None:
    response = Response("https://example.com")
    response.request = Request("https://example.com", meta={"session": "store1"})
    request = Request("https://example.com/next", meta={"session": "store2"})
    list(mw.process_spider_output(response, [request]))
    assert request.meta["session"] == "store2"


def test_items_pass_through(mw: SessionsSpiderMiddleware) -> None:
    response = Response("https://example.com")
    response.request = Request("https://example.com", meta={"session": "store1"})
    item = {"a": 1}
    assert list(mw.process_spider_output(response, [item])) == [item]


class _CookieSpider(Spider):
    name = "sessions"

    def __init__(self, mockserver: MockServer, **kwargs: Any):
        super().__init__(**kwargs)
        self.mockserver = mockserver
        self.sent: list[list[str]] = []

    async def start(self) -> AsyncIterator[Request]:
        yield Request(self.mockserver.url("/set-cookie?a=1"), meta={"session": "s1"})
        yield Request(self.mockserver.url("/set-cookie?b=2"))

    def parse(self, response: Response) -> Any:
        yield Request(
            self.mockserver.url("/echo"),
            callback=self.parse_echo,
            dont_filter=True,
        )

    def parse_echo(self, response: Response) -> None:
        self.sent.append(json.loads(response.text)["headers"].get("Cookie", []))


@coroutine_test
async def test_crawl(mockserver: MockServer) -> None:
    crawler = get_crawler(_CookieSpider)
    await crawler.crawl_async(mockserver=mockserver)
    assert isinstance(crawler.spider, _CookieSpider)
    assert sorted(crawler.spider.sent) == [["a=1"], ["b=2"]]
    assert "main" in crawler.sessions
    assert "s1" in crawler.sessions
