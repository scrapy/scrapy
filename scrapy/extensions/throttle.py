import logging

from scrapy import signals
from scrapy.exceptions import NotConfigured

logger = logging.getLogger(__name__)


class AutoThrottle:
    def __init__(self, crawler):
        self.crawler = crawler
        if not crawler.settings.getbool("AUTOTHROTTLE_ENABLED"):
            raise NotConfigured

        self.debug = crawler.settings.getbool("AUTOTHROTTLE_DEBUG")
        self.target_concurrency = crawler.settings.getfloat(
            "AUTOTHROTTLE_TARGET_CONCURRENCY"
        )
        crawler.signals.connect(self._spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(
            self._response_downloaded, signal=signals.response_downloaded
        )

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def _spider_opened(self, spider):
        self.mindelay = self._min_delay(spider)
        self.maxdelay = self._max_delay(spider)
        spider.download_delay = self._start_delay(spider)

    def _min_delay(self, spider):
        s = self.crawler.settings
        return getattr(spider, "download_delay", s.getfloat("DOWNLOAD_DELAY"))

    def _max_delay(self, spider):
        return self.crawler.settings.getfloat("AUTOTHROTTLE_MAX_DELAY")

    def _start_delay(self, spider):
        return max(
            self.mindelay, self.crawler.settings.getfloat("AUTOTHROTTLE_START_DELAY")
        )

    def _response_downloaded(self, response, request, spider):
        key, slot = self._get_slot(request, spider)
        latency = request.meta.get("download_latency")
        if latency is None or slot is None:
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
                extra={"spider": spider},
            )

    def _get_slot(self, request, spider):
        key = request.meta.get("download_slot")
        return key, self.crawler.engine.downloader.slots.get(key)

    def _adjust_delay(self, slot, latency, response):
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
