from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

import pytest

from scrapy.exceptions import NotConfigured
from scrapy.extensions.spiderstate import SpiderState
from scrapy.spiders import Spider
from scrapy.utils.test import get_crawler

if TYPE_CHECKING:
    from pathlib import Path


def test_store_load(tmp_path: Path) -> None:
    jobdir = str(tmp_path)

    spider = Spider(name="default")
    dt = datetime.now(tz=timezone.utc)

    ss = SpiderState(jobdir)
    ss.spider_opened(spider)
    assert hasattr(spider, "state")
    spider.state["one"] = 1
    spider.state["dt"] = dt
    ss.spider_closed(spider)

    spider2 = Spider(name="default")
    ss2 = SpiderState(jobdir)
    ss2.spider_opened(spider2)
    assert hasattr(spider2, "state")
    assert spider2.state == {"one": 1, "dt": dt}
    ss2.spider_closed(spider2)


def test_state_attribute() -> None:
    # state attribute must be present if jobdir is not set, to provide a
    # consistent interface
    spider = Spider(name="default")
    ss = SpiderState()
    ss.spider_opened(spider)
    assert hasattr(spider, "state")
    assert spider.state == {}
    ss.spider_closed(spider)


def test_not_configured() -> None:
    crawler = get_crawler(Spider)
    with pytest.raises(NotConfigured):
        SpiderState.from_crawler(crawler)
