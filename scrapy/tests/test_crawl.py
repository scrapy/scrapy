import sys, time
from twisted.internet import defer
from twisted.trial.unittest import TestCase
from subprocess import Popen, PIPE
from scrapy.spider import BaseSpider
from scrapy.http import Request
from scrapy.contrib.linkextractors.sgml import SgmlLinkExtractor
from scrapy.utils.test import get_crawler, get_testenv

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

def docrawl(spider, settings=None):
    crawler = get_crawler(settings)
    crawler.configure()
    crawler.crawl(spider)
    return crawler.start()

class CrawlTestCase(TestCase):

    def setUp(self):
        self.proc = Popen([sys.executable, '-u', '-m', 'scrapy.tests.mockserver'],
            stdout=PIPE, env=get_testenv())
        self.proc.stdout.readline()

    def tearDown(self):
        self.proc.kill()
        self.proc.wait()
        time.sleep(0.2)

    @defer.inlineCallbacks
    def test_follow_all(self):
        spider = FollowAllSpider()
        yield docrawl(spider)
        self.assertEqual(len(spider.urls_visited), 11) # 10 + start_url

    @defer.inlineCallbacks
    def test_delay(self):
        spider = FollowAllSpider()
        yield docrawl(spider, {"DOWNLOAD_DELAY": 0.3})
        t = spider.times[0]
        for t2 in spider.times[1:]:
            self.assertTrue(t2-t > 0.15, "download delay too small: %s" % (t2-t))
            t = t2

    @defer.inlineCallbacks
    def test_timeout_success(self):
        spider = DelaySpider(n=0.5)
        yield docrawl(spider)
        self.assertTrue(spider.t1 > 0)
        self.assertTrue(spider.t2 > 0)
        self.assertTrue(spider.t2 > spider.t1)

    @defer.inlineCallbacks
    def test_timeout_failure(self):
        spider = DelaySpider(n=0.5)
        yield docrawl(spider, {"DOWNLOAD_TIMEOUT": 0.35})
        self.assertTrue(spider.t1 > 0)
        self.assertTrue(spider.t2 == 0)
        self.assertTrue(spider.t2_err > 0)
        self.assertTrue(spider.t2_err > spider.t1)
