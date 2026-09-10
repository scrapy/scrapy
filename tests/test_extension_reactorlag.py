from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from scrapy.exceptions import NotConfigured
from scrapy.extensions.reactorlag import ReactorLagMonitor
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.test import get_crawler
from tests.spiders import SimpleSpider
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from scrapy.crawler import Crawler


@pytest.fixture
def crawler() -> Crawler:
    crawler = get_crawler(SimpleSpider)
    crawler.spider = crawler._create_spider("spidey")
    return crawler


def test_disabled_with_zero_threshold() -> None:
    crawler = get_crawler(SimpleSpider, {"REACTORLAG_WARNING_THRESHOLD": 0})
    with pytest.raises(NotConfigured):
        build_from_crawler(ReactorLagMonitor, crawler)


@coroutine_test
async def test_no_warning_within_threshold(
    crawler: Crawler, caplog: pytest.LogCaptureFixture
) -> None:
    monitor = build_from_crawler(ReactorLagMonitor, crawler)
    assert crawler.spider
    monitor.spider_opened(crawler.spider)
    assert monitor._last_tick is not None
    monitor._last_tick -= monitor.threshold - 1
    monitor.tick(crawler.spider)
    monitor.spider_closed(crawler.spider)
    assert "unresponsive" not in caplog.text


@coroutine_test
async def test_warning_beyond_threshold(
    crawler: Crawler, caplog: pytest.LogCaptureFixture
) -> None:
    monitor = build_from_crawler(ReactorLagMonitor, crawler)
    assert crawler.spider
    monitor.spider_opened(crawler.spider)
    assert monitor._last_tick is not None
    monitor._last_tick -= monitor.threshold + 5
    monitor.tick(crawler.spider)
    monitor.spider_closed(crawler.spider)
    assert "unresponsive for 5." in caplog.text
