"""
This is a spider for the unittest sample site.

See scrapy/tests/test_engine.py for more info.
"""
import re

from scrapy.spider import BaseSpider
from scrapy.item import ScrapedItem
from scrapy.link import LinkExtractor
from scrapy.http import Request

class TestSpider(BaseSpider):
    domain_name = "scrapytest.org"
    extra_domain_names = ["localhost"]
    start_urls = ['http://localhost']

    itemurl_re = re.compile("item\d+.html")
    name_re = re.compile("<h1>(.*?)</h1>", re.M)
    price_re = re.compile(">Price: \$(.*?)<", re.M)

    def parse(self, response):
        xlink = LinkExtractor()
        itemre = re.compile(self.itemurl_re)
        for url in xlink.extract_urls(response):
            if itemre.search(url):
                yield Request(url=url, callback=self.parse_item)

    def parse_item(self, response):
        item = ScrapedItem()
        m = self.name_re.search(response.body.to_string())
        if m:
            item.name = m.group(1)
        item.url = response.url
        m = self.price_re.search(response.body.to_string())
        if m:
            item.price = m.group(1)
        return [item]
        

SPIDER = TestSpider()
