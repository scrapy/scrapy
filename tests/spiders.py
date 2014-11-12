"""
Some spiders used for testing and benchmarking
"""

import time
from six.moves.urllib.parse import urlencode

from scrapy.spider import Spider
from scrapy.http import Request
from scrapy.item import Item
from scrapy.contrib.linkextractors import LinkExtractor


class MetaSpider(Spider):

    name = 'meta'

    def __init__(self, *args, **kwargs):
        super(MetaSpider, self).__init__(*args, **kwargs)
        self.meta = {}

    def closed(self, reason):
        self.meta['close_reason'] = reason


class FollowAllSpider(MetaSpider):

    name = 'follow'
    link_extractor = LinkExtractor()

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


class SingleRequestSpider(MetaSpider):

    seed = None
    callback_func = None
    errback_func = None

    def start_requests(self):
        if isinstance(self.seed, Request):
            yield self.seed.replace(callback=self.parse, errback=self.on_error)
        else:
            yield Request(self.seed, callback=self.parse, errback=self.on_error)

    def parse(self, response):
        self.meta.setdefault('responses', []).append(response)
        if callable(self.callback_func):
            return self.callback_func(response)
        if 'next' in response.meta:
            return response.meta['next']

    def on_error(self, failure):
        self.meta['failure'] = failure
        if callable(self.errback_func):
            return self.errback_func(failure)


class DuplicateStartRequestsSpider(Spider):
    dont_filter = True
    name = 'duplicatestartrequests'
    distinct_urls = 2
    dupe_factor = 3

    def start_requests(self):
        for i in range(0, self.distinct_urls):
            for j in range(0, self.dupe_factor):
                url = "http://localhost:8998/echo?headers=1&body=test%d" % i
                yield self.make_requests_from_url(url)

    def make_requests_from_url(self, url):
        return Request(url, dont_filter=self.dont_filter)

    def __init__(self, url="http://localhost:8998", *args, **kwargs):
        super(DuplicateStartRequestsSpider, self).__init__(*args, **kwargs)
        self.visited = 0

    def parse(self, response):
        self.visited += 1
