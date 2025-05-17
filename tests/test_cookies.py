import json

from twisted.internet import defer
from twisted.trial.unittest import TestCase

from scrapy.crawler import CrawlerRunner
from scrapy.http import Request
from tests.mockserver import MockServer
from tests.spiders import MetaSpider


class CookiesSpider(MetaSpider):
    name = "cookies"

    def start_requests(self):
        url = self.mockserver.url("/echo2/")
        for status in [200, 302, 503]:
            # Response params that mockserver will return
            body = {
                "status": status,
                "headers": {
                    "Set-cookie": f"status={status}",
                },
                "body": "<html></html>",
            }

            if status == 302:
                body["headers"]["location"] = self.mockserver.url("/")

            yield Request(
                url,
                callback=self.parse,
                meta={"cookiejar": status},
                body=json.dumps(body),
            )

    def parse(self, response):
        pass

    def close(self, spider):
        mw = [
            m
            for m in self.crawler.engine.downloader.middleware.middlewares
            if "Cookies" in str(type(m))
        ][0]
        jars_data = {}
        for k, jar in mw.jars.items():
            jars_data[k] = {
                s: v.value for s, v in jar._cookies["127.0.0.1"]["/echo2"].items()
            }
        self.crawler.stats._stats["cookies_values"] = jars_data


class CookiesTestCase(TestCase):
    def setUp(self):
        self.mockserver = MockServer()
        self.mockserver.__enter__()
        self.runner = CrawlerRunner()

    def tearDown(self):
        self.mockserver.__exit__(None, None, None)

    @defer.inlineCallbacks
    def test_cookies(self):
        crawler = CrawlerRunner().create_crawler(CookiesSpider)
        yield crawler.crawl(mockserver=self.mockserver)
        cookies_stats = crawler.stats._stats.get("cookies_values")
        expected_cookies = {
            200: {"status": "200"},
            302: {"status": "302"},
            503: {"status": "503"},
        }
        self.assertEqual(cookies_stats, expected_cookies)
