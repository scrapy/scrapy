"""
Scrapy engine tests

This starts a testing web server (using twisted.server.Site) and then crawls it
with the Scrapy crawler.

To view the testing web server in a browser you can start it by running this
module with the ``runserver`` argument::

    python test_engine.py runserver
"""

from __future__ import print_function
import sys, os, re
from six.moves.urllib.parse import urlparse

from twisted.internet import reactor, defer
from twisted.web import server, static, util
from twisted.trial import unittest

from scrapy import signals
from scrapy.utils.test import get_crawler
from scrapy.xlib.pydispatch import dispatcher
from tests import tests_datadir
from scrapy.spider import Spider
from scrapy.item import Item, Field
from scrapy.contrib.linkextractors import LinkExtractor
from scrapy.http import Request
from scrapy.utils.signal import disconnect_all

class TestItem(Item):
    name = Field()
    url = Field()
    price = Field()

class TestSpider(Spider):
    name = "scrapytest.org"
    allowed_domains = ["scrapytest.org", "localhost"]

    itemurl_re = re.compile("item\d+.html")
    name_re = re.compile("<h1>(.*?)</h1>", re.M)
    price_re = re.compile(">Price: \$(.*?)<", re.M)

    def parse(self, response):
        xlink = LinkExtractor()
        itemre = re.compile(self.itemurl_re)
        for link in xlink.extract_links(response):
            if itemre.search(link.url):
                yield Request(url=link.url, callback=self.parse_item)

    def parse_item(self, response):
        item = TestItem()
        m = self.name_re.search(response.body)
        if m:
            item['name'] = m.group(1)
        item['url'] = response.url
        m = self.price_re.search(response.body)
        if m:
            item['price'] = m.group(1)
        return item

def start_test_site(debug=False):
    root_dir = os.path.join(tests_datadir, "test_site")
    r = static.File(root_dir)
    r.putChild("redirect", util.Redirect("/redirected"))
    r.putChild("redirected", static.Data("Redirected here", "text/plain"))

    port = reactor.listenTCP(0, server.Site(r), interface="127.0.0.1")
    if debug:
        print("Test server running at http://localhost:%d/ - hit Ctrl-C to finish." \
            % port.getHost().port)
    return port


class CrawlerRun(object):
    """A class to run the crawler and keep track of events occurred"""

    def __init__(self):
        self.spider = None
        self.respplug = []
        self.reqplug = []
        self.itemresp = []
        self.signals_catched = {}

    def run(self):
        self.port = start_test_site()
        self.portno = self.port.getHost().port

        start_urls = [self.geturl("/"), self.geturl("/redirect")]

        for name, signal in vars(signals).items():
            if not name.startswith('_'):
                dispatcher.connect(self.record_signal, signal)

        self.crawler = get_crawler(TestSpider)
        self.crawler.signals.connect(self.item_scraped, signals.item_scraped)
        self.crawler.signals.connect(self.request_scheduled, signals.request_scheduled)
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

    def item_scraped(self, item, spider, response):
        self.itemresp.append((item, response))

    def request_scheduled(self, request, spider):
        self.reqplug.append((request, spider))

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
        self.run = CrawlerRun()
        yield self.run.run()
        self._assert_visited_urls()
        self._assert_scheduled_requests()
        self._assert_downloaded_responses()
        self._assert_scraped_items()
        self._assert_signals_catched()

    def _assert_visited_urls(self):
        must_be_visited = ["/", "/redirect", "/redirected",
                           "/item1.html", "/item2.html", "/item999.html"]
        urls_visited = set([rp[0].url for rp in self.run.respplug])
        urls_expected = set([self.run.geturl(p) for p in must_be_visited])
        assert urls_expected <= urls_visited, "URLs not visited: %s" % list(urls_expected - urls_visited)

    def _assert_scheduled_requests(self):
        self.assertEqual(6, len(self.run.reqplug))

        paths_expected = ['/item999.html', '/item2.html', '/item1.html']

        urls_requested = set([rq[0].url for rq in self.run.reqplug])
        urls_expected = set([self.run.geturl(p) for p in paths_expected])
        assert urls_expected <= urls_requested

    def _assert_downloaded_responses(self):
        # response tests
        self.assertEqual(6, len(self.run.respplug))

        for response, _ in self.run.respplug:
            if self.run.getpath(response.url) == '/item999.html':
                self.assertEqual(404, response.status)
            if self.run.getpath(response.url) == '/redirect':
                self.assertEqual(302, response.status)

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
        self.run.signals_catched[signals.spider_closed].pop('spider_stats', None) # XXX: remove for scrapy 0.17
        self.assertEqual({'spider': self.run.spider, 'reason': 'finished'},
                         self.run.signals_catched[signals.spider_closed])


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == 'runserver':
        start_test_site(debug=True)
        reactor.run()
