from scrapy import Spider
import logging
from scrapy.crawler import CrawlerProcess

class FailingSpider(Spider):
    name = "fail"

    def __init__(self,*args, **kwargs):
        print("parse hit")
        raise RuntimeError("simulated init error")

def test_crawl_error_logged_not_unhandled(caplog):
    process = CrawlerProcess({"TWISTED_REACTOR_ENABLED": True, "LOG_LEVEL": "DEBUG"})
    process.crawl(FailingSpider)
    
    with caplog.at_level(logging.ERROR):
        process.start()

    assert any("error during crawl" in r.message for r in caplog.records)

    assert not any("Unhandled error in Deferred" in r.message for r in caplog.records)
    assert process.bootstrap_failed