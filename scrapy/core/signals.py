"""
Scrapy core signals

These signals are documented in docs/topics/signals.rst. Please don't add new
signals here without documenting them there.
"""

engine_started = object()
engine_stopped = object()
spider_opened = object()
spider_idle = object()
spider_closed = object()
request_received = object()
request_uploaded = object()
response_received = object()
response_downloaded = object()
item_scraped = object()
item_passed = object()
item_dropped = object()
