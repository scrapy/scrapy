"""
A spider that generate light requests to meassure QPS troughput

usage:

    scrapy runspider qpsclient.py --loglevel=INFO --set RANDOMIZE_DOWNLOAD_DELAY=0 --set CONCURRENT_REQUESTS=50 -a qps=10 -a sleep=0.3

"""

from scrapy.spider import BaseSpider
from scrapy.http import Request


class QPSSpider(BaseSpider):

    name = 'qps'
    benchurl = 'http://localhost:8880/'


    # Max concurrency is limited by global CONCURRENT_REQUESTS setting
    max_concurrent_requests = 8
    # Requests per second goal
    qps = None # same as: 1 / download_delay
    # time in seconds to delay server responses
    sleep = None 

    def __init__(self, *a, **kw):
        super(QPSSpider, self).__init__(*a, **kw)
        if self.qps is not None:
            self.qps = float(self.qps)
            self.download_delay = 1 / self.qps

    def start_requests(self):
        url = self.benchurl
        if self.sleep is not None:
            url += '?sleep={0}'.format(self.sleep)

        while True:
            yield Request(url, dont_filter=True)

    def parse(self, response):
        pass
