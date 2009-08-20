"""
Scrapy core signals

These signals are documented in docs/topics/signals.rst. Please don't add new
signals here without documenting them there.
"""

engine_started = object()
engine_stopped = object()
domain_opened = object()
domain_idle = object()
domain_closed = object()
request_received = object()
request_uploaded = object()
response_received = object()
response_downloaded = object()
item_scraped = object()
item_passed = object()
item_dropped = object()

# XXX: deprecated signals (will be removed in Scrapy 0.8)
domain_open = object()

