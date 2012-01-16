from scrapy.xlib.pydispatch import dispatcher
from scrapy.exceptions import NotConfigured
from scrapy import signals
from scrapy.utils.httpobj import urlparse_cached
from scrapy.resolver import dnscache

class AutoThrottle(object):
    """
    ============
    AutoThrottle
    ============

    This is an extension for automatically throttling crawling speed based on
    load.

    Design goals
    ============

    1. be nicer to sites instead of using default download delay of zero

    2. automatically adjust scrapy to the optimum crawling speed, so the user
    doesn't have to tune the download delays and concurrent requests to find
    the optimum one. the user only needs to specify the maximum concurrent
    requests it allows, and the extension does the rest.

    Download latencies
    ==================

    In Scrapy, the download latency is the (real) time elapsed between
    establishing the TCP connection and receiving the HTTP headers.

    Note that these latencies are very hard to measure accurately in a
    cooperative multitasking environment because Scrapy may be busy processing
    a spider callback, for example, and unable to attend downloads. However,
    the latencies should give a reasonable estimate of how busy Scrapy (and
    ultimately, the server) is. This extension builds on that premise.

    Throttling rules
    ================

    This adjusts download delays and concurrency based on the following rules:

    1. spiders always start with one concurrent request and a download delay of
    START_DELAY

    2. when a response is received, the download delay is adjusted to the
    average of previous download delay and the latency of the response.

    3. after CONCURRENCY_CHECK_PERIOD responses have passed, the average
    latency of this period is checked against the previous one and:

    3.1. if the latency remained constant (within standard deviation limits)
    and the concurrency is lower than MAX_CONCURRENCY, the concurrency is
    increased

    3.2. if the latency has increased (beyond standard deviation limits) and
    the concurrency is higher than 1, the concurrency is decreased

    """

    def __init__(self, crawler):
        settings = crawler.settings    
        if not settings.getbool('AUTOTHROTTLE_ENABLED'):
            raise NotConfigured
        self.crawler = crawler
        dispatcher.connect(self.spider_opened, signal=signals.spider_opened)
        dispatcher.connect(self.response_received, signal=signals.response_received)
        self.START_DELAY = settings.getfloat("AUTOTHROTTLE_START_DELAY", 5.0)
        self.CONCURRENCY_CHECK_PERIOD = settings.getint("AUTOTHROTTLE_CONCURRENCY_CHECK_PERIOD", 10)
        self.MAX_CONCURRENCY = settings.getint("AUTOTHROTTLE_MAX_CONCURRENCY", 8)
        self.DEBUG = settings.getbool("AUTOTHROTTLE_DEBUG")
        self.MIN_DOWNLOAD_DELAY = settings.getint("AUTOTHROTTLE_MIN_DOWNLOAD_DELAY")
        self.last_latencies = [self.START_DELAY]
        self.last_lat = self.START_DELAY, 0.0

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
        slot = self._get_slot(response.request)
        latency = response.meta.get('download_latency')
        
        if not latency or not slot:
            return

        self._adjust_delay(slot, latency, response)
        self._check_concurrency(slot, latency)

        if self.DEBUG:
            spider.log("conc:%2d | delay:%5d ms | latency:%5d ms | size:%6d bytes" % \
                (slot.concurrency, slot.delay*1000, \
                latency*1000, len(response.body)))

    def _get_slot(self, request):
        downloader = self.crawler.engine.downloader
        key = urlparse_cached(request).hostname or ''
        if downloader.ip_concurrency:
            key = dnscache.get(key, key)
        return downloader.slots.get(key)

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
