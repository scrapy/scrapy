"""
Scrapy engine tests

This starts a testing web server (using twisted.server.Site) and then crawls it
with the Scrapy crawler.

To view the testing web server in a browser you can start it by running this
module with the ``runserver`` argument::

    python test_engine.py runserver
"""

import os
import re
import sys
from urllib.parse import urlparse

from twisted.internet import reactor, defer
from twisted.web import server, static, util
from twisted.trial import unittest

from scrapy import signals
from scrapy.core.engine import ExecutionEngine
from scrapy.utils.test import get_crawler
from pydispatch import dispatcher
from tests import tests_datadir
from scrapy.spiders import Spider
from scrapy.item import Item, Field
from scrapy.linkextractors import LinkExtractor
from scrapy.http import Request
from scrapy.utils.signal import disconnect_all


class TestItem(Item):
    name = Field()
    url = Field()
    price = Field()


class TestSpider(Spider):
    name = "scrapytest.org"
    allowed_domains = ["scrapytest.org", "localhost"]

    itemurl_re = re.compile(r"item\d+.html")
    name_re = re.compile(r"<h1>(.*?)</h1>", re.M)
    price_re = re.compile(r">Price: \$(.*?)<", re.M)

    item_cls = TestItem

    def parse(self, response):
        xlink = LinkExtractor()
        itemre = re.compile(self.itemurl_re)
        for link in xlink.extract_links(response):
            if itemre.search(link.url):
                yield Request(url=link.url, callback=self.parse_item)

    def parse_item(self, response):
        item = self.item_cls()
        m = self.name_re.search(response.text)
        if m:
            item['name'] = m.group(1)
        item['url'] = response.url
        m = self.price_re.search(response.text)
        if m:
            item['price'] = m.group(1)
        return item


class TestDupeFilterSpider(TestSpider):
    def start_requests(self):
        return (Request(url) for url in self.start_urls)  # no dont_filter=True


class DictItemsSpider(TestSpider):
    item_cls = dict


class ItemZeroDivisionErrorSpider(TestSpider):
    custom_settings = {
        "ITEM_PIPELINES": {
            "tests.pipelines.ProcessWithZeroDivisionErrorPipiline": 300,
        }
    }


def start_test_site(debug=False):
    root_dir = os.path.join(tests_datadir, "test_site")
    r = static.File(root_dir)
    r.putChild(b"redirect", util.Redirect(b"/redirected"))
    r.putChild(b"redirected", static.Data(b"Redirected here", "text/plain"))

    port = reactor.listenTCP(0, server.Site(r), interface="127.0.0.1")
    if debug:
        print("Test server running at http://localhost:%d/ - hit Ctrl-C to finish."
              % port.getHost().port)
    return port


class CrawlerRun:
    """A class to run the crawler and keep track of events occurred"""

    def __init__(self, spider_class):
        self.spider = None
        self.respplug = []
        self.reqplug = []
        self.reqdropped = []
        self.reqreached = []
        self.itemerror = []
        self.itemresp = []
        self.signals_catched = {}
        self.spider_class = spider_class

    def run(self):
        self.port = start_test_site()
        self.portno = self.port.getHost().port

        start_urls = [self.geturl("/"), self.geturl("/redirect"),
                      self.geturl("/redirect")]  # a duplicate

        for name, signal in vars(signals).items():
            if not name.startswith('_'):
                dispatcher.connect(self.record_signal, signal)

        self.crawler = get_crawler(self.spider_class)
        self.crawler.signals.connect(self.item_scraped, signals.item_scraped)
        self.crawler.signals.connect(self.item_error, signals.item_error)
        self.crawler.signals.connect(self.request_scheduled, signals.request_scheduled)
        self.crawler.signals.connect(self.request_dropped, signals.request_dropped)
        self.crawler.signals.connect(self.request_reached, signals.request_reached_downloader)
        self.crawler.signals.connect(self.response_downloaded, signals.response_downloaded)
        self.crawler.crawl(start_urls=start_urls)
        self.spider = self.crawler.spider

        self.deferred = defer.Deferred()
        dispatcher.connect(self.stop, signals.engine_stopped)
        return self.deferred

    def stop(self):
        self.port.stopListening()
        for name, signal in vars(signals).items():
            if not name.startswith('_'):
                disconnect_all(signal)
        self.deferred.callback(None)

    def geturl(self, path):
        return "http://localhost:%s%s" % (self.portno, path)

    def getpath(self, url):
        u = urlparse(url)
        return u.path

    def item_error(self, item, response, spider, failure):
        self.itemerror.append((item, response, spider, failure))

    def item_scraped(self, item, spider, response):
        self.itemresp.append((item, response))

    def request_scheduled(self, request, spider):
        self.reqplug.append((request, spider))

    def request_reached(self, request, spider):
        self.reqreached.append((request, spider))

    def request_dropped(self, request, spider):
        self.reqdropped.append((request, spider))

    def response_downloaded(self, response, spider):
        self.respplug.append((response, spider))

    def record_signal(self, *args, **kwargs):
        """Record a signal and its parameters"""
        signalargs = kwargs.copy()
        sig = signalargs.pop('signal')
        signalargs.pop('sender', None)
        self.signals_catched[sig] = signalargs


