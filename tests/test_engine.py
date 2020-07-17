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
from collections import defaultdict
from urllib.parse import urlparse

import attr
from itemadapter import ItemAdapter
from pydispatch import dispatcher
from testfixtures import LogCapture
from twisted.internet import defer, reactor
from twisted.trial import unittest
from twisted.web import server, static, util

from scrapy import signals
from scrapy.core.engine import ExecutionEngine
from scrapy.exceptions import StopDownload
from scrapy.http import Request
from scrapy.item import Item, Field
from scrapy.linkextractors import LinkExtractor
from scrapy.spiders import Spider
from scrapy.utils.signal import disconnect_all
from scrapy.utils.test import get_crawler

from tests import get_testdata, tests_datadir


class TestItem(Item):
    name = Field()
    url = Field()
    price = Field()


@attr.s
class AttrsItem:
    name = attr.ib(default="")
    url = attr.ib(default="")
    price = attr.ib(default=0)


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


class AttrsItemsSpider(TestSpider):
    item_class = AttrsItem


try:
    from dataclasses import make_dataclass
except ImportError:
    DataClassItemsSpider = None
else:
    TestDataClass = make_dataclass("TestDataClass", [("name", str), ("url", str), ("price", int)])

    class DataClassItemsSpider(DictItemsSpider):
        def parse_item(self, response):
            item = super().parse_item(response)
            return TestDataClass(
                name=item.get('name'),
                url=item.get('url'),
                price=item.get('price'),
            )


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
    numbers = [str(x).encode("utf8") for x in range(2**18)]
    r.putChild(b"numbers", static.Data(b"".join(numbers), "text/plain"))

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
        self.bytes = defaultdict(lambda: list())
        self.signals_caught = {}
        self.spider_class = spider_class

    def run(self):
        self.port = start_test_site()
        self.portno = self.port.getHost().port

        start_urls = [
            self.geturl("/"),
            self.geturl("/redirect"),
            self.geturl("/redirect"),  # duplicate
            self.geturl("/numbers"),
        ]

        for name, signal in vars(signals).items():
            if not name.startswith('_'):
                dispatcher.connect(self.record_signal, signal)

        self.crawler = get_crawler(self.spider_class)
        self.crawler.signals.connect(self.item_scraped, signals.item_scraped)
        self.crawler.signals.connect(self.item_error, signals.item_error)
        self.crawler.signals.connect(self.bytes_received, signals.bytes_received)
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

    def bytes_received(self, data, request, spider):
        self.bytes[request].append(data)

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
        self.signals_caught[sig] = signalargs


class StopDownloadCrawlerRun(CrawlerRun):
    """
    Make sure raising the StopDownload exception stops the download of the response body
    """

    def bytes_received(self, data, request, spider):
        super().bytes_received(data, request, spider)
        raise StopDownload(fail=False)


