"""
Scrapy signals

These signals are documented in docs/topics/signals.rst. Please don't add new
signals here without documenting them there.
"""


class _Signal:
    def __init__(self, name: str):
        self.name = name

    def __repr__(self) -> str:
        return f"scrapy.signals.{self.name}"


engine_started = _Signal("engine_started")
engine_stopped = _Signal("engine_stopped")
scheduler_empty = _Signal("scheduler_empty")
spider_opened = _Signal("spider_opened")
spider_idle = _Signal("spider_idle")
spider_closed = _Signal("spider_closed")
spider_error = _Signal("spider_error")
memusage_warning_reached = _Signal("memusage_warning_reached")
request_scheduled = _Signal("request_scheduled")
request_dropped = _Signal("request_dropped")
request_reached_downloader = _Signal("request_reached_downloader")
request_left_downloader = _Signal("request_left_downloader")
response_received = _Signal("response_received")
response_downloaded = _Signal("response_downloaded")
headers_received = _Signal("headers_received")
bytes_received = _Signal("bytes_received")
robots_parsed = _Signal("robots_parsed")
item_scraped = _Signal("item_scraped")
item_dropped = _Signal("item_dropped")
item_error = _Signal("item_error")
feed_slot_closed = _Signal("feed_slot_closed")
feed_exporter_closed = _Signal("feed_exporter_closed")
feed_slots_initialized = _Signal("feed_slots_initialized")
spider_state_loaded = _Signal("spider_state_loaded")
spider_state_saving = _Signal("spider_state_saving")

_signal_args: dict[object, frozenset[str]] = {
    engine_started: frozenset(),
    engine_stopped: frozenset(),
    scheduler_empty: frozenset(),
    spider_opened: frozenset({"spider"}),
    spider_idle: frozenset({"spider"}),
    spider_closed: frozenset({"spider", "reason", "error"}),
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
    robots_parsed: frozenset({"robotparser", "request", "response"}),
    item_scraped: frozenset({"item", "response", "spider"}),
    item_dropped: frozenset({"item", "response", "spider", "exception"}),
    item_error: frozenset({"item", "response", "spider", "failure"}),
    feed_slot_closed: frozenset({"slot"}),
    feed_exporter_closed: frozenset(),
    feed_slots_initialized: frozenset({"slots"}),
    spider_state_loaded: frozenset({"state"}),
    spider_state_saving: frozenset({"state"}),
}
"""Arguments that each signal sends, used to catch handlers that declare an
argument their signal never sends. ``signal`` and ``sender`` are omitted
because every signal sends them.
"""