class EngineTest(unittest.TestCase):

    @defer.inlineCallbacks
    def test_crawler(self):
        for spider in TestSpider, DictItemsSpider:
            self.run = CrawlerRun(spider)
            yield self.run.run()
            self._assert_visited_urls()
            self._assert_scheduled_requests(urls_to_visit=8)
            self._assert_downloaded_responses()
            self._assert_scraped_items()
            self._assert_signals_catched()

    @defer.inlineCallbacks
    def test_crawler_dupefilter(self):
        self.run = CrawlerRun(TestDupeFilterSpider)
        yield self.run.run()
        self._assert_scheduled_requests(urls_to_visit=7)
        self._assert_dropped_requests()

    @defer.inlineCallbacks
    def test_crawler_itemerror(self):
        self.run = CrawlerRun(ItemZeroDivisionErrorSpider)
        yield self.run.run()
        self._assert_items_error()

    def _assert_visited_urls(self):
        must_be_visited = ["/", "/redirect", "/redirected",
                           "/item1.html", "/item2.html", "/item999.html"]
        urls_visited = set([rp[0].url for rp in self.run.respplug])
        urls_expected = set([self.run.geturl(p) for p in must_be_visited])
        assert urls_expected <= urls_visited, "URLs not visited: %s" % list(urls_expected - urls_visited)

    def _assert_scheduled_requests(self, urls_to_visit=None):
        self.assertEqual(urls_to_visit, len(self.run.reqplug))

        paths_expected = ['/item999.html', '/item2.html', '/item1.html']

        urls_requested = set([rq[0].url for rq in self.run.reqplug])
        urls_expected = set([self.run.geturl(p) for p in paths_expected])
        assert urls_expected <= urls_requested
        scheduled_requests_count = len(self.run.reqplug)
        dropped_requests_count = len(self.run.reqdropped)
        responses_count = len(self.run.respplug)
        self.assertEqual(scheduled_requests_count,
                         dropped_requests_count + responses_count)
        self.assertEqual(len(self.run.reqreached),
                         responses_count)

    def _assert_dropped_requests(self):
        self.assertEqual(len(self.run.reqdropped), 1)

    def _assert_downloaded_responses(self):
        # response tests
        self.assertEqual(8, len(self.run.respplug))
        self.assertEqual(8, len(self.run.reqreached))

        for response, _ in self.run.respplug:
            if self.run.getpath(response.url) == '/item999.html':
                self.assertEqual(404, response.status)
            if self.run.getpath(response.url) == '/redirect':
                self.assertEqual(302, response.status)

    def _assert_items_error(self):
        self.assertEqual(2, len(self.run.itemerror))
        for item, response, spider, failure in self.run.itemerror:
            self.assertEqual(failure.value.__class__, ZeroDivisionError)
            self.assertEqual(spider, self.run.spider)

            self.assertEqual(item['url'], response.url)
            if 'item1.html' in item['url']:
                self.assertEqual('Item 1 name', item['name'])
                self.assertEqual('100', item['price'])
            if 'item2.html' in item['url']:
                self.assertEqual('Item 2 name', item['name'])
                self.assertEqual('200', item['price'])

    def _assert_scraped_items(self):
        self.assertEqual(2, len(self.run.itemresp))
        for item, response in self.run.itemresp:
            self.assertEqual(item['url'], response.url)
            if 'item1.html' in item['url']:
                self.assertEqual('Item 1 name', item['name'])
                self.assertEqual('100', item['price'])
            if 'item2.html' in item['url']:
                self.assertEqual('Item 2 name', item['name'])
                self.assertEqual('200', item['price'])

    def _assert_signals_catched(self):
        assert signals.engine_started in self.run.signals_catched
        assert signals.engine_stopped in self.run.signals_catched
        assert signals.spider_opened in self.run.signals_catched
        assert signals.spider_idle in self.run.signals_catched
        assert signals.spider_closed in self.run.signals_catched

        self.assertEqual({'spider': self.run.spider},
                         self.run.signals_catched[signals.spider_opened])
        self.assertEqual({'spider': self.run.spider},
                         self.run.signals_catched[signals.spider_idle])
        self.assertEqual({'spider': self.run.spider, 'reason': 'finished'},
                         self.run.signals_catched[signals.spider_closed])

    @defer.inlineCallbacks
    def test_close_downloader(self):
        e = ExecutionEngine(get_crawler(TestSpider), lambda _: None)
        yield e.close()

    @defer.inlineCallbacks
    def test_close_spiders_downloader(self):
        e = ExecutionEngine(get_crawler(TestSpider), lambda _: None)
        yield e.open_spider(TestSpider(), [])
        self.assertEqual(len(e.open_spiders), 1)
        yield e.close()
        self.assertEqual(len(e.open_spiders), 0)

    @defer.inlineCallbacks
    def test_close_engine_spiders_downloader(self):
        e = ExecutionEngine(get_crawler(TestSpider), lambda _: None)
        yield e.open_spider(TestSpider(), [])
        e.start()
        self.assertTrue(e.running)
        yield e.close()
        self.assertFalse(e.running)
        self.assertEqual(len(e.open_spiders), 0)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == 'runserver':
        start_test_site(debug=True)
        reactor.run()
