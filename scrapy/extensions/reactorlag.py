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


class ReactorLagMonitor:
    """Log a warning when the reactor loop takes longer than
    :setting:`REACTORLAG_WARNING_THRESHOLD` seconds to run an iteration,
    which happens when CPU-bound code in a callback blocks every other
    pending callback and I/O operation for as long as it runs. Move such
    code to a thread with :func:`scrapy.utils.asyncio.run_in_thread` to
    avoid it.
    """

    def __init__(self, threshold: float):
        self.threshold: float = threshold
        self.task: AsyncioLoopingCall | LoopingCall | None = None
        self._last_tick: float | None = None

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        threshold: float = crawler.settings.getfloat("REACTORLAG_WARNING_THRESHOLD")
        if not threshold:
            raise NotConfigured
        o = cls(threshold)
        crawler.signals.connect(o.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(o.spider_closed, signal=signals.spider_closed)
        return o

    def spider_opened(self, spider: Spider) -> None:
        self._last_tick = time.monotonic()
        self.task = create_looping_call(self.tick, spider)
        self.task.start(self.threshold, now=False)

    def tick(self, spider: Spider) -> None:
        now = time.monotonic()
        assert self._last_tick is not None
        lag = now - self._last_tick - self.threshold
        self._last_tick = now
        if lag > 0:
            logger.warning(
                f"The reactor loop was unresponsive for {lag:.3f}s, "
                f"probably due to CPU-bound code running in a callback. "
                f"Consider moving it to a thread with run_in_thread().",
                extra={"spider": spider},
            )

    def spider_closed(self, spider: Spider) -> None:
        if self.task and self.task.running:
            self.task.stop()
