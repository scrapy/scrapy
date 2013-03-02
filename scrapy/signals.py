"""
Scrapy signals

These signals are documented in docs/topics/signals.rst. Please don't add new
signals here without documenting them there.
"""

class Signal(object):
    def __init__(self, name):
        self.name = name

engine_started = Signal("engine_started")
engine_stopped = Signal("engine_stopped")
spider_opened = Signal("spider_opened")
spider_idle = Signal("spider_idle")
spider_closed = Signal("spider_closed")
spider_error = Signal("spider_error")
request_received = Signal("request_received")
response_received = Signal("response_received")
response_downloaded = Signal("response_downloaded")
item_scraped = Signal("item_scraped")
item_dropped = Signal("item_dropped")

stats_spider_opened = spider_opened
stats_spider_closing = spider_closed
stats_spider_closed = spider_closed

item_passed = item_scraped # for backwards compatibility
