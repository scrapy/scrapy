import sys, time
from twisted.internet import defer
from twisted.trial.unittest import TestCase
from subprocess import Popen, PIPE
from scrapy.spider import BaseSpider
from scrapy.http import Request
from scrapy.contrib.linkextractors.sgml import SgmlLinkExtractor
from scrapy.utils.test import get_crawler

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

def docrawl(spider, settings=None):
    crawler = get_crawler(settings)
    crawler.configure()
    crawler.crawl(spider)
    return crawler.start()

class CrawlTestCase(TestCase):

    def setUp(self):
        self.proc = Popen([sys.executable, '-u', '-m', 'scrapy.tests.mockserver'], stdout=PIPE)
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
