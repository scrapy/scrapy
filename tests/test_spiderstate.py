from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

import pytest

from scrapy import signals
from scrapy.exceptions import NotConfigured, ScrapyDeprecationWarning
from scrapy.extensions.spiderstate import SpiderState
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from pathlib import Path


def test_deprecated_methods(tmp_path: Path) -> None:
    crawler = get_crawler(Spider, {"JOBDIR": str(tmp_path)})
    ss = SpiderState.from_crawler(crawler)
    spider = Spider(name="default")
    with pytest.warns(ScrapyDeprecationWarning, match="spider_opened"):
        ss.spider_opened(spider)
    with pytest.warns(ScrapyDeprecationWarning, match="spider_closed"):
        ss.spider_closed(spider)


def test_not_configured() -> None:
    crawler = get_crawler(Spider)
    with pytest.raises(NotConfigured):
        SpiderState.from_crawler(crawler)


@coroutine_test
async def test_store_load(tmp_path: Path) -> None:
    jobdir = str(tmp_path)
    spider = Spider(name="default")
    dt = datetime.now(tz=timezone.utc)

    crawler = get_crawler(Spider, {"JOBDIR": jobdir})
    ss = SpiderState.from_crawler(crawler)
    await ss._spider_opened(spider)
    assert hasattr(spider, "state")
    spider.state["one"] = 1
    spider.state["dt"] = dt
    await ss._spider_closed(spider)

    spider2 = Spider(name="default")
    crawler2 = get_crawler(Spider, {"JOBDIR": jobdir})
    ss2 = SpiderState.from_crawler(crawler2)
    await ss2._spider_opened(spider2)
    assert hasattr(spider2, "state")
    assert spider2.state == {"one": 1, "dt": dt}
    await ss2._spider_closed(spider2)


@coroutine_test
async def test_spider_state_loaded_signal_fires(tmp_path: Path) -> None:
    crawler = get_crawler(Spider, {"JOBDIR": str(tmp_path)})
    ss = SpiderState.from_crawler(crawler)

    received: list[dict] = []

    def on_loaded(state: dict) -> None:
        received.append(dict(state))

    crawler.signals.connect(on_loaded, signal=signals.spider_state_loaded, weak=False)

    spider = Spider(name="default")
    await ss._spider_opened(spider)

    assert received == [{}]
    assert spider.state == {}


@coroutine_test
async def test_spider_state_saving_signal_fires(tmp_path: Path) -> None:
    crawler = get_crawler(Spider, {"JOBDIR": str(tmp_path)})
    ss = SpiderState.from_crawler(crawler)

    spider = Spider(name="default")
    await ss._spider_opened(spider)
    spider.state["key"] = "value"

    saving_calls: list[dict] = []

    def on_saving(state: dict) -> None:
        saving_calls.append(dict(state))

    crawler.signals.connect(on_saving, signal=signals.spider_state_saving, weak=False)
    await ss._spider_closed(spider)

    assert saving_calls == [{"key": "value"}]
