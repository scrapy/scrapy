from logging import INFO
from unittest.mock import Mock

import pytest

from scrapy import Request, Spider
from scrapy.exceptions import NotConfigured
from scrapy.extensions.throttle import AutoThrottle
from scrapy.http.response import Response
from scrapy.settings.default_settings import (
    AUTOTHROTTLE_MAX_DELAY,
    AUTOTHROTTLE_START_DELAY,
    DOWNLOAD_DELAY,
)
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.test import get_crawler as _get_crawler

UNSET = object()


class TestSpider(Spider):
    name = "test"


def get_crawler(settings=None, spidercls=None):
    settings = settings or {}
    settings["AUTOTHROTTLE_ENABLED"] = True
    return _get_crawler(settings_dict=settings, spidercls=spidercls)


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        (UNSET, False),
        (False, False),
        (True, True),
    ),
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
    (
        0.0,
        -1.0,
    ),
)
def test_target_concurrency_invalid(value):
    settings = {"AUTOTHROTTLE_TARGET_CONCURRENCY": value}
    crawler = get_crawler(settings)
    with pytest.raises(NotConfigured):
        build_from_crawler(AutoThrottle, crawler)


@pytest.mark.parametrize(
    ("spider", "setting", "expected"),
    (
        (UNSET, UNSET, DOWNLOAD_DELAY),
        (1.0, UNSET, 1.0),
        (UNSET, 1.0, 1.0),
        (1.0, 2.0, 1.0),
        (3.0, 2.0, 3.0),
    ),
)
def test_mindelay_definition(spider, setting, expected):
    settings = {}
    if setting is not UNSET:
        settings["DOWNLOAD_DELAY"] = setting

    class _TestSpider(Spider):
        name = "test"

    if spider is not UNSET:
        _TestSpider.download_delay = spider

    crawler = get_crawler(settings, _TestSpider)
    at = build_from_crawler(AutoThrottle, crawler)
    at._spider_opened(_TestSpider())
    assert at.mindelay == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    (
        (UNSET, AUTOTHROTTLE_MAX_DELAY),
        (1.0, 1.0),
    ),
)
def test_maxdelay_definition(value, expected):
    settings = {}
    if value is not UNSET:
        settings["AUTOTHROTTLE_MAX_DELAY"] = value
    crawler = get_crawler(settings)
    at = build_from_crawler(AutoThrottle, crawler)
    at._spider_opened(TestSpider())
    assert at.maxdelay == expected


@pytest.mark.parametrize(
    ("min_spider", "min_setting", "start_setting", "expected"),
    (
        (UNSET, UNSET, UNSET, AUTOTHROTTLE_START_DELAY),
        (AUTOTHROTTLE_START_DELAY - 1.0, UNSET, UNSET, AUTOTHROTTLE_START_DELAY),
        (AUTOTHROTTLE_START_DELAY + 1.0, UNSET, UNSET, AUTOTHROTTLE_START_DELAY + 1.0),
        (UNSET, AUTOTHROTTLE_START_DELAY - 1.0, UNSET, AUTOTHROTTLE_START_DELAY),
        (UNSET, AUTOTHROTTLE_START_DELAY + 1.0, UNSET, AUTOTHROTTLE_START_DELAY + 1.0),
        (UNSET, UNSET, AUTOTHROTTLE_START_DELAY - 1.0, AUTOTHROTTLE_START_DELAY - 1.0),
        (UNSET, UNSET, AUTOTHROTTLE_START_DELAY + 1.0, AUTOTHROTTLE_START_DELAY + 1.0),
        (
            AUTOTHROTTLE_START_DELAY + 1.0,
            AUTOTHROTTLE_START_DELAY + 2.0,
            UNSET,
            AUTOTHROTTLE_START_DELAY + 1.0,
        ),
        (
            AUTOTHROTTLE_START_DELAY + 2.0,
            UNSET,
            AUTOTHROTTLE_START_DELAY + 1.0,
            AUTOTHROTTLE_START_DELAY + 2.0,
        ),
        (
            AUTOTHROTTLE_START_DELAY + 1.0,
            UNSET,
            AUTOTHROTTLE_START_DELAY + 2.0,
            AUTOTHROTTLE_START_DELAY + 2.0,
        ),
    ),
)
def test_startdelay_definition(min_spider, min_setting, start_setting, expected):
    settings = {}
    if min_setting is not UNSET:
        settings["DOWNLOAD_DELAY"] = min_setting
    if start_setting is not UNSET:
        settings["AUTOTHROTTLE_START_DELAY"] = start_setting

    class _TestSpider(Spider):
        name = "test"

    if min_spider is not UNSET:
        _TestSpider.download_delay = min_spider

    crawler = get_crawler(settings, _TestSpider)
    at = build_from_crawler(AutoThrottle, crawler)
    spider = _TestSpider()
    at._spider_opened(spider)
    assert spider.download_delay == expected


