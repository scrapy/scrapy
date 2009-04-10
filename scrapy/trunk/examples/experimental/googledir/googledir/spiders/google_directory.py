# -*- coding: utf8 -*-
import re

from scrapy.xpath import HtmlXPathSelector
from scrapy.contrib.spiders import CrawlSpider, rule
from scrapy.utils.misc import items_to_csv

from googledir.items import GoogledirItem, GoogledirItemAdaptor

class GoogleDirectorySpider(CrawlSpider):
    domain_name = 'google.com'
    start_urls = ['http://www.google.com/dirhp']

    rules = (
        rule('google.com/[A-Z][a-zA-Z_/]+$', 'parse_category', follow=True),
    )
    csv_file = open('scraped_items.csv', 'ab+')
    
    def parse_category(self, response):
        # The selector we're going to use in order to extract data from the page
        hxs = HtmlXPathSelector(response)

        # The path to website links in directory page
        links = hxs.x('//td[descendant::a[contains(@href, "#pagerank")]]/following-sibling::td/font')

        for link in links:
            extractor = GoogledirItemAdaptor()
            extractor.name =  link.x('a/text()')
            extractor.url = link.x('a/@href')
            extractor.description = link.x('font[2]/text()')
            item = extractor.item_instance
            yield item

SPIDER = GoogleDirectorySpider()
