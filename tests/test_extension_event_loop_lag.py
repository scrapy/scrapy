from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import pytest

from scrapy import Spider
from scrapy.exceptions import NotConfigured
from scrapy.extensions.event_loop_lag import EventLoopLagMonitor
from scrapy.utils.asyncio import sleep
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.test import get_crawler
from tests.utils.decorators import coroutine_test

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class _BlockingSpider(Spider):
    name = "blocking"

    def __init__(self, block: float, **kwargs: Any):
        super().__init__(**kwargs)
        self.block = block

    async def start(self) -> AsyncIterator[Any]:
        await sleep(0.3)
        time.sleep(self.block)  # noqa: ASYNC251
        await sleep(0.3)
        return
        yield


def test_disabled_with_zero_threshold() -> None:
    crawler = get_crawler(Spider, {"EVENT_LOOP_LAG_THRESHOLD": 0})
    with pytest.raises(NotConfigured):
        build_from_crawler(EventLoopLagMonitor, crawler)


@pytest.mark.parametrize(("block", "warns"), [(0.2, False), (0.8, True)])
@coroutine_test
async def test_warning(
    block: float, warns: bool, caplog: pytest.LogCaptureFixture
) -> None:
    crawler = get_crawler(_BlockingSpider, {"EVENT_LOOP_LAG_THRESHOLD": 0.5})
    await crawler.crawl_async(block=block)
    messages = [
        r.getMessage()
        for r in caplog.records
        if "event loop was blocked" in r.getMessage()
    ]
    if warns:
        assert len(messages) == 1
        lag = float(messages[0].split(" for ")[1].split("s,")[0])
        assert 0.6 < lag < 0.9
    else:
        assert not messages
