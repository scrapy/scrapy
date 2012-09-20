from scrapy.exceptions import NotConfigured
from scrapy import signals
from scrapy.utils.httpobj import urlparse_cached
from scrapy.resolver import dnscache

class AutoThrottle(object):

    def __init__(self, crawler):
        settings = crawler.settings    
        if not settings.getbool('AUTOTHROTTLE_ENABLED'):
            raise NotConfigured
        self.crawler = crawler
        crawler.signals.connect(self.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(self.response_received, signal=signals.response_received)
        self.START_DELAY = settings.getfloat("AUTOTHROTTLE_START_DELAY", 5.0)
        self.CONCURRENCY_CHECK_PERIOD = settings.getint("AUTOTHROTTLE_CONCURRENCY_CHECK_PERIOD", 10)
        self.MAX_CONCURRENCY = self._max_concurency(settings)
        self.MIN_DOWNLOAD_DELAY = self._min_download_delay(settings)
        self.DEBUG = settings.getbool("AUTOTHROTTLE_DEBUG")
        self.last_latencies = [self.START_DELAY]
        self.last_lat = self.START_DELAY, 0.0

    def _min_download_delay(self, settings):
        return max(settings.getint("AUTOTHROTTLE_MIN_DOWNLOAD_DELAY"),
            settings.getint("DOWNLOAD_DELAY"))

    def _max_concurency(self, settings):
        delay = self._min_download_delay(settings)
        if delay == 0:
            candidates = ["AUTOTHROTTLE_MAX_CONCURRENCY",
                "CONCURRENT_REQUESTS_PER_DOMAIN", "CONCURRENT_REQUESTS_PER_IP"]
            candidates = [settings.getint(x) for x in candidates]
            candidates = [x for x in candidates if x > 0]
            if candidates:
                return min(candidates)
        return 1

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def spider_opened(self, spider):
        if hasattr(spider, "download_delay"):
            self.MIN_DOWNLOAD_DELAY = spider.download_delay
        spider.download_delay = self.START_DELAY
        if hasattr(spider, "max_concurrent_requests"):
            self.MAX_CONCURRENCY = spider.max_concurrent_requests
        # override in order to avoid to initialize slot with concurrency > 1
        spider.max_concurrent_requests = 1

    def response_received(self, response, spider):
        key, slot = self._get_slot(response.request)
        latency = response.meta.get('download_latency')
        
        if not latency or not slot:
            return

        self._adjust_delay(slot, latency, response)
        self._check_concurrency(slot, latency)

        if self.DEBUG:
            spider.log("slot: %s | conc:%2d | delay:%5d ms | latency:%5d ms | size:%6d bytes" % \
                (key, slot.concurrency, slot.delay*1000, \
                latency*1000, len(response.body)))

    def _get_slot(self, request):
        downloader = self.crawler.engine.downloader
        key = urlparse_cached(request).hostname or ''
        if downloader.ip_concurrency:
            key = dnscache.get(key, key)
        return key, downloader.slots.get(key) or downloader.inactive_slots.get(key)

    def _check_concurrency(self, slot, latency):
        latencies = self.last_latencies
        latencies.append(latency)
        if len(latencies) == self.CONCURRENCY_CHECK_PERIOD:
            curavg, curdev = avg_stdev(latencies)
            preavg, predev = self.last_lat
            self.last_lat = curavg, curdev
            del latencies[:]
            if curavg > preavg + predev:
                if slot.concurrency > 1:
                    slot.concurrency -= 1
            elif slot.concurrency < self.MAX_CONCURRENCY:
                slot.concurrency += 1

    def _adjust_delay(self, slot, latency, response):
        """Define delay adjustment policy"""
        # if latency is bigger than old delay, then use latency instead of mean. Works better with problematic sites
        new_delay = (slot.delay + latency) / 2.0 if latency < slot.delay else latency

        if new_delay < self.MIN_DOWNLOAD_DELAY:
            new_delay = self.MIN_DOWNLOAD_DELAY

        # dont adjust delay if response status != 200 and new delay is smaller than old one,
        # as error pages (and redirections) are usually small and so tend to reduce latency, thus provoking a positive feedback
        # by reducing delay instead of increase.
        if response.status == 200 or new_delay > slot.delay:
            slot.delay = new_delay

def avg_stdev(lst):
    """Return average and standard deviation of the given list"""
    avg = sum(lst)/len(lst)
    sdsq = sum((x-avg) ** 2 for x in lst)
    stdev = (sdsq / (len(lst) -1)) ** 0.5
    return avg, stdev
