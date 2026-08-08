"""
Scrapy signals

These signals are documented in docs/topics/signals.rst. Please don't add new
signals here without documenting them there.
"""

engine_started = object()
engine_stopped = object()
scheduler_empty = object()
spider_opened = object()
spider_idle = object()
spider_closed = object()
spider_error = object()
memusage_warning_reached = object()
request_scheduled = object()
request_dropped = object()
request_reached_downloader = object()
request_left_downloader = object()
response_received = object()
response_downloaded = object()
headers_received = object()
bytes_received = object()
robots_parsed = object()
item_scraped = object()
item_dropped = object()
item_error = object()
feed_slot_closed = object()
feed_exporter_closed = object()

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
