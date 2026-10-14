from logging import INFO
from typing import Any
from unittest.mock import Mock

import pytest

from scrapy import Request, Spider
from scrapy.crawler import Crawler
from scrapy.exceptions import NotConfigured
from scrapy.extensions.throttle import AutoThrottle
from scrapy.http.response import Response
from scrapy.settings.default_settings import (
    AUTOTHROTTLE_MAX_DELAY,
    AUTOTHROTTLE_START_DELAY,
    DOWNLOAD_DELAY,
)
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler as _get_crawler

UNSET = object()


def get_crawler(
    settings: dict[str, Any] | None = None, spidercls: type[Spider] | None = None
) -> Crawler:
    settings = settings or {}
    settings["AUTOTHROTTLE_ENABLED"] = True
    return _get_crawler(settings_dict=settings, spidercls=spidercls)


def _mock_downloader(crawler: Crawler) -> Mock:
    """Give *crawler* a mock engine, whose downloader AutoThrottle reads."""
    crawler.engine = Mock()
    downloader: Mock = crawler.engine.downloader
    downloader.slots = {}
    return downloader


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (UNSET, False),
        (False, False),
        (True, True),
    ],
)
def test_enabled(value, expected):
    settings = {}
    if value is not UNSET:
        settings["AUTOTHROTTLE_ENABLED"] = value
    crawler = _get_crawler(settings_dict=settings)
    if expected:
        build_from_crawler(AutoThrottle, crawler)
    else:
        with pytest.raises(NotConfigured):
            build_from_crawler(AutoThrottle, crawler)


@pytest.mark.parametrize(
    "value",
    [
        0.0,
        -1.0,
    ],
)
def test_target_concurrency_invalid(value):
    settings = {"AUTOTHROTTLE_TARGET_CONCURRENCY": value}
    crawler = get_crawler(settings)
    with pytest.raises(NotConfigured):
        build_from_crawler(AutoThrottle, crawler)


@pytest.mark.parametrize(
    ("setting", "expected"),
    [
        (UNSET, DOWNLOAD_DELAY),
        (1.0, 1.0),
    ],
)
def test_mindelay_definition(setting, expected):
    settings = {}
    if setting is not UNSET:
        settings["DOWNLOAD_DELAY"] = setting

    crawler = get_crawler(settings)
    at = build_from_crawler(AutoThrottle, crawler)
    _mock_downloader(crawler)
    at._spider_opened(DefaultSpider.from_crawler(crawler))
    assert at.mindelay == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (UNSET, AUTOTHROTTLE_MAX_DELAY),
        (1.0, 1.0),
    ],
)
def test_maxdelay_definition(value, expected):
    settings = {}
    if value is not UNSET:
        settings["AUTOTHROTTLE_MAX_DELAY"] = value
    crawler = get_crawler(settings)
    at = build_from_crawler(AutoThrottle, crawler)
    _mock_downloader(crawler)
    at._spider_opened(DefaultSpider.from_crawler(crawler))
    assert at.maxdelay == expected


@pytest.mark.parametrize(
    ("min_setting", "start_setting", "expected"),
    [
        (UNSET, UNSET, AUTOTHROTTLE_START_DELAY),
        (AUTOTHROTTLE_START_DELAY - 1.0, UNSET, AUTOTHROTTLE_START_DELAY),
        (AUTOTHROTTLE_START_DELAY + 1.0, UNSET, AUTOTHROTTLE_START_DELAY + 1.0),
        (UNSET, AUTOTHROTTLE_START_DELAY - 1.0, AUTOTHROTTLE_START_DELAY - 1.0),
        (UNSET, AUTOTHROTTLE_START_DELAY + 1.0, AUTOTHROTTLE_START_DELAY + 1.0),
        (
            AUTOTHROTTLE_START_DELAY + 2.0,
            AUTOTHROTTLE_START_DELAY + 1.0,
            AUTOTHROTTLE_START_DELAY + 2.0,
        ),
        (
            AUTOTHROTTLE_START_DELAY + 1.0,
            AUTOTHROTTLE_START_DELAY + 2.0,
            AUTOTHROTTLE_START_DELAY + 2.0,
        ),
    ],
)
def test_startdelay_definition(min_setting, start_setting, expected):
    settings = {}
    if min_setting is not UNSET:
        settings["DOWNLOAD_DELAY"] = min_setting
    if start_setting is not UNSET:
        settings["AUTOTHROTTLE_START_DELAY"] = start_setting

    crawler = get_crawler(settings)
    at = build_from_crawler(AutoThrottle, crawler)
    downloader = _mock_downloader(crawler)
    at._spider_opened(DefaultSpider.from_crawler(crawler))
    assert downloader._delay == expected


@pytest.mark.parametrize(
    ("meta", "slot"),
    [
        ({}, None),
        ({"download_latency": 1.0}, None),
        ({"download_slot": "foo"}, None),
        ({"download_slot": "foo"}, "foo"),
        ({"download_latency": 1.0, "download_slot": "foo"}, None),
        (
            {
                "download_latency": 1.0,
                "download_slot": "foo",
                "autothrottle_dont_adjust_delay": True,
            },
            "foo",
        ),
    ],
)
def test_skipped(meta, slot, monkeypatch):
    crawler = get_crawler()
    at = build_from_crawler(AutoThrottle, crawler)
    downloader = _mock_downloader(crawler)
    spider = DefaultSpider.from_crawler(crawler)
    at._spider_opened(spider)
    request = Request("https://example.com", meta=meta)

    if slot is not None:
        downloader.slots[slot] = object()
    # Fail instead of adjusting the delay.
    monkeypatch.setattr(at, "_adjust_delay", Mock(side_effect=AssertionError))

    at._response_downloaded(Response("https://example.com"), request, spider)


