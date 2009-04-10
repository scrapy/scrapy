# -*- coding: utf8 -*-
import re

from scrapy.xpath import HtmlXPathSelector
from scrapy.link.extractors import RegexLinkExtractor
from scrapy.contrib.spiders import CrawlSpider, Rule
from googledir.items import GoogledirItem

class GoogleDirectorySpider(CrawlSpider):
    domain_name = 'google.com'
    start_urls = ['http://www.google.com/dirhp']

    rules = (
        Rule(RegexLinkExtractor(allow='google.com/[A-Z][a-zA-Z_/]+$'),
            'parse_category',
            follow=True,
        ),
    )
    
    def parse_category(self, response):
        # The selector we're going to use in order to extract data from the page
        hxs = HtmlXPathSelector(response)

        # The path to website links in directory page
        links = hxs.x('//td[descendant::a[contains(@href, "#pagerank")]]/following-sibling::td/font')

        for link in links:
            item = GoogledirItem()

            item.name = link.x('a/text()').extract()
            item.url = link.x('a/@href').extract()
            item.description = link.x('font[2]/text()')
            yield item

SPIDER = GoogleDirectorySpider()
