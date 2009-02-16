# -*- coding: utf8 -*-
import re

from scrapy.xpath import HtmlXPathSelector
from scrapy.link.extractors import RegexLinkExtractor
from scrapy.contrib.spiders import CrawlSpider, Rule
from scrapy.contrib_exp import adaptors
from scrapy.utils.misc import items_to_csv
from googledir.items import GoogledirItem

class GoogleDirectorySpider(CrawlSpider):
    domain_name = 'google.com'
    start_urls = ['http://www.google.com/dirhp']

    rules = (
        Rule(RegexLinkExtractor(allow=('google.com/[A-Z][a-zA-Z_/]+$',),),
            'parse_category',
            follow=True,
        ),
    )
    csv_file = open('scraped_items.csv', 'ab+')
    
    def parse_category(self, response):
        # The selector we're going to use in order to extract data from the page
        hxs = HtmlXPathSelector(response)

        # The path to website links in directory page
        links = hxs.x('//td[descendant::a[contains(@href, "#pagerank")]]/following-sibling::td/font')

        # The list of functions to apply to an attribute before assigning its value
        adaptor_pipe = [adaptors.extract, adaptors.delist(''), adaptors.strip]
        adaptor_map = {
            'name': adaptor_pipe,
            'url': adaptor_pipe,
            'description': adaptor_pipe,
            }

        for link in links:
            item = GoogledirItem()
            item.set_adaptors(adaptor_map)

            item.attribute('name', link.x('a/text()'))
            item.attribute('url', link.x('a/@href'))
            item.attribute('description', link.x('font[2]/text()'))
            items_to_csv(self.csv_file, [item])
            yield item

SPIDER = GoogleDirectorySpider()
