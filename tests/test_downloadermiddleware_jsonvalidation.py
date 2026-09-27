from __future__ import annotations

import json
from gzip import compress

import pytest

from scrapy.downloadermiddlewares.jsonvalidation import JsonValidationMiddleware
from scrapy.exceptions import NotConfigured
from scrapy.http import JsonResponse, Request, Response, TextResponse
from scrapy.spiders import Spider
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.test import get_crawler
from tests.test_downloadermiddleware import TestManagerBase
from tests.utils.decorators import coroutine_test

URL = "https://example.com"


def _mw() -> JsonValidationMiddleware:
    crawler = get_crawler(Spider, {"JSONVALIDATION_ENABLED": True})
    return build_from_crawler(JsonValidationMiddleware, crawler)


def test_disabled_by_default() -> None:
    with pytest.raises(NotConfigured):
        build_from_crawler(JsonValidationMiddleware, get_crawler(Spider))


def test_valid() -> None:
    response = JsonResponse(URL, body=b'{"a": 1}')
    assert _mw().process_response(Request(URL), response) is response


@pytest.mark.parametrize("body", [b"", b"{", b"<html></html>"])
def test_invalid(body: bytes) -> None:
    response = JsonResponse(URL, body=body)
    with pytest.raises(json.JSONDecodeError):
        _mw().process_response(Request(URL), response)


@pytest.mark.parametrize(
    ("method", "status", "cls"),
    [
        ("GET", 200, Response),
        ("GET", 200, TextResponse),
        ("GET", 204, JsonResponse),
        ("GET", 404, JsonResponse),
        ("GET", 503, JsonResponse),
        ("HEAD", 200, JsonResponse),
    ],
)
def test_skipped(method: str, status: int, cls: type[Response]) -> None:
    response = cls(URL, status=status, body=b"{")
    result = _mw().process_response(Request(URL, method=method), response)
    assert result is response


class TestChain(TestManagerBase):
    settings_dict = {
        "JSONVALIDATION_ENABLED": True,
        "DOWNLOADER_MIDDLEWARE_RESPONSE_EXCEPTIONS": True,
    }

    @coroutine_test
    async def test_retry(self) -> None:
        req = Request(URL)
        async with self.get_mwman() as mwman:
            result = await self._download(mwman, req, JsonResponse(URL, body=b"{"))
        assert isinstance(result, Request)
        assert result.meta["retry_times"] == 1

    @coroutine_test
    async def test_compressed(self) -> None:
        req = Request(URL)
        resp = Response(
            URL,
            body=compress(b'{"a": 1}'),
            headers={"Content-Type": "application/json", "Content-Encoding": "gzip"},
        )
        async with self.get_mwman() as mwman:
            result = await self._download(mwman, req, resp)
        assert isinstance(result, JsonResponse)
        assert result.json() == {"a": 1}
