import pprint

from scrapy import log


class PeriodicStatsPipeline(object):
    """
    Base class for periodic stats pipeline
    """
    def __init__(self, crawler):
        pass

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    def open_spider(self, spider):
        pass

    def close_spider(self, spider, reason):
        pass

    def process_stats(self, spider, period, stats):
        raise NotImplementedError


class PeriodicStatsLogger(PeriodicStatsPipeline):
    """
    Stats processor that print stats debug info
    """
    def process_stats(self, spider, interval, stats):
        log.msg('Dumping Scrapy periodic stats:\n' + pprint.pformat({
            'spider': spider.name,
            'interval': interval,
            'stats': stats,
        }))
        return stats
