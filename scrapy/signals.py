"""
Scrapy signals

These signals are documented in docs/topics/signals.rst. Please don't add new
signals here without documenting them there.
"""
from scrapy.dispatch import Signal

engine_started = Signal()
engine_stopped = Signal()
spider_opened = Signal()
spider_idle = Signal()
spider_closed = Signal()
spider_error = Signal()
request_scheduled = Signal()
request_dropped = Signal()
response_received = Signal()
response_downloaded = Signal()
item_scraped = Signal()
item_dropped = Signal()

# for backwards compatibility
stats_spider_opened = spider_opened
stats_spider_closing = spider_closed
stats_spider_closed = spider_closed

item_passed = item_scraped

request_received = request_scheduled
