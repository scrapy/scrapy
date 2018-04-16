# -*- coding: utf-8 -*-
import scrapy
from scrapy.contrib.spiders import CrawlSpider, Rule
from scrapy.contrib.linkextractors.lxmlhtml import LxmlLinkExtractor


class OurspiderSpider(CrawlSpider):
    name = 'ourspider'
    allowed_domains = ['https://en.wikipedia.org']
    start_urls = ['https://en.wikipedia.org/wiki/Lewis_Tappan_Barney']

    rules = (Rule(LxmlLinkExtractor(allow=()), callback='parse_obj', follow=True),)

    #def start_requests(self):
        # yield scrapy.Request('https://en.wikipedia.org', meta={'bindaddress': ('1234:5678:111::0a', 0)})

    # def parse(self, response):
    #     pass

    def parse_obj(self,response):
        for link in LxmlLinkExtractor(allow=()).extract_links(response):
            print(link);
            # item = someItem()
            # item['url'] = link.url
