# tests/test_memusage.py

import sys

import pytest

from scrapy.crawler import Crawler
from scrapy.exceptions import NotConfigured
from scrapy.extensions.memusage import MemoryUsage
from scrapy.settings import Settings
from scrapy.spiders import Spider


class DummySpider(Spider):
    name = "dummy"


@pytest.mark.skipif(
    sys.platform.startswith("win"), reason="memusage not supported on Windows"
)
def test_memusage_extension_initializes():
    """Test that the MemoryUsage extension initializes correctly on supported platforms."""
    settings = Settings(
        {
            "MEMUSAGE_ENABLED": True,
            "MEMUSAGE_LIMIT_MB": 2048,
        }
    )

    crawler = Crawler(DummySpider, settings)
    try:
        ext = MemoryUsage.from_crawler(crawler)
    except NotConfigured:
        pytest.skip("MemoryUsage extension not configured for this platform")

    assert ext.limit is not None
    assert isinstance(ext.limit, int)
    assert ext.warn_on_limit_reached is True
