# -*- coding: utf-8 -*-
import scrapy


class MilSpider(scrapy.Spider):
    name = 'mil'
    allowed_domains = ['milsims.com.au']
    start_urls = ['http://www.milsims.com.au/catalog/1746'
                  
    ]

    def parse(self, response):
        for title in response.css('div.views-field-title'):
            yield {'title': title.css('a ::text').extract_first()}

        for price in response.css('div.views-field-phpcode'):
            yield {'price': price.css('a ::text').extract_first()}

        next_page = response.css('li.pager-next a::attr(href)').extract_first()
        if next_page is not None:
            next_page = response.urljoin(next_page)
            yield scrapy.Request(next_page, callback=self.parse)
