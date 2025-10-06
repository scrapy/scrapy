# tests/test_extension_memusage.py

from scrapy.crawler import Crawler
from scrapy.extensions.memusage import MemoryUsage
from scrapy.settings import Settings
from scrapy.spiders import Spider


class DummySpider(Spider):
    name = "dummy_spider"


def test_memusage_extension_initializes_correctly():
    """Ensure the MemoryUsage extension loads with default settings."""
    settings = Settings(
        {
            "MEMUSAGE_ENABLED": True,
            "MEMUSAGE_LIMIT_MB": 256,
            "MEMUSAGE_NOTIFY_MAIL": [],
        }
    )
    crawler = Crawler(DummySpider, settings)
    ext = MemoryUsage.from_crawler(crawler)

    assert isinstance(ext.limit, int)
    assert ext.limit == 256
    assert ext.warn_on_limit_reached is True
    assert callable(ext.update)
