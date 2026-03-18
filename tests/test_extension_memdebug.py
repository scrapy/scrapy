import gc
from unittest.mock import MagicMock

import pytest

from scrapy import signals
from scrapy.exceptions import NotConfigured
from scrapy.extensions import memdebug
from scrapy.signalmanager import SignalManager
from scrapy.statscollectors import StatsCollector
from scrapy.utils.spider import DefaultSpider
from scrapy.utils.trackref import live_refs


@pytest.fixture
def dummy_stats():
    class DummyStats(StatsCollector):
        def __init__(self):
            # pylint: disable=super-init-not-called
            self._stats = {"global_item_scraped_count": 42}

        def get_stats(self):
            return {"item_scraped_count": 10, **self._stats}

    return DummyStats()


def test_from_crawler_without_memdebug_enabled_raises_notconfigured():
    crawler = MagicMock()
    crawler.settings.getbool.return_value = ""
    crawler.stats = MagicMock()

    with pytest.raises(NotConfigured):
        memdebug.MemoryDebugger.from_crawler(crawler)


def test_from_crawler_connects_spider_closed_signal(dummy_stats):
    crawler = MagicMock()
    crawler.settings.getlist.return_value = ["MEMDEBUG_ENABLED"]
    crawler.stats = dummy_stats
    crawler.signals = SignalManager(crawler)

    connected = crawler.signals.send_catch_log(
        signals.spider_closed, spider=DefaultSpider(name="dummy")
    )
    assert connected is not None


def test_spider_closed_collects_info_about_objects_uncollected_by_garbage(dummy_stats):
    ext = memdebug.MemoryDebugger(dummy_stats)

    spider = DefaultSpider(name="dummy")
    ext.spider_closed(spider, reason="finished")

    gc.collect()
    assert ext.stats.get_value("memdebug/gc_garbage_count") == len(gc.garbage)


def test_spider_closed_collects_info_about_objects_left_alive(dummy_stats):
    ext = memdebug.MemoryDebugger(dummy_stats)

    spider = DefaultSpider(name="dummy")
    ext.spider_closed(spider, reason="finished")

    gc.collect()
    for cls, wdict in live_refs.items():
        if not wdict:
            continue
        assert ext.stats.get_value(f"memdebug/live_refs/{cls.__name__}") == len(wdict)