@pytest.mark.parametrize(
    ("download_latency", "target_concurrency", "slot_delay", "expected"),
    [
        (2.0, 2.0, 1.0, 1.0),
        (1.0, 2.0, 1.0, 0.75),
        (4.0, 2.0, 1.0, 2.0),
        (2.0, 1.0, 1.0, 2.0),
        (2.0, 4.0, 1.0, 0.75),
        (2.0, 2.0, 0.5, 1.0),
        (2.0, 2.0, 2.0, 1.5),
    ],
)
def test_adjustment(download_latency, target_concurrency, slot_delay, expected):
    settings = {"AUTOTHROTTLE_TARGET_CONCURRENCY": target_concurrency}
    crawler = get_crawler(settings)
    at = build_from_crawler(AutoThrottle, crawler)
    downloader = _mock_downloader(crawler)
    spider = DefaultSpider.from_crawler(crawler)
    at._spider_opened(spider)
    meta = {"download_latency": download_latency, "download_slot": "foo"}
    request = Request("https://example.com", meta=meta)
    response = Response(request.url)

    slot = Mock()
    slot.delay = slot_delay
    downloader.slots["foo"] = slot

    at._response_downloaded(response, request, spider)

    assert slot.delay == expected, f"{slot.delay} != {expected}"


@pytest.mark.parametrize(
    ("mindelay", "maxdelay", "expected"),
    [
        (0.5, 2.0, 1.0),
        (0.25, 0.5, 0.5),
        (2.0, 4.0, 2.0),
    ],
)
def test_adjustment_limits(mindelay, maxdelay, expected):
    download_latency, target_concurrency, slot_delay = (2.0, 2.0, 1.0)
    # expected adjustment without limits with these values: 1.0
    settings = {
        "AUTOTHROTTLE_MAX_DELAY": maxdelay,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": target_concurrency,
        "DOWNLOAD_DELAY": mindelay,
    }
    crawler = get_crawler(settings)
    at = build_from_crawler(AutoThrottle, crawler)
    downloader = _mock_downloader(crawler)
    spider = DefaultSpider.from_crawler(crawler)
    at._spider_opened(spider)
    meta = {"download_latency": download_latency, "download_slot": "foo"}
    request = Request("https://example.com", meta=meta)
    response = Response(request.url)

    slot = Mock()
    slot.delay = slot_delay
    downloader.slots["foo"] = slot

    at._response_downloaded(response, request, spider)

    assert slot.delay == expected, f"{slot.delay} != {expected}"


@pytest.mark.parametrize(
    ("download_latency", "target_concurrency", "slot_delay", "expected"),
    [
        (2.0, 2.0, 1.0, 1.0),
        (1.0, 2.0, 1.0, 1.0),  # Instead of 0.75
        (4.0, 2.0, 1.0, 2.0),
    ],
)
def test_adjustment_bad_response(
    download_latency, target_concurrency, slot_delay, expected
):
    settings = {"AUTOTHROTTLE_TARGET_CONCURRENCY": target_concurrency}
    crawler = get_crawler(settings)
    at = build_from_crawler(AutoThrottle, crawler)
    downloader = _mock_downloader(crawler)
    spider = DefaultSpider.from_crawler(crawler)
    at._spider_opened(spider)
    meta = {"download_latency": download_latency, "download_slot": "foo"}
    request = Request("https://example.com", meta=meta)
    response = Response(request.url, status=400)

    slot = Mock()
    slot.delay = slot_delay
    downloader.slots["foo"] = slot

    at._response_downloaded(response, request, spider)

    assert slot.delay == expected, f"{slot.delay} != {expected}"


def test_debug(caplog):
    settings = {"AUTOTHROTTLE_DEBUG": True}
    crawler = get_crawler(settings)
    at = build_from_crawler(AutoThrottle, crawler)
    downloader = _mock_downloader(crawler)
    spider = DefaultSpider.from_crawler(crawler)
    at._spider_opened(spider)
    meta = {"download_latency": 1.0, "download_slot": "foo"}
    request = Request("https://example.com", meta=meta)
    response = Response(request.url, body=b"foo")

    slot = Mock()
    slot.delay = 2.0
    slot.transferring = (None, None)
    downloader.slots["foo"] = slot

    caplog.clear()
    with caplog.at_level(INFO):
        at._response_downloaded(response, request, spider)

    assert caplog.record_tuples == [
        (
            "scrapy.extensions.throttle",
            INFO,
            "slot: foo | conc: 2 | delay: 1500 ms (-500) | latency: 1000 ms | size:     3 bytes",
        ),
    ]


def test_debug_disabled(caplog):
    crawler = get_crawler()
    at = build_from_crawler(AutoThrottle, crawler)
    downloader = _mock_downloader(crawler)
    spider = DefaultSpider.from_crawler(crawler)
    at._spider_opened(spider)
    meta = {"download_latency": 1.0, "download_slot": "foo"}
    request = Request("https://example.com", meta=meta)
    response = Response(request.url, body=b"foo")

    slot = Mock()
    slot.delay = 2.0
    slot.transferring = (None, None)
    downloader.slots["foo"] = slot

    caplog.clear()
    with caplog.at_level(INFO):
        at._response_downloaded(response, request, spider)

    assert caplog.record_tuples == []
