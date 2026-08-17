from __future__ import annotations

import gc

import pytest

from scrapy.exceptions import NotConfigured
from scrapy.extensions.memdebug import MemoryDebugger
from scrapy.utils.misc import build_from_crawler
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.test import get_crawler
from scrapy.utils.trackref import object_ref
from tests.utils.decorators import coroutine_test


def test_disabled_by_default() -> None:
    with pytest.raises(NotConfigured):
        build_from_crawler(MemoryDebugger, get_crawler())


def test_spider_closed_sets_stats() -> None:
    crawler = get_crawler(settings_dict={"MEMDEBUG_ENABLED": True})
    ext = build_from_crawler(MemoryDebugger, crawler)

    class TrackedObject(object_ref):
        pass

    class CollectedObject(object_ref):
        pass

    tracked = [TrackedObject(), TrackedObject()]
    CollectedObject()

    ext.spider_closed(DefaultSpider.from_crawler(crawler), "finished")

    assert crawler.stats.get_value("memdebug/gc_garbage_count") == len(gc.garbage)
    assert crawler.stats.get_value("memdebug/live_refs/TrackedObject") == len(tracked)
    assert crawler.stats.get_value("memdebug/live_refs/CollectedObject") is None


@coroutine_test
async def test_crawl_sets_stats() -> None:
    # unique class so that other tests don't pollute live_refs
    class MemDebugSpider(DefaultSpider):
        pass

    crawler = get_crawler(MemDebugSpider, settings_dict={"MEMDEBUG_ENABLED": True})
    await crawler.crawl_async()
    assert crawler.stats.get_value("memdebug/gc_garbage_count") is not None
    assert crawler.stats.get_value("memdebug/live_refs/MemDebugSpider") == 1
