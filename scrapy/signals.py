"""
Scrapy signals

These signals are documented in docs/topics/signals.rst. Please don't add new
signals here without documenting them there.
"""

engine_started = object()
engine_stopped = object()

#: Sent when the :ref:`engine <engine>` is waiting for :meth:`Spider.start
#: <scrapy.Spider.start>` to either finish or yield its next start item or
#: request, and is otherwise idle (:signal:`spider_idle`).
#:
#: Can be used, for example, for :ref:`idle start request scheduling
#: <start-requests-idle>`.
spider_start_blocking = object()

#: Sent whenever the :ref:`engine <engine>` asks for a pending request from the
#: :ref:`scheduler <topics-scheduler>` (i.e. calls its
#: :meth:`~scrapy.core.scheduler.BaseScheduler.next_request` method) and the
#: scheduler returns none.
#:
#: Can be used, for example, for :ref:`lazy start request scheduling
#: <start-requests-lazy>`.
scheduler_empty = object()

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
