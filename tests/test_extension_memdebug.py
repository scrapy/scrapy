from __future__ import annotations

import gc

import pytest

from scrapy.exceptions import NotConfigured
from scrapy.extensions.memdebug import MemoryDebugger
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler
from scrapy.utils.trackref import object_ref
from tests.utils.decorators import coroutine_test


def test_disabled_by_default() -> None:
    with pytest.raises(NotConfigured):
        MemoryDebugger.from_crawler(get_crawler())


def test_spider_closed_sets_stats() -> None:
    crawler = get_crawler(settings_dict={"MEMDEBUG_ENABLED": True})
    ext = MemoryDebugger.from_crawler(crawler)

    class TrackedObject(object_ref):
        pass

    class CollectedObject(object_ref):
        pass

    tracked = [TrackedObject(), TrackedObject()]
    CollectedObject()

    ext.spider_closed(DefaultSpider(), "finished")

    assert crawler.stats
    assert crawler.stats.get_value("memdebug/gc_garbage_count") == len(gc.garbage)
    assert crawler.stats.get_value("memdebug/live_refs/TrackedObject") == len(tracked)
    assert crawler.stats.get_value("memdebug/live_refs/CollectedObject") is None


@coroutine_test
async def test_crawl_sets_stats() -> None:
    crawler = get_crawler(DefaultSpider, settings_dict={"MEMDEBUG_ENABLED": True})
    await crawler.crawl_async()
    assert crawler.stats
    assert crawler.stats.get_value("memdebug/gc_garbage_count") is not None
    assert crawler.stats.get_value("memdebug/live_refs/DefaultSpider") == 1