@pytest.mark.parametrize(
    ("meta", "slot"),
    (
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
    ),
)
def test_skipped(meta, slot):
    crawler = get_crawler()
    at = build_from_crawler(AutoThrottle, crawler)
    spider = TestSpider()
    at._spider_opened(spider)
    request = Request("https://example.com", meta=meta)

    crawler.engine = Mock()
    crawler.engine.downloader = Mock()
    crawler.engine.downloader.slots = {}
    if slot is not None:
        crawler.engine.downloader.slots[slot] = object()
    at._adjust_delay = None  # Raise exception if called.

    at._response_downloaded(None, request, spider)


@pytest.mark.parametrize(
    ("download_latency", "target_concurrency", "slot_delay", "expected"),
    (
        (2.0, 2.0, 1.0, 1.0),
        (1.0, 2.0, 1.0, 0.75),
        (4.0, 2.0, 1.0, 2.0),
        (2.0, 1.0, 1.0, 2.0),
        (2.0, 4.0, 1.0, 0.75),
        (2.0, 2.0, 0.5, 1.0),
        (2.0, 2.0, 2.0, 1.5),
    ),
)
def test_adjustment(download_latency, target_concurrency, slot_delay, expected):
    settings = {"AUTOTHROTTLE_TARGET_CONCURRENCY": target_concurrency}
    crawler = get_crawler(settings)
    at = build_from_crawler(AutoThrottle, crawler)
    spider = TestSpider()
    at._spider_opened(spider)
    meta = {"download_latency": download_latency, "download_slot": "foo"}
    request = Request("https://example.com", meta=meta)
    response = Response(request.url)

    crawler.engine = Mock()
    crawler.engine.downloader = Mock()
    crawler.engine.downloader.slots = {}
    slot = Mock()
    slot.delay = slot_delay
    crawler.engine.downloader.slots["foo"] = slot

    at._response_downloaded(response, request, spider)

    assert slot.delay == expected, f"{slot.delay} != {expected}"


@pytest.mark.parametrize(
    ("mindelay", "maxdelay", "expected"),
    (
        (0.5, 2.0, 1.0),
        (0.25, 0.5, 0.5),
        (2.0, 4.0, 2.0),
    ),
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
    spider = TestSpider()
    at._spider_opened(spider)
    meta = {"download_latency": download_latency, "download_slot": "foo"}
    request = Request("https://example.com", meta=meta)
    response = Response(request.url)

    crawler.engine = Mock()
    crawler.engine.downloader = Mock()
    crawler.engine.downloader.slots = {}
    slot = Mock()
    slot.delay = slot_delay
    crawler.engine.downloader.slots["foo"] = slot

    at._response_downloaded(response, request, spider)

    assert slot.delay == expected, f"{slot.delay} != {expected}"


@pytest.mark.parametrize(
    ("download_latency", "target_concurrency", "slot_delay", "expected"),
    (
        (2.0, 2.0, 1.0, 1.0),
        (1.0, 2.0, 1.0, 1.0),  # Instead of 0.75
        (4.0, 2.0, 1.0, 2.0),
    ),
)
def test_adjustment_bad_response(
    download_latency, target_concurrency, slot_delay, expected
):
    settings = {"AUTOTHROTTLE_TARGET_CONCURRENCY": target_concurrency}
    crawler = get_crawler(settings)
    at = build_from_crawler(AutoThrottle, crawler)
    spider = TestSpider()
    at._spider_opened(spider)
    meta = {"download_latency": download_latency, "download_slot": "foo"}
    request = Request("https://example.com", meta=meta)
    response = Response(request.url, status=400)

    crawler.engine = Mock()
    crawler.engine.downloader = Mock()
    crawler.engine.downloader.slots = {}
    slot = Mock()
    slot.delay = slot_delay
    crawler.engine.downloader.slots["foo"] = slot

    at._response_downloaded(response, request, spider)

    assert slot.delay == expected, f"{slot.delay} != {expected}"


def test_debug(caplog):
    settings = {"AUTOTHROTTLE_DEBUG": True}
    crawler = get_crawler(settings)
    at = build_from_crawler(AutoThrottle, crawler)
    spider = TestSpider()
    at._spider_opened(spider)
    meta = {"download_latency": 1.0, "download_slot": "foo"}
    request = Request("https://example.com", meta=meta)
    response = Response(request.url, body=b"foo")

    crawler.engine = Mock()
    crawler.engine.downloader = Mock()
    crawler.engine.downloader.slots = {}
    slot = Mock()
    slot.delay = 2.0
    slot.transferring = (None, None)
    crawler.engine.downloader.slots["foo"] = slot

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
    spider = TestSpider()
    at._spider_opened(spider)
    meta = {"download_latency": 1.0, "download_slot": "foo"}
    request = Request("https://example.com", meta=meta)
    response = Response(request.url, body=b"foo")

    crawler.engine = Mock()
    crawler.engine.downloader = Mock()
    crawler.engine.downloader.slots = {}
    slot = Mock()
    slot.delay = 2.0
    slot.transferring = (None, None)
    crawler.engine.downloader.slots["foo"] = slot

    caplog.clear()
    with caplog.at_level(INFO):
        at._response_downloaded(response, request, spider)

    assert caplog.record_tuples == []
