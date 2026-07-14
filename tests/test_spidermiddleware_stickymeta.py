from __future__ import annotations

from typing import Any

import pytest

from scrapy import Request, Spider
from scrapy.exceptions import NotConfigured
from scrapy.http import Response
from scrapy.spidermiddlewares.stickymeta import StickyMetaParamsMiddleware
from scrapy.utils.asyncgen import as_async_generator, collect_asyncgen
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.test import get_crawler
from tests.utils.decorators import coroutine_test

TEST_URL = "http://www.example.com"


def _make_mw(sticky_meta_keys: Any) -> StickyMetaParamsMiddleware:
    crawler = get_crawler(Spider, {"STICKY_META_KEYS": sticky_meta_keys})
    return build_from_crawler(StickyMetaParamsMiddleware, crawler)


async def _run_all_paths(
    mw: StickyMetaParamsMiddleware, response: Response, spider_output: list[Any]
) -> list[list[Any]]:
    """Run the spider output through every processing path of the middleware."""
    return [
        list(mw.process_spider_output(response, spider_output)),
        await collect_asyncgen(
            mw.process_spider_output_async(response, as_async_generator(spider_output))
        ),
    ]


def test_not_configured() -> None:
    crawler = get_crawler(Spider)
    with pytest.raises(NotConfigured):
        build_from_crawler(StickyMetaParamsMiddleware, crawler)


def test_comma_separated_string_setting() -> None:
    mw = _make_mw("param1,param2")
    assert mw.sticky_meta_keys == ["param1", "param2"]


@coroutine_test
async def test_sticky_params() -> None:
    mw = _make_mw(["param2"])
    request = Request(
        TEST_URL, meta={"param": "Will not be stickied", "param2": "Stickied!"}
    )
    response = Response(TEST_URL, request=request)
    spider_output = [Request(TEST_URL), {"name": "dummy"}]
    for processed in await _run_all_paths(mw, response, spider_output):
        assert processed[0].meta == {"param2": "Stickied!"}
        assert processed[1] == {"name": "dummy"}


@coroutine_test
async def test_sticky_param_does_not_override_manually_configured_param() -> None:
    mw = _make_mw(["param", "param2"])
    request = Request(TEST_URL, meta={"param": "Stickied!", "param2": "Stickied!"})
    response = Response(TEST_URL, request=request)
    spider_output = [Request(TEST_URL, meta={"param": "Override stickied"})]
    for processed in await _run_all_paths(mw, response, spider_output):
        assert processed[0].meta == {
            "param": "Override stickied",
            "param2": "Stickied!",
        }


@coroutine_test
async def test_start_requests_have_no_response() -> None:
    """Start seeds are processed with ``response=None`` and are left untouched."""
    mw = _make_mw(["param"])
    start_request = Request(TEST_URL, meta={"param": "value"})
    processed = await collect_asyncgen(
        mw.process_start(as_async_generator([start_request]))
    )
    assert processed[0].meta == {"param": "value"}
