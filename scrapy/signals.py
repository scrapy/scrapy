"""
Scrapy signals

These signals are documented in docs/topics/signals.rst. Please don't add new
signals here without documenting them there.
"""

engine_started = object()
engine_stopped = object()
spider_opened = object()
spider_idle = object()
spider_closed = object()
spider_error = object()
request_scheduled = object()
request_dropped = object()
request_reached_downloader = object()
request_left_downloader = object()
response_received = object()
response_downloaded = object()
headers_received = object()
bytes_received = object()
item_scraped = object()
item_dropped = object()
item_error = object()
feed_slot_closed = object()
feed_exporter_closed = object()

# for backward compatibility
stats_spider_opened = spider_opened
stats_spider_closing = spider_closed
stats_spider_closed = spider_closed

item_passed = item_scraped

request_received = request_scheduled