class EngineTest(unittest.TestCase):

    @defer.inlineCallbacks
    def test_crawler(self):

        for spider in (TestSpider, DictItemsSpider, AttrsItemsSpider, DataClassItemsSpider):
            if spider is None:
                continue
            self.run = CrawlerRun(spider)
            yield self.run.run()
            self._assert_visited_urls()
            self._assert_scheduled_requests(urls_to_visit=9)
            self._assert_downloaded_responses()
            self._assert_scraped_items()
            self._assert_signals_caught()
            self._assert_bytes_received()

    @defer.inlineCallbacks
    def test_crawler_dupefilter(self):
        self.run = CrawlerRun(TestDupeFilterSpider)
        yield self.run.run()
        self._assert_scheduled_requests(urls_to_visit=8)
        self._assert_dropped_requests()

    @defer.inlineCallbacks
    def test_crawler_itemerror(self):
        self.run = CrawlerRun(ItemZeroDivisionErrorSpider)
        yield self.run.run()
        self._assert_items_error()

    def _assert_visited_urls(self):
        must_be_visited = ["/", "/redirect", "/redirected",
                           "/item1.html", "/item2.html", "/item999.html"]
        urls_visited = {rp[0].url for rp in self.run.respplug}
        urls_expected = {self.run.geturl(p) for p in must_be_visited}
        assert urls_expected <= urls_visited, "URLs not visited: %s" % list(urls_expected - urls_visited)

    def _assert_scheduled_requests(self, urls_to_visit=None):
        self.assertEqual(urls_to_visit, len(self.run.reqplug))

        paths_expected = ['/item999.html', '/item2.html', '/item1.html']

        urls_requested = {rq[0].url for rq in self.run.reqplug}
        urls_expected = {self.run.geturl(p) for p in paths_expected}
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
        self.assertEqual(9, len(self.run.respplug))
        self.assertEqual(9, len(self.run.reqreached))

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
            item = ItemAdapter(item)
            self.assertEqual(item['url'], response.url)
            if 'item1.html' in item['url']:
                self.assertEqual('Item 1 name', item['name'])
                self.assertEqual('100', item['price'])
            if 'item2.html' in item['url']:
                self.assertEqual('Item 2 name', item['name'])
                self.assertEqual('200', item['price'])

    def _assert_bytes_received(self):
        self.assertEqual(9, len(self.run.bytes))
        for request, data in self.run.bytes.items():
            joined_data = b"".join(data)
            if self.run.getpath(request.url) == "/":
                self.assertEqual(joined_data, get_testdata("test_site", "index.html"))
            elif self.run.getpath(request.url) == "/item1.html":
                self.assertEqual(joined_data, get_testdata("test_site", "item1.html"))
            elif self.run.getpath(request.url) == "/item2.html":
                self.assertEqual(joined_data, get_testdata("test_site", "item2.html"))
            elif self.run.getpath(request.url) == "/redirected":
                self.assertEqual(joined_data, b"Redirected here")
            elif self.run.getpath(request.url) == '/redirect':
                self.assertEqual(
                    joined_data,
                    b"\n<html>\n"
                    b"    <head>\n"
                    b"        <meta http-equiv=\"refresh\" content=\"0;URL=/redirected\">\n"
                    b"    </head>\n"
                    b"    <body bgcolor=\"#FFFFFF\" text=\"#000000\">\n"
                    b"    <a href=\"/redirected\">click here</a>\n"
                    b"    </body>\n"
                    b"</html>\n"
                )
            elif self.run.getpath(request.url) == "/tem999.html":
                self.assertEqual(
                    joined_data,
                    b"\n<html>\n"
                    b"  <head><title>404 - No Such Resource</title></head>\n"
                    b"  <body>\n"
                    b"    <h1>No Such Resource</h1>\n"
                    b"    <p>File not found.</p>\n"
                    b"  </body>\n"
                    b"</html>\n"
                )
            elif self.run.getpath(request.url) == "/numbers":
                # signal was fired multiple times
                self.assertTrue(len(data) > 1)
                # bytes were received in order
                numbers = [str(x).encode("utf8") for x in range(2**18)]
                self.assertEqual(joined_data, b"".join(numbers))

    def _assert_signals_caught(self):
        assert signals.engine_started in self.run.signals_caught
        assert signals.engine_stopped in self.run.signals_caught
        assert signals.spider_opened in self.run.signals_caught
        assert signals.spider_idle in self.run.signals_caught
        assert signals.spider_closed in self.run.signals_caught

        self.assertEqual({'spider': self.run.spider},
                         self.run.signals_caught[signals.spider_opened])
        self.assertEqual({'spider': self.run.spider},
                         self.run.signals_caught[signals.spider_idle])
        self.assertEqual({'spider': self.run.spider, 'reason': 'finished'},
                         self.run.signals_caught[signals.spider_closed])

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


class StopDownloadEngineTest(EngineTest):

    @defer.inlineCallbacks
    def test_crawler(self):
        for spider in TestSpider, DictItemsSpider:
            self.run = StopDownloadCrawlerRun(spider)
            with LogCapture() as log:
                yield self.run.run()
                log.check_present(("scrapy.core.downloader.handlers.http11",
                                   "DEBUG",
                                   "Download stopped for <GET http://localhost:{}/redirected> from signal handler"
                                   " StopDownloadCrawlerRun.bytes_received".format(self.run.portno)))
                log.check_present(("scrapy.core.downloader.handlers.http11",
                                   "DEBUG",
                                   "Download stopped for <GET http://localhost:{}/> from signal handler"
                                   " StopDownloadCrawlerRun.bytes_received".format(self.run.portno)))
                log.check_present(("scrapy.core.downloader.handlers.http11",
                                   "DEBUG",
                                   "Download stopped for <GET http://localhost:{}/numbers> from signal handler"
                                   " StopDownloadCrawlerRun.bytes_received".format(self.run.portno)))
            self._assert_visited_urls()
            self._assert_scheduled_requests(urls_to_visit=9)
            self._assert_downloaded_responses()
            self._assert_signals_caught()
            self._assert_bytes_received()

    def _assert_bytes_received(self):
        self.assertEqual(9, len(self.run.bytes))
        for request, data in self.run.bytes.items():
            joined_data = b"".join(data)
            self.assertTrue(len(data) == 1)  # signal was fired only once
            if self.run.getpath(request.url) == "/numbers":
                # Received bytes are not the complete response. The exact amount depends
                # on the buffer size, which can vary, so we only check that the amount
                # of received bytes is strictly less than the full response.
                numbers = [str(x).encode("utf8") for x in range(2**18)]
                self.assertTrue(len(joined_data) < len(b"".join(numbers)))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == 'runserver':
        start_test_site(debug=True)
        reactor.run()
