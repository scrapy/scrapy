"""
A spider that generate light requests to measure QPS throughput

usage:

    scrapy runspider qpsclient.py --loglevel=INFO --set RANDOMIZE_DOWNLOAD_DELAY=0
     --set CONCURRENT_REQUESTS=50 -a qps=10 -a latency=0.3

"""

from scrapy.http import Request
from scrapy.spiders import Spider


class QPSSpider(Spider):
    name = "qps"
    benchurl = "http://localhost:8880/"

    # Requests per second goal
    qps = None  # same as: 1 / DOWNLOAD_DELAY
    # time in seconds to delay server responses
    latency = None
    # number of slots to create
    slots = 1

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        if spider.qps is not None:
            spider.qps = float(spider.qps)
            crawler.settings.set("DOWNLOAD_DELAY", 1 / spider.qps, priority="spider")
        return spider

    async def start(self):
        url = self.benchurl
        if self.latency is not None:
            url += f"?latency={self.latency}"

        slots = int(self.slots)
        if slots > 1:
            urls = [url.replace("localhost", f"127.0.0.{x + 1}") for x in range(slots)]
        else:
            urls = [url]

        idx = 0
        while True:
            url = urls[idx % len(urls)]
            yield Request(url, dont_filter=True)
            idx += 1

    def parse(self, response):
        pass
