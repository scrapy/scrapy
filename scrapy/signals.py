"""
Scrapy signals

These signals are documented in docs/topics/signals.rst. Please don't add new
signals here without documenting them there.
"""

from blinker import NamedSignal as _NamedSignal

engine_started = _NamedSignal("engine_started")
engine_stopped = _NamedSignal("engine_stopped")
scheduler_empty = _NamedSignal("scheduler_empty")
spider_opened = _NamedSignal("spider_opened")
spider_idle = _NamedSignal("spider_idle")
spider_closed = _NamedSignal("spider_closed")
spider_error = _NamedSignal("spider_error")
memusage_warning_reached = _NamedSignal("memusage_warning_reached")
request_scheduled = _NamedSignal("request_scheduled")
request_dropped = _NamedSignal("request_dropped")
request_reached_downloader = _NamedSignal("request_reached_downloader")
request_left_downloader = _NamedSignal("request_left_downloader")
response_received = _NamedSignal("response_received")
response_downloaded = _NamedSignal("response_downloaded")
headers_received = _NamedSignal("headers_received")
bytes_received = _NamedSignal("bytes_received")
robots_parsed = _NamedSignal("robots_parsed")
item_scraped = _NamedSignal("item_scraped")
item_dropped = _NamedSignal("item_dropped")
item_error = _NamedSignal("item_error")
feed_slot_closed = _NamedSignal("feed_slot_closed")
feed_exporter_closed = _NamedSignal("feed_exporter_closed")

#: Arguments that each signal sends, used to catch handlers that declare an
#: argument their signal never sends. ``signal`` and ``sender`` are omitted
#: because every signal sends them.
_signal_args: dict[object, frozenset[str]] = {
    engine_started: frozenset(),
    engine_stopped: frozenset(),
    scheduler_empty: frozenset(),
    spider_opened: frozenset({"spider"}),
    spider_idle: frozenset({"spider"}),
    spider_closed: frozenset({"spider", "reason"}),
    spider_error: frozenset({"failure", "response", "spider"}),
    memusage_warning_reached: frozenset(),
    request_scheduled: frozenset({"request", "spider"}),
    request_dropped: frozenset({"request", "spider"}),
    request_reached_downloader: frozenset({"request", "spider"}),
    request_left_downloader: frozenset({"request", "spider"}),
    response_received: frozenset({"response", "request", "spider"}),
    response_downloaded: frozenset({"response", "request", "spider"}),
    headers_received: frozenset({"headers", "body_length", "request", "spider"}),
    bytes_received: frozenset({"data", "request", "spider"}),
    robots_parsed: frozenset({"robotparser", "request"}),
    item_scraped: frozenset({"item", "response", "spider"}),
    item_dropped: frozenset({"item", "response", "spider", "exception"}),
    item_error: frozenset({"item", "response", "spider", "failure"}),
    feed_slot_closed: frozenset({"slot"}),
    feed_exporter_closed: frozenset(),
}
