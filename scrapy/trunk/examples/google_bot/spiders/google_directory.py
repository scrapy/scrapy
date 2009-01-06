# -*- coding: utf8 -*-
from scrapy.xpath import HtmlXPathSelector
from scrapy.item import ScrapedItem
from scrapy.contrib import adaptors
from scrapy.contrib.spiders import CrawlSpider, Rule
from scrapy.link.extractors import RegexLinkExtractor
from scrapy.utils.misc import items_to_csv

class GoogleDirectorySpider(CrawlSpider):
    domain_name = 'google.com'
    start_urls = ['http://www.google.com/dirhp']

    rules = (
        Rule(RegexLinkExtractor(allow=('google.com/[A-Z][a-zA-Z_/]+$', ), ),
            'parse_category',
            follow=True,
        ),
    )

    adaptor_pipe = [adaptors.extract, adaptors.Delist(), adaptors.strip]
    csv_file = open('scraped_items.csv', 'w')

    def parse_category(self, response):
        items = [] # The item (links to websites) list we're going to return
        hxs = HtmlXPathSelector(response) # The selector we're going to use in order to extract data from the page
        links = hxs.x('//td[descendant::a[contains(@href, "#pagerank")]]/following-sibling::td/font')

        for link in links:
            item = ScrapedItem()
            item.set_adaptors({
                'name': self.adaptor_pipe,
                'url': self.adaptor_pipe,
                'description': self.adaptor_pipe,
            })

            item.attribute('name', link.x('a/text()'))
            item.attribute('url', link.x('a/@href'))
            item.attribute('description', link.x('font[2]/text()'))
            items.append(item)

        items_to_csv(self.csv_file, items)
        return items

SPIDER = GoogleDirectorySpider()
