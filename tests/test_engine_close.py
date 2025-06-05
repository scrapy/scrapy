import pytest
from scrapy.core.engine import ExecutionEngine

class DummyCrawler:
    settings = {"DOWNLOADER": "scrapy.core.downloader.Downloader", "SCHEDULER": "scrapy.core.scheduler.Scheduler"}
    signals = logformatter = stats = None

def dummy_spider_closed_callback(spider):
    return None

def test_engine_close_without_downloader():
    """Should not raise if downloader was never set."""
    engine = ExecutionEngine.__new__(ExecutionEngine)  # bypass __init__
    engine.running = False
    engine.spider = None
    engine.close()
