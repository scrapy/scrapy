"""
Some spiders used for testing and benchmarking
"""

import time
from urllib import urlencode

from scrapy.spider import BaseSpider
from scrapy.http import Request
from scrapy.item import Item
from scrapy.contrib.linkextractors.sgml import SgmlLinkExtractor


class MetaSpider(BaseSpider):

    name = 'meta'

    def __init__(self, *args, **kwargs):
        super(MetaSpider, self).__init__(*args, **kwargs)
        self.meta = {}

    def closed(self, reason):
        self.meta['close_reason'] = reason


class FollowAllSpider(MetaSpider):

    name = 'follow'
    link_extractor = SgmlLinkExtractor()

    def __init__(self, total=10, show=20, order="rand", maxlatency=0.0, *args, **kwargs):
        super(FollowAllSpider, self).__init__(*args, **kwargs)
        self.urls_visited = []
        self.times = []
        qargs = {'total': total, 'show': show, 'order': order, 'maxlatency': maxlatency}
        url = "http://localhost:8998/follow?%s" % urlencode(qargs, doseq=1)
        self.start_urls = [url]

    def parse(self, response):
        self.urls_visited.append(response.url)
        self.times.append(time.time())
        for link in self.link_extractor.extract_links(response):
            yield Request(link.url, callback=self.parse)


class DelaySpider(MetaSpider):

    name = 'delay'

    def __init__(self, n=1, b=0, *args, **kwargs):
        super(DelaySpider, self).__init__(*args, **kwargs)
        self.n = n
        self.b = b
        self.t1 = self.t2 = self.t2_err = 0

    def start_requests(self):
        self.t1 = time.time()
        url = "http://localhost:8998/delay?n=%s&b=%s" % (self.n, self.b)
        yield Request(url, callback=self.parse, errback=self.errback)

    def parse(self, response):
        self.t2 = time.time()

    def errback(self, failure):
        self.t2_err = time.time()


class SimpleSpider(MetaSpider):

    name = 'simple'

    def __init__(self, url="http://localhost:8998", *args, **kwargs):
        super(SimpleSpider, self).__init__(*args, **kwargs)
        self.start_urls = [url]

    def parse(self, response):
        self.log("Got response %d" % response.status)


class ItemSpider(FollowAllSpider):

    name = 'item'

    def parse(self, response):
        for request in super(ItemSpider, self).parse(response):
            yield request
            yield Item()


class DefaultError(Exception):
    pass


class ErrorSpider(FollowAllSpider):

    name = 'error'
    exception_cls = DefaultError

    def raise_exception(self):
        raise self.exception_cls('Expected exception')

    def parse(self, response):
        for request in super(ErrorSpider, self).parse(response):
            yield request
            self.raise_exception()


class BrokenStartRequestsSpider(FollowAllSpider):

    fail_before_yield = False
    fail_yielding = False

    def __init__(self, *a, **kw):
        super(BrokenStartRequestsSpider, self).__init__(*a, **kw)
        self.seedsseen = []

    def start_requests(self):
        if self.fail_before_yield:
            1 / 0

        for s in xrange(100):
            qargs = {'total': 10, 'seed': s}
            url = "http://localhost:8998/follow?%s" % urlencode(qargs, doseq=1)
            yield Request(url, meta={'seed': s})
            if self.fail_yielding:
                2 / 0

        assert self.seedsseen, \
                'All start requests consumed before any download happened'

    def parse(self, response):
        self.seedsseen.append(response.meta.get('seed'))
        for req in super(BrokenStartRequestsSpider, self).parse(response):
            yield req
