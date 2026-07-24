from logging import INFO

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
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler as _get_crawler

UNSET = object()


def get_crawler(settings=None, spidercls=None):
    settings = settings or {}
    settings["AUTOTHROTTLE_ENABLED"] = True
    return _get_crawler(settings_dict=settings, spidercls=spidercls)


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
    ("spider", "setting", "expected"),
    [
        (UNSET, UNSET, DOWNLOAD_DELAY),
        (1.0, UNSET, 1.0),
        (UNSET, 1.0, 1.0),
        (1.0, 2.0, 1.0),
        (3.0, 2.0, 3.0),
    ],
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
    at._spider_opened(DefaultSpider())
    assert at.maxdelay == expected


@pytest.mark.parametrize(
    ("min_spider", "min_setting", "start_setting", "expected"),
    [
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
    ],
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
    assert at._startdelay == expected


@pytest.mark.parametrize(
    "meta",
    [
        # No download latency to react to.
        {},
        # Adjustment explicitly opted out of for this request.
        {"download_latency": 1.0, "autothrottle_dont_adjust_delay": True},
    ],
    ids=["no-latency", "dont-adjust"],
)
def test_skipped(meta):
    crawler = get_crawler()
    at = build_from_crawler(AutoThrottle, crawler)
    spider = DefaultSpider()
    at._spider_opened(spider)
    request = Request("https://example.com", meta=meta)
    response = Response(request.url)
    at._adjust_delay = None  # Raise an exception if called.

    at._response_downloaded(response, request, spider)


def _adjust(crawler, at, spider, download_latency, scope_delay, status=200, body=b""):
    """Drive one response through the extension and return the resulting scope
    delay. The scope is pre-marked as started so *scope_delay* is used verbatim
    as the old delay (no AUTOTHROTTLE_START_DELAY bump)."""
    scope_id = "example.com"
    assert crawler.throttler is not None
    at._started_scopes.add(scope_id)
    crawler.throttler.set_scope_delay(scope_id, scope_delay)
    request = Request(
        f"https://{scope_id}", meta={"download_latency": download_latency}
    )
    response = Response(request.url, status=status, body=body)
    at._response_downloaded(response, request, spider)
    return crawler.throttler.get_scope_delay(scope_id)


@pytest.mark.parametrize(
    ("download_latency", "target_concurrency", "scope_delay", "expected"),
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
def test_adjustment(download_latency, target_concurrency, scope_delay, expected):
    settings = {"AUTOTHROTTLE_TARGET_CONCURRENCY": target_concurrency}
    crawler = get_crawler(settings)
    at = build_from_crawler(AutoThrottle, crawler)
    spider = DefaultSpider()
    at._spider_opened(spider)

    delay = _adjust(crawler, at, spider, download_latency, scope_delay)

    assert delay == expected, f"{delay} != {expected}"


@pytest.mark.parametrize(
    ("mindelay", "maxdelay", "expected"),
    [
        (0.5, 2.0, 1.0),
        (0.25, 0.5, 0.5),
        (2.0, 4.0, 2.0),
    ],
)
def test_adjustment_limits(mindelay, maxdelay, expected):
    download_latency, target_concurrency, scope_delay = (2.0, 2.0, 1.0)
    # expected adjustment without limits with these values: 1.0
    settings = {
        "AUTOTHROTTLE_MAX_DELAY": maxdelay,
        "AUTOTHROTTLE_TARGET_CONCURRENCY": target_concurrency,
        "DOWNLOAD_DELAY": mindelay,
    }
    crawler = get_crawler(settings)
    at = build_from_crawler(AutoThrottle, crawler)
    spider = DefaultSpider()
    at._spider_opened(spider)

    delay = _adjust(crawler, at, spider, download_latency, scope_delay)

    assert delay == expected, f"{delay} != {expected}"


@pytest.mark.parametrize(
    ("download_latency", "target_concurrency", "scope_delay", "expected"),
    [
        (2.0, 2.0, 1.0, 1.0),
        (1.0, 2.0, 1.0, 1.0),  # Instead of 0.75
        (4.0, 2.0, 1.0, 2.0),
    ],
)
def test_adjustment_bad_response(
    download_latency, target_concurrency, scope_delay, expected
):
    settings = {"AUTOTHROTTLE_TARGET_CONCURRENCY": target_concurrency}
    crawler = get_crawler(settings)
    at = build_from_crawler(AutoThrottle, crawler)
    spider = DefaultSpider()
    at._spider_opened(spider)

    delay = _adjust(crawler, at, spider, download_latency, scope_delay, status=400)

    assert delay == expected, f"{delay} != {expected}"


def test_start_delay_applied_once_per_scope():
    # The first response for a scope raises the delay to AUTOTHROTTLE_START_DELAY
    # before adjusting; subsequent responses adjust from the current scope delay.
    crawler = get_crawler({"AUTOTHROTTLE_START_DELAY": 5.0})
    at = build_from_crawler(AutoThrottle, crawler)
    spider = DefaultSpider()
    at._spider_opened(spider)
    assert crawler.throttler is not None
    scope_id = "example.com"
    request = Request(f"https://{scope_id}", meta={"download_latency": 5.0})
    at._response_downloaded(Response(request.url), request, spider)
    # old delay = max(0, 5.0) = 5.0; target = 5.0/1.0; new = (5+5)/2 = 5.0.
    assert crawler.throttler.get_scope_delay(scope_id) == 5.0
    assert scope_id in at._started_scopes


def test_debug(caplog):
    settings = {"AUTOTHROTTLE_DEBUG": True}
    crawler = get_crawler(settings)
    at = build_from_crawler(AutoThrottle, crawler)
    spider = DefaultSpider()
    at._spider_opened(spider)

    caplog.clear()
    with caplog.at_level(INFO):
        _adjust(crawler, at, spider, download_latency=1.0, scope_delay=2.0, body=b"foo")

    assert caplog.record_tuples == [
        (
            "scrapy.extensions.throttle",
            INFO,
            "slot: example.com | delay: 1500 ms (-500) | latency: 1000 ms | size:     3 bytes",
        ),
    ]


def test_debug_disabled(caplog):
    crawler = get_crawler()
    at = build_from_crawler(AutoThrottle, crawler)
    spider = DefaultSpider()
    at._spider_opened(spider)

    caplog.clear()
    with caplog.at_level(INFO):
        _adjust(crawler, at, spider, download_latency=1.0, scope_delay=2.0, body=b"foo")

    assert caplog.record_tuples == []
