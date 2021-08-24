"""
A spider that generate light requests to meassure QPS troughput

usage:

    scrapy runspider qpsclient.py --loglevel=INFO --set RANDOMIZE_DOWNLOAD_DELAY=0 --set CONCURRENT_REQUESTS=50 -a qps=10 -a latency=0.3

"""

from scrapy.spiders import Spider
from scrapy.http import Request


class QPSSpider(Spider):

    name = 'qps'
    benchurl = 'http://localhost:8880/'

    # Max concurrency is limited by global CONCURRENT_REQUESTS setting
    max_concurrent_requests = 8
    # Requests per second goal
    qps = None # same as: 1 / download_delay
    download_delay = None
    # time in seconds to delay server responses
    latency = None
    # number of slots to create
    slots = 1

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        if self.qps is not None:
            self.qps = float(self.qps)
            self.download_delay = 1 / self.qps
        elif self.download_delay is not None:
            self.download_delay = float(self.download_delay)

    def start_requests(self):
        url = self.benchurl
        if self.latency is not None:
            url += f'?latency={self.latency}'

        slots = int(self.slots)
        if slots > 1:
            urls = [url.replace('localhost', f'127.0.0.{x + 1}') for x in range(slots)]
        else:
            urls = [url]

        idx = 0
        while True:
            url = urls[idx % len(urls)]
            yield Request(url, dont_filter=True)
            idx += 1

    def parse(self, response):
        pass
