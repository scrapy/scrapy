"""
Scrapy engine tests
"""

import sys
import os
import urlparse
import unittest

from twisted.internet import reactor
from twisted.web import server, resource, static, util

#class TestResource(resource.Resource):
#    isLeaf = True
#
#    def render_GET(self, request):
#        return "hello world!"

def start_test_site():
    root_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), "sample_data", "test_site")
    r = static.File(root_dir)
#    r.putChild("test", TestResource())
    r.putChild("redirect", util.Redirect("/redirected"))
    r.putChild("redirected", static.Data("Redirected here", "text/plain"))

    port = reactor.listenTCP(0, server.Site(r), interface="127.0.0.1")
    return port


class CrawlingSession(object):

    def __init__(self):
        self.domain = 'scrapytest.org'
        self.spider = None
        self.respplug = []
        self.reqplug = []
        self.itemresp = []
        self.signals_catched = {}
        self.wasrun = False

    def run(self):
        self.port = start_test_site()
        self.portno = self.port.getHost().port

        from scrapy.spider import spiders
        spiders.spider_modules = ['scrapy.tests.test_spiders']
        spiders.reload()

        self.spider = spiders.fromdomain(self.domain)
        if self.spider:
            self.spider.start_urls = [
                self.geturl("/"),
                self.geturl("/redirect"),
                ]

            from scrapy.core import signals
            from scrapy.core.manager import scrapymanager
            from scrapy.core.engine import scrapyengine
            from pydispatch import dispatcher

            dispatcher.connect(self.record_signal, signals.engine_started)
            dispatcher.connect(self.record_signal, signals.engine_stopped)
            dispatcher.connect(self.record_signal, signals.domain_opened)
            dispatcher.connect(self.record_signal, signals.domain_idle)
            dispatcher.connect(self.record_signal, signals.domain_closed)
            dispatcher.connect(self.item_scraped, signals.item_scraped)
            dispatcher.connect(self.request_received, signals.request_received)
            dispatcher.connect(self.response_downloaded, signals.response_downloaded)

            scrapymanager.runonce(self.domain)
            self.port.stopListening()
            self.wasrun = True

    def geturl(self, path):
        return "http://localhost:%s%s" % (self.portno, path)

    def getpath(self, url):
        u = urlparse.urlparse(url)
        return u.path

    def item_scraped(self, item, spider, response):
        self.itemresp.append((item, response))

    def request_received(self, request, spider):
        self.reqplug.append((request, spider))

    def response_downloaded(self, response, spider):
        self.respplug.append((response, spider))

    def record_signal(self, *args, **kwargs):
        """Record a signal and its parameters"""
        signalargs = kwargs.copy()
        sig = signalargs.pop('signal')
        signalargs.pop('sender', None)
        self.signals_catched[sig] = signalargs

session = CrawlingSession()


class EngineTest(unittest.TestCase):

    def setUp(self):
        if not session.wasrun:
            session.run()

            # disable extensions that cause problems with tests (probably
            # because they leave the reactor in an unclean state)
            from scrapy.conf import settings
            settings.overrides['CLUSTER_MANAGER_ENABLED'] = 0

    def test_spider_locator(self):
        """
        Check the spider is loaded and located properly via the SpiderLocator
        """
        assert session.spider is not None
        self.assertEqual(session.spider.domain_name, session.domain)

    def test_visited_urls(self):
        """
        Make sure certain URls were actually visited
        """
        # expected urls that should be visited
        must_be_visited = ["/", "/redirect", "/redirected", 
                           "/item1.html", "/item2.html", "/item999.html"]

        urls_visited = set([rp[0].url for rp in session.respplug])
        urls_expected = set([session.geturl(p) for p in must_be_visited])
        assert urls_expected <= urls_visited, "URLs not visited: %s" % list(urls_expected - urls_visited)

    def test_requests_received(self):
        """
        Check requests received
        """
        # 3 requests should be received from the spider. start_urls and redirects don't count
        self.assertEqual(3, len(session.reqplug))

        paths_expected = ['/item999.html', '/item2.html', '/item1.html']

        urls_requested = set([rq[0].url for rq in session.reqplug])
        urls_expected = set([session.geturl(p) for p in paths_expected])
        assert urls_expected <= urls_requested

    def test_responses_downloaded(self):
        """
        Check responses downloaded
        """
        # response tests
        self.assertEqual(6, len(session.respplug))

        for response, spider in session.respplug:
            if session.getpath(response.url) == '/item999.html':
                self.assertEqual('404', response.status)
            if session.getpath(response.url) == '/redirect':
                self.assertEqual('302', response.status)
            self.assertEqual(response.domain, spider.domain_name)

    def test_item_data(self):
        """
        Check item data
        """
        # item tests
        self.assertEqual(2, len(session.itemresp))
        for item, response in session.itemresp:
            self.assertEqual(item.url, response.url)
            if 'item1.html' in item.url:
                self.assertEqual('Item 1 name', item.name)
                self.assertEqual('100', item.price)
            if 'item2.html' in item.url:
                self.assertEqual('Item 2 name', item.name)
                self.assertEqual('200', item.price)

    def test_signals(self):
        """
        Check signals were sent properly
        """
        from scrapy.core import signals

        assert signals.engine_started in session.signals_catched
        assert signals.engine_stopped in session.signals_catched
        assert signals.domain_opened in session.signals_catched
        assert signals.domain_idle in session.signals_catched
        assert signals.domain_closed in session.signals_catched

        self.assertEqual({'domain': session.domain, 'spider': session.spider},
                         session.signals_catched[signals.domain_opened])
        self.assertEqual({'domain': session.domain, 'spider': session.spider},
                         session.signals_catched[signals.domain_idle])
        self.assertEqual({'domain': session.domain, 'spider': session.spider, 'status': 'finished'},
                         session.signals_catched[signals.domain_closed])

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == 'runserver':
        port = start_test_site()
        print "Test server running at http://localhost:%d/ - hit Ctrl-C to finish." % port.getHost().port
        reactor.run()
    else:
        unittest.main()
