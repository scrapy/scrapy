import sys, time
from twisted.internet import defer
from twisted.trial.unittest import TestCase, SkipTest
from subprocess import Popen
from scrapy.spider import BaseSpider
from scrapy.http import Request
from scrapy.contrib.linkextractors.sgml import SgmlLinkExtractor
from scrapy.utils.test import get_crawler

class FollowAllSpider(BaseSpider):

    name = 'follow'
    start_urls = ["http://localhost:8998/follow?total=10&show=5&order=rand"]
    link_extractor = SgmlLinkExtractor()

    def __init__(self):
        self.urls_visited = []
        self.times = []

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
        self.proc = Popen([sys.executable, '-m', 'scrapy.tests.mockserver'])
        time.sleep(0.2)

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
        # FIXME: this test fails because Scrapy leaves the reactor dirty with
        # callLater calls when download delays are used. This test should be
        # enabled after this bug is fixed.
        raise SkipTest("disabled due to a reactor leak in the scrapy downloader")

        spider = FollowAllSpider()
        yield docrawl(spider)
        t = spider.times[0]
        for y in spider.times[1:]:
            self.assertTrue(y-t > 0.5, "download delay too small: %s" % (y-t))
