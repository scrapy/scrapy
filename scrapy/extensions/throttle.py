from __future__ import annotations

import logging
import warnings
from typing import TYPE_CHECKING

from scrapy import Request, Spider, signals
from scrapy.exceptions import NotConfigured, ScrapyDeprecationWarning

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.core.downloader import Slot
    from scrapy.crawler import Crawler
    from scrapy.http import Response


logger = logging.getLogger(__name__)


class AutoThrottle:
    def __init__(self, crawler: Crawler):
        self.crawler: Crawler = crawler
        if not crawler.settings.getbool("AUTOTHROTTLE_ENABLED"):
            raise NotConfigured

        self.debug: bool = crawler.settings.getbool("AUTOTHROTTLE_DEBUG")
        self.target_concurrency: float = crawler.settings.getfloat(
            "AUTOTHROTTLE_TARGET_CONCURRENCY"
        )
        if self.target_concurrency <= 0.0:
            raise NotConfigured(
                f"AUTOTHROTTLE_TARGET_CONCURRENCY "
                f"({self.target_concurrency!r}) must be higher than 0."
            )
        crawler.signals.connect(self._spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(
            self._response_downloaded, signal=signals.response_downloaded
        )

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls(crawler)

    def _spider_opened(self, spider: Spider) -> None:
        self.mindelay = self._min_delay(spider)
        self.maxdelay = self._max_delay()
        spider.download_delay = self._start_delay()  # type: ignore[attr-defined]

    def _min_delay(self, spider: Spider | None = None) -> float:
        if spider is not None:
            warnings.warn(
                "Passing a 'spider' argument to AutoThrottle._min_delay is deprecated.",
                category=ScrapyDeprecationWarning,
                stacklevel=2,
            )
            return getattr(
                spider,
                "download_delay",
                self.crawler.settings.getfloat("DOWNLOAD_DELAY"),
            )
        return getattr(
            self.crawler.spider,
            "download_delay",
            self.crawler.settings.getfloat("DOWNLOAD_DELAY"),
        )

    def _max_delay(self) -> float:
        return self.crawler.settings.getfloat("AUTOTHROTTLE_MAX_DELAY")

    def _start_delay(self) -> float:
        return max(
            self.mindelay, self.crawler.settings.getfloat("AUTOTHROTTLE_START_DELAY")
        )

    def _response_downloaded(
        self, response: Response, request: Request, spider: Spider | None = None
    ) -> None:
        if spider is not None:
            warnings.warn(
                "Passing a 'spider' argument to AutoThrottle._response_downloaded is deprecated.",
                category=ScrapyDeprecationWarning,
                stacklevel=2,
            )
        key, slot = self._get_slot(request)
        latency = request.meta.get("download_latency")
        if (
            latency is None
            or slot is None
            or request.meta.get("autothrottle_dont_adjust_delay", False) is True
        ):
            return

        olddelay = slot.delay
        self._adjust_delay(slot, latency, response)
        if self.debug:
            diff = slot.delay - olddelay
            size = len(response.body)
            conc = len(slot.transferring)
            logger.info(
                "slot: %(slot)s | conc:%(concurrency)2d | "
                "delay:%(delay)5d ms (%(delaydiff)+d) | "
                "latency:%(latency)5d ms | size:%(size)6d bytes",
                {
                    "slot": key,
                    "concurrency": conc,
                    "delay": slot.delay * 1000,
                    "delaydiff": diff * 1000,
                    "latency": latency * 1000,
                    "size": size,
                },
                extra={"spider": self.crawler.spider},
            )

    def _get_slot(self, request: Request) -> tuple[str | None, Slot | None]:
        key: str | None = request.meta.get("download_slot")
        if key is None:
            return None, None
        assert self.crawler.engine
        return key, self.crawler.engine.downloader.slots.get(key)

    def _adjust_delay(self, slot: Slot, latency: float, response: Response) -> None:
        """Define delay adjustment policy"""

        # If a server needs `latency` seconds to respond then
        # we should send a request each `latency/N` seconds
        # to have N requests processed in parallel
        target_delay = latency / self.target_concurrency

        # Adjust the delay to make it closer to target_delay
        new_delay = (slot.delay + target_delay) / 2.0

        # If target delay is bigger than old delay, then use it instead of mean.
        # It works better with problematic sites.
        new_delay = max(target_delay, new_delay)

        # Make sure self.mindelay <= new_delay <= self.max_delay
        new_delay = min(max(self.mindelay, new_delay), self.maxdelay)

        # Dont adjust delay if response status != 200 and new delay is smaller
        # than old one, as error pages (and redirections) are usually small and
        # so tend to reduce latency, thus provoking a positive feedback by
        # reducing delay instead of increase.
        if response.status != 200 and new_delay <= slot.delay:
            return

        slot.delay = new_delay
