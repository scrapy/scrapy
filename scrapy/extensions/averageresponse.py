"""
Extension for getting the average response time of each request
"""
import logging
import time

from scrapy import signals
from scrapy.exceptions import NotConfigured

logger = logging.getLogger(__name__)


class ResponseTime:
    def __init__(self, stats, crawler):
        self.stats = stats
        self.start_time = None

        self.response_times = []
        self.elapsed_time = None

        if not crawler.settings.getbool("AVERAGERESPOSNE_ENABLED"):
            raise NotConfigured

    @classmethod
    def from_crawler(cls, crawler):
        o = cls(crawler.stats, crawler)
        crawler.signals.connect(o.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(o.spider_closed, signal=signals.spider_closed)
        crawler.signals.connect(o.response_received, signal=signals.response_received)
        crawler.signals.connect(
            o.request_reached_downloader, signal=signals.request_reached_downloader
        )
        return o

    def request_reached_downloader(self):
        self.start_time = time.time()

    def spider_opened(self, spider):
        logger.info("opened spider %s", spider.name)

    def spider_closed(self, spider, reason):
        logger.info("closed spider %s", spider.name)
        if len(self.response_times) > 0:
            averageresponsetime = sum(self.response_times) / len(self.response_times)
            logger.info("average response time %d ms", averageresponsetime)
        else:
            logger.info("No responses logged.")

    def response_received(self, spider):
        self.stats.inc_value("response_received_count", spider=spider)
        self.response_times.append((time.time() * 1000 - self.start_time * 1000))
