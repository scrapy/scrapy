import pytest
from scrapy.http import Request
from scrapy_priority_scheduler.scheduler import PriorityScheduler
from scrapy.crawler import Crawler
from scrapy.spiders import Spider
from scrapy.settings import Settings

@pytest.fixture
def crawler():
    settings = Settings({
        "CONCURRENT_REQUESTS": 16,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 8,
        "PRIORITY_SCHEDULER_MULTIPLIER": 2.0,
    })
    spider = Spider(name="test_spider")
    crawler = Crawler(spider, settings)
    return crawler

@pytest.fixture
def scheduler(crawler):
    return PriorityScheduler(crawler)

def test_enqueue_and_dequeue_branch_priority(scheduler, crawler):
    scheduler.open(crawler.spider)
    
    # Enqueue branch and leaf requests
    branch_request = Request("https://example.com/1", meta={"priority_type": "branch"})
    leaf_request = Request("https://example.com/2", meta={"priority_type": "leaf"})
    
    scheduler.enqueue_request(branch_request)
    scheduler.enqueue_request(leaf_request)
    
    # First request should be branch
    next_req = scheduler.next_request()
    assert next_req is branch_request, "Expected branch request to be dequeued first"
    
    # Enqueue another leaf request
    scheduler.enqueue_request(leaf_request)
    
    # Next request should be leaf (since branch queue is empty)
    next_req = scheduler.next_request()
    assert next_req is leaf_request, "Expected leaf request to be dequeued when branch queue is empty"
    
    scheduler.close("test")

def test_warning_for_unmarked_request(scheduler, crawler, caplog):
    scheduler.open(crawler.spider)
    request = Request("https://example.com/unmarked")
    with caplog.at_level("WARNING"):
        scheduler.enqueue_request(request)
    assert "has no priority_type set" in caplog.text
    scheduler.close("test")
