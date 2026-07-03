from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from warnings import warn

from scrapy import Request, Spider, signals
from scrapy.exceptions import NotConfigured, ScrapyDeprecationWarning
from scrapy.utils.httpobj import urlparse_cached

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.http import Response
    from scrapy.throttling import ThrottlingManagerProtocol


logger = logging.getLogger(__name__)


class AutoThrottle:
    def __init__(self, crawler: Crawler):
        self.crawler: Crawler = crawler
        if not crawler.settings.getbool("AUTOTHROTTLE_ENABLED"):
            raise NotConfigured

        warn(
            "You have set the AUTOTHROTTLE_ENABLED setting to True, however "
            "the AutoThrottle extension is deprecated; use throttling and "
            "backoff settings instead: "
            "https://docs.scrapy.org/en/latest/topics/throttling.html",
            ScrapyDeprecationWarning,
            stacklevel=2,
        )

        self.debug: bool = crawler.settings.getbool("AUTOTHROTTLE_DEBUG")
        self.target_concurrency: float = crawler.settings.getfloat(
            "AUTOTHROTTLE_TARGET_CONCURRENCY"
        )
        if self.target_concurrency <= 0.0:
            raise NotConfigured(
                f"AUTOTHROTTLE_TARGET_CONCURRENCY "
                f"({self.target_concurrency!r}) must be higher than 0."
            )
        self._started_scopes: set[str] = set()
        crawler.signals.connect(self._spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(
            self._response_downloaded, signal=signals.response_downloaded
        )

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls(crawler)

    def _spider_opened(self, spider: Spider) -> None:
        self.mindelay = self._min_delay(spider)
        self.maxdelay = self._max_delay(spider)
        self.startdelay = max(
            self.mindelay, self.crawler.settings.getfloat("AUTOTHROTTLE_START_DELAY")
        )

    def _min_delay(self, spider: Spider) -> float:
        s = self.crawler.settings
        return getattr(spider, "download_delay", s.getfloat("DOWNLOAD_DELAY"))

    def _max_delay(self, spider: Spider) -> float:
        return self.crawler.settings.getfloat("AUTOTHROTTLE_MAX_DELAY")

    def _response_downloaded(
        self, response: Response, request: Request, spider: Spider
    ) -> None:
        throttler = self.crawler.throttler
        assert throttler is not None
        latency = request.meta.get("download_latency")
        if (
            latency is None
            or request.meta.get("autothrottle_dont_adjust_delay", False) is True
        ):
            return

        scope_id = urlparse_cached(request).hostname or ""
        olddelay = self._scope_delay(throttler, scope_id)
        newdelay = self._adjust_delay(olddelay, latency, response)
        throttler.set_scope_delay(scope_id, newdelay)
        if self.debug:
            logger.info(
                "slot: %(slot)s | "
                "delay:%(delay)5d ms (%(delaydiff)+d) | "
                "latency:%(latency)5d ms | size:%(size)6d bytes",
                {
                    "slot": scope_id,
                    "delay": newdelay * 1000,
                    "delaydiff": (newdelay - olddelay) * 1000,
                    "latency": latency * 1000,
                    "size": len(response.body),
                },
                extra={"spider": spider},
            )

    def _scope_delay(
        self, throttler: ThrottlingManagerProtocol, scope_id: str
    ) -> float:
        """Return the current delay of *scope_id*, applying AUTOTHROTTLE_START_DELAY
        the first time the scope is seen."""
        delay = throttler.get_scope_delay(scope_id)
        if scope_id not in self._started_scopes:
            self._started_scopes.add(scope_id)
            delay = max(delay, self.startdelay)
        return delay

    def _adjust_delay(
        self, olddelay: float, latency: float, response: Response
    ) -> float:
        """Return the new delay given the current *olddelay* and the observed
        *latency*."""

        # If a server needs `latency` seconds to respond then
        # we should send a request each `latency/N` seconds
        # to have N requests processed in parallel
        target_delay = latency / self.target_concurrency

        # Adjust the delay to make it closer to target_delay
        new_delay = (olddelay + target_delay) / 2.0

        # If target delay is bigger than old delay, then use it instead of mean.
        # It works better with problematic sites.
        new_delay = max(target_delay, new_delay)

        # Make sure self.mindelay <= new_delay <= self.maxdelay
        new_delay = min(max(self.mindelay, new_delay), self.maxdelay)

        # Dont adjust delay if response status != 200 and new delay is smaller
        # than old one, as error pages (and redirections) are usually small and
        # so tend to reduce latency, thus provoking a positive feedback by
        # reducing delay instead of increase.
        if response.status != 200 and new_delay <= olddelay:
            return olddelay

        return new_delay
