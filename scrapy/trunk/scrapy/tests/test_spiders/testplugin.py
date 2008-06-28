"""
This is a spider for the unittest sample site.

See scrapy/tests/test_engine.py for more info.
"""
import re

from scrapy.spider import BaseSpider
from scrapy.item import ScrapedItem
from decobot.utils.link_extraction import follow_link_pattern

class TestSpider(BaseSpider):
    domain_name = "scrapytest.org"
    extra_domain_names = ["localhost"]
    start_urls = ['http://localhost']

    itemurl_re = re.compile("item\d+.html")
    name_re = re.compile("<h1>(.*?)</h1>", re.M)
    price_re = re.compile(">Price: \$(.*?)<", re.M)

    def parse(self, response):
        return follow_link_pattern(response.body.to_string(), self.parse_item, response.url, self.itemurl_re)

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
