import logging
from scrapy.exceptions import NotConfigured
from scrapy import signals


class AutoThrottle(object):

    def __init__(self, crawler):
        self.crawler = crawler
        if not crawler.settings.getbool('AUTOTHROTTLE_ENABLED'):
            raise NotConfigured

        self.debug = crawler.settings.getbool("AUTOTHROTTLE_DEBUG")
        crawler.signals.connect(self._spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(self._response_downloaded, signal=signals.response_downloaded)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def _spider_opened(self, spider):
        self.mindelay = self._min_delay(spider)
        self.maxdelay = self._max_delay(spider)
        spider.download_delay = self._start_delay(spider)

    def _min_delay(self, spider):
        s = self.crawler.settings
        return getattr(spider, 'download_delay', 0.0) or \
            s.getfloat('AUTOTHROTTLE_MIN_DOWNLOAD_DELAY') or \
            s.getfloat('DOWNLOAD_DELAY')

    def _max_delay(self, spider):
        return self.crawler.settings.getfloat('AUTOTHROTTLE_MAX_DELAY', 60.0)

    def _start_delay(self, spider):
        return max(self.mindelay, self.crawler.settings.getfloat('AUTOTHROTTLE_START_DELAY', 5.0))

    def _response_downloaded(self, response, request, spider):
        key, slot = self._get_slot(request, spider)
        latency = request.meta.get('download_latency')
        if latency is None or slot is None:
            return

        olddelay = slot.delay
        self._adjust_delay(slot, latency, response)
        if self.debug:
            diff = slot.delay - olddelay
            size = len(response.body)
            conc = len(slot.transferring)
            msg = "slot: %s | conc:%2d | delay:%5d ms (%+d) | latency:%5d ms | size:%6d bytes" % \
                  (key, conc, slot.delay * 1000, diff * 1000, latency * 1000, size)
            spider.log(msg, level=logging.INFO)

    def _get_slot(self, request, spider):
        key = request.meta.get('download_slot')
        return key, self.crawler.engine.downloader.slots.get(key)

    def _adjust_delay(self, slot, latency, response):
        """Define delay adjustment policy"""
        # If latency is bigger than old delay, then use latency instead of mean.
        # It works better with problematic sites
        new_delay = min(max(self.mindelay, latency, (slot.delay + latency) / 2.0), self.maxdelay)

        # Dont adjust delay if response status != 200 and new delay is smaller
        # than old one, as error pages (and redirections) are usually small and
        # so tend to reduce latency, thus provoking a positive feedback by
        # reducing delay instead of increase.
        if response.status == 200 or new_delay > slot.delay:
            slot.delay = new_delay
