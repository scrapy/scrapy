from __future__ import annotations

from logging import WARNING, LogRecord
from typing import TYPE_CHECKING

import pytest

from scrapy.downloadermiddlewares.retry import get_retry_request
from scrapy.http import Request, Response
from scrapy.spidermiddlewares.metacopy import MetaCopyDetectionMiddleware
from scrapy.spiders import Spider
from scrapy.utils.misc import build_from_crawler
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
    return build_from_crawler(MetaCopyDetectionMiddleware, crawler)


def process(
    mw: MetaCopyDetectionMiddleware,
    requests: list[Request],
    response: Response | None = None,
) -> list[Request]:
    if response is None:
        response = make_response()
    return list(mw.process_spider_output(response, requests))


def test_no_warning_for_clean_request(
    mw: MetaCopyDetectionMiddleware, caplog: pytest.LogCaptureFixture
) -> None:
    req = Request("https://example.com/1", meta={"my_key": "value"})
    with caplog.at_level(WARNING):
        process(mw, [req])
    assert not caplog.records


def test_warns_on_internal_key(
    mw: MetaCopyDetectionMiddleware, caplog: pytest.LogCaptureFixture
) -> None:
    req = Request("https://example.com/1", meta={"retry_times": 1})
    with caplog.at_level(WARNING):
        process(mw, [req])
    assert len(caplog.records) == 1
    assert "retry_times" in caplog.text
    assert "https://example.com/1" in caplog.text


def test_warns_once_across_multiple_requests(
    mw: MetaCopyDetectionMiddleware, caplog: pytest.LogCaptureFixture
) -> None:
    reqs = [
        Request("https://example.com/1", meta={"retry_times": 1}),
        Request("https://example.com/2", meta={"retry_times": 2}),
    ]
    with caplog.at_level(WARNING):
        process(mw, reqs)
    assert len(caplog.records) == 1


def test_reports_all_found_keys(
    mw: MetaCopyDetectionMiddleware, caplog: pytest.LogCaptureFixture
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
    mw: MetaCopyDetectionMiddleware, caplog: pytest.LogCaptureFixture
) -> None:
    response = make_response("https://source.example.com")
    req = Request("https://example.com/1", meta={"retry_times": 1})
    with caplog.at_level(WARNING):
        process(mw, [req], response=response)
    assert "https://source.example.com" in caplog.text


@pytest.fixture
def skip_keys_mw() -> MetaCopyDetectionMiddleware:
    crawler = get_crawler(Spider, {"META_COPY_WARN_SKIP_KEYS": ["retry_times"]})
    return build_from_crawler(MetaCopyDetectionMiddleware, crawler)


def test_skip_keys_setting(
    skip_keys_mw: MetaCopyDetectionMiddleware, caplog: pytest.LogCaptureFixture
) -> None:
    req = Request("https://example.com/1", meta={"retry_times": 1})
    with caplog.at_level(WARNING):
        process(skip_keys_mw, [req])
    assert not caplog.records


def test_skip_keys_setting_partial(
    skip_keys_mw: MetaCopyDetectionMiddleware, caplog: pytest.LogCaptureFixture
) -> None:
    req = Request(
        "https://example.com/1",
        meta={"retry_times": 1, "redirect_times": 2},
    )
    with caplog.at_level(WARNING):
        process(skip_keys_mw, [req])
    assert len(caplog.records) == 1
    assert "retry_times" not in caplog.text
    assert "redirect_times" in caplog.text


def test_no_warning_for_start_requests(
    mw: MetaCopyDetectionMiddleware, caplog: pytest.LogCaptureFixture
) -> None:
    req = Request("https://example.com/1", meta={"retry_times": 1})
    with caplog.at_level(WARNING):
        list(mw.process_spider_output(None, [req]))
    assert not caplog.records


def warnings(caplog: pytest.LogCaptureFixture) -> list[LogRecord]:
    """Return the captured warnings, leaving out e.g. the debug message that
    get_retry_request() logs."""
    return [record for record in caplog.records if record.levelno >= WARNING]


def make_downloaded_response(url: str = "https://example.com") -> Response:
    """Return a response whose request has the meta keys that Scrapy
    components set while downloading it."""
    request = Request(
        url,
        meta={
            "cache_timestamp": 1700000000,
            "download_latency": 0.5,
            "redirect_times": 1,
            "redirect_urls": ["https://example.com/old"],
        },
    )
    return Response(url, request=request)


def test_no_warning_for_retry_request(
    crawler: Crawler,
    mw: MetaCopyDetectionMiddleware,
    caplog: pytest.LogCaptureFixture,
) -> None:
    crawler.spider = crawler._create_spider("foo")
    response = make_downloaded_response()
    assert response.request is not None
    req = get_retry_request(response.request, spider=crawler.spider, reason="empty")
    assert req is not None
    with caplog.at_level(WARNING):
        assert process(mw, [req], response=response) == [req]
    assert not warnings(caplog)


def test_no_warning_for_second_retry_request(
    crawler: Crawler,
    mw: MetaCopyDetectionMiddleware,
    caplog: pytest.LogCaptureFixture,
) -> None:
    crawler.spider = crawler._create_spider("foo")
    response = make_downloaded_response()
    assert response.request is not None
    response.request.meta["retry_times"] = 1
    req = get_retry_request(response.request, spider=crawler.spider, reason="empty")
    assert req is not None
    assert req.meta["retry_times"] == 2
    with caplog.at_level(WARNING):
        process(mw, [req], response=response)
    assert not warnings(caplog)


def test_warns_on_copied_meta_after_retry_request(
    crawler: Crawler,
    mw: MetaCopyDetectionMiddleware,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Skipping a retry does not use up the warning of the crawl."""
    crawler.spider = crawler._create_spider("foo")
    response = make_downloaded_response()
    assert response.request is not None
    retry = get_retry_request(response.request, spider=crawler.spider, reason="empty")
    assert retry is not None
    copy = Request("https://example.com/1", meta=response.meta)
    with caplog.at_level(WARNING):
        process(mw, [retry, copy], response=response)
    assert len(warnings(caplog)) == 1
    assert "download_latency" in caplog.text
    assert "https://example.com/1" in caplog.text


def test_warns_on_copy_of_retry_request(
    crawler: Crawler,
    mw: MetaCopyDetectionMiddleware,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Only the request that get_retry_request() returns is skipped, not
    requests built from it."""
    crawler.spider = crawler._create_spider("foo")
    response = make_downloaded_response()
    assert response.request is not None
    retry = get_retry_request(response.request, spider=crawler.spider, reason="empty")
    assert retry is not None
    req = retry.replace(url="https://example.com/1")
    with caplog.at_level(WARNING):
        process(mw, [req], response=response)
    assert len(warnings(caplog)) == 1
    assert "retry_times" in caplog.text
