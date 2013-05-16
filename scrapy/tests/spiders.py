"""
Some spiders used for testing and benchmarking
"""

import time

from scrapy.spider import BaseSpider
from scrapy.http import Request
from scrapy.contrib.linkextractors.sgml import SgmlLinkExtractor

class FollowAllSpider(BaseSpider):

    name = 'follow'
    link_extractor = SgmlLinkExtractor()

    def __init__(self, total=10, show=20, order="rand"):
        self.urls_visited = []
        self.times = []
        url = "http://localhost:8998/follow?total=%s&show=%s&order=%s" % (total, show, order)
        self.start_urls = [url]

    def parse(self, response):
        self.urls_visited.append(response.url)
        self.times.append(time.time())
        for link in self.link_extractor.extract_links(response):
            yield Request(link.url, callback=self.parse)

class DelaySpider(BaseSpider):

    name = 'delay'

    def __init__(self, n=1):
        self.n = n
        self.t1 = self.t2 = self.t2_err = 0

    def start_requests(self):
        self.t1 = time.time()
        yield Request("http://localhost:8998/delay?n=%s" % self.n, \
            callback=self.parse, errback=self.errback)

    def parse(self, response):
        self.t2 = time.time()

    def errback(self, failure):
        self.t2_err = time.time()

class SimpleSpider(BaseSpider):

    name = 'simple'

    def __init__(self, url="http://localhost:8998"):
        self.start_urls = [url]

    def parse(self, response):
        self.log("Got response %d" % response.status)
