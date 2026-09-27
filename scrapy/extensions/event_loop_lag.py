from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from scrapy import Spider, signals
from scrapy.exceptions import NotConfigured
from scrapy.utils.asyncio import AsyncioLoopingCall, create_looping_call

if TYPE_CHECKING:
    from twisted.internet.task import LoopingCall

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler


logger = logging.getLogger(__name__)

_MAX_INTERVAL = 0.1


class EventLoopLagMonitor:
    """Log a warning when the event loop is blocked for longer than
    :setting:`EVENT_LOOP_LAG_THRESHOLD` seconds, which happens when CPU-bound
    code in a callback delays every other pending callback and I/O operation
    for as long as it runs. Move such code to a thread with
    :func:`scrapy.utils.asyncio.run_in_thread` to avoid it.

    To find out which callback is blocking the event loop, use the
    :ref:`asyncio debug mode <asyncio-debug-mode>`, which logs callbacks that
    take longer than :attr:`asyncio.loop.slow_callback_duration`.
    """

    def __init__(self, threshold: float):
        self._threshold: float = threshold
        self._interval: float = min(threshold, _MAX_INTERVAL)
        self._task: AsyncioLoopingCall[[Spider], None] | LoopingCall | None = None
        self._last_tick: float | None = None

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        threshold: float = crawler.settings.getfloat("EVENT_LOOP_LAG_THRESHOLD")
        if not threshold:
            raise NotConfigured
        o = cls(threshold)
        crawler.signals.connect(o.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(o.spider_closed, signal=signals.spider_closed)
        return o

    def spider_opened(self, spider: Spider) -> None:
        self._last_tick = time.monotonic()
        self._task = create_looping_call(self._tick, spider)
        self._task.start(self._interval, now=False)

    def _tick(self, spider: Spider) -> None:
        now = time.monotonic()
        assert self._last_tick is not None
        lag = now - self._last_tick - self._interval
        self._last_tick = now
        if lag > self._threshold:
            logger.warning(
                f"The event loop was blocked for {lag:.3f}s, probably by "
                f"CPU-bound code running in a callback. Consider moving it to "
                f"a thread with run_in_thread().",
                extra={"spider": spider},
            )

    def spider_closed(self, spider: Spider) -> None:
        if self._task and self._task.running:
            self._task.stop()
