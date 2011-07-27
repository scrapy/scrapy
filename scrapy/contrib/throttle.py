# TODO: this extension is currently broken and needs to be ported after the
# downloader refactoring introduced in r2732

from scrapy.xlib.pydispatch import dispatcher
from scrapy.utils.python import setattr_default
from scrapy.conf import settings
from scrapy.exceptions import NotConfigured
from scrapy import signals

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

    # TODO: convert these to settings
    START_DELAY = 5.0
    MAX_CONCURRENCY = 8
    CONCURRENCY_CHECK_PERIOD = 10

    DEBUG = 0

    def __init__(self):
        if not settings.getbool('AUTOTHROTTLE_ENABLED'):
            raise NotConfigured
        dispatcher.connect(self.spider_opened, signal=signals.spider_opened)
        dispatcher.connect(self.spider_closed, signal=signals.spider_closed)
        dispatcher.connect(self.response_received, signal=signals.response_received)
        self.last_latencies = {}
        self.last_lat = {}

    def spider_opened(self, spider):
        spider.download_delay = self.START_DELAY
        spider.max_concurrent_requests = 1
        self.last_latencies[spider] = [self.START_DELAY]
        self.last_lat[spider] = self.START_DELAY, 0.0

    def spider_closed(self, spider):
        del self.last_latencies[spider]
        del self.last_lat[spider]

    def response_received(self, response, spider):
        latency = response.meta.get('download_latency')
        if not latency:
            return
        spider.download_delay = (spider.download_delay + latency) / 2.0
        self._check_concurrency(spider, latency)
        if self.DEBUG:
            print "conc:%2d | delay:%5d ms | latency:%5d ms | size:%6d bytes" % \
                (spider.max_concurrent_requests, spider.download_delay*1000, \
                latency*1000, len(response.body))

    def _check_concurrency(self, spider, latency):
        latencies = self.last_latencies[spider]
        latencies.append(latency)
        if len(latencies) == self.CONCURRENCY_CHECK_PERIOD:
            curavg, curdev = avg_stdev(latencies)
            preavg, predev = self.last_lat[spider]
            self.last_lat[spider] = curavg, curdev
            del latencies[:]
            if curavg > preavg + predev:
                if spider.max_concurrent_requests > 1:
                    spider.max_concurrent_requests -= 1
            elif spider.max_concurrent_requests < self.MAX_CONCURRENCY:
                spider.max_concurrent_requests += 1

def avg_stdev(lst):
    """Return average and standard deviation of the given list"""
    avg = sum(lst)/len(lst)
    sdsq = sum((x-avg) ** 2 for x in lst)
    stdev = (sdsq / (len(lst) -1)) ** 0.5
    return avg, stdev
