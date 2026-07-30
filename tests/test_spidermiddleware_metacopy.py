from __future__ import annotations

from logging import WARNING
from typing import TYPE_CHECKING

import pytest

from scrapy.http import Request, Response
from scrapy.spidermiddlewares.metacopy import MetaCopyDetectionMiddleware
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler

if TYPE_CHECKING:
    from scrapy.crawler import Crawler


def make_response(url: str = "https://example.com") -> Response:
    response = Response(url)
    response.request = Request(url)
    return response


@pytest.fixture
def crawler() -> Crawler:
    return get_crawler(Spider)


@pytest.fixture
def mw(crawler: Crawler) -> MetaCopyDetectionMiddleware:
    return MetaCopyDetectionMiddleware.from_crawler(crawler)


def process(
    mw: MetaCopyDetectionMiddleware,
    requests: list[Request],
    response: Response | None = None,
) -> list[Request]:
    if response is None:
        response = make_response()
    return list(mw.process_spider_output(response, requests))


class TestInternalKeysCheck:
    def test_no_warning_for_clean_request(
        self, mw: MetaCopyDetectionMiddleware, caplog: pytest.LogCaptureFixture
    ) -> None:
        req = Request("https://example.com/1", meta={"my_key": "value"})
        with caplog.at_level(WARNING):
            process(mw, [req])
        assert not caplog.records

    def test_warns_on_internal_key(
        self, mw: MetaCopyDetectionMiddleware, caplog: pytest.LogCaptureFixture
    ) -> None:
        req = Request("https://example.com/1", meta={"retry_times": 1})
        with caplog.at_level(WARNING):
            process(mw, [req])
        assert len(caplog.records) == 1
        assert "retry_times" in caplog.text
        assert "https://example.com/1" in caplog.text

    def test_warns_once_across_multiple_requests(
        self, mw: MetaCopyDetectionMiddleware, caplog: pytest.LogCaptureFixture
    ) -> None:
        reqs = [
            Request("https://example.com/1", meta={"retry_times": 1}),
            Request("https://example.com/2", meta={"retry_times": 2}),
        ]
        with caplog.at_level(WARNING):
            process(mw, reqs)
        assert len(caplog.records) == 1

    def test_reports_all_found_keys(
        self, mw: MetaCopyDetectionMiddleware, caplog: pytest.LogCaptureFixture
    ) -> None:
        req = Request(
            "https://example.com/1",
            meta={"retry_times": 1, "redirect_times": 2},
        )
        with caplog.at_level(WARNING):
            process(mw, [req])
        assert "retry_times" in caplog.text
        assert "redirect_times" in caplog.text

    def test_includes_source_response_in_message(
        self, mw: MetaCopyDetectionMiddleware, caplog: pytest.LogCaptureFixture
    ) -> None:
        response = make_response("https://source.example.com")
        req = Request("https://example.com/1", meta={"retry_times": 1})
        with caplog.at_level(WARNING):
            process(mw, [req], response=response)
        assert "https://source.example.com" in caplog.text

    def test_skip_keys_setting(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(WARNING):
            crawler = get_crawler(Spider, {"META_COPY_WARN_SKIP_KEYS": ["retry_times"]})
            mw = MetaCopyDetectionMiddleware.from_crawler(crawler)
            req = Request("https://example.com/1", meta={"retry_times": 1})
            process(mw, [req])
        assert not caplog.records

    def test_skip_keys_setting_partial(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(WARNING):
            crawler = get_crawler(Spider, {"META_COPY_WARN_SKIP_KEYS": ["retry_times"]})
            mw = MetaCopyDetectionMiddleware.from_crawler(crawler)
            req = Request(
                "https://example.com/1",
                meta={"retry_times": 1, "redirect_times": 2},
            )
            process(mw, [req])
        assert len(caplog.records) == 1
        assert "retry_times" not in caplog.text
        assert "redirect_times" in caplog.text

    def test_no_warning_for_start_requests(
        self, mw: MetaCopyDetectionMiddleware, caplog: pytest.LogCaptureFixture
    ) -> None:
        req = Request("https://example.com/1", meta={"retry_times": 1})
        with caplog.at_level(WARNING):
            list(mw.process_spider_output(None, [req]))
        assert not caplog.records
