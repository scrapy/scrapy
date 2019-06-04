# -*- coding: utf-8 -*-
import scrapy


class BlogPythonSpider(scrapy.Spider):
    name = 'blog_python'
    allowed_domains = ['blog.python.org']
    start_urls = ['https://blog.python.org/']

    def parse(self, response):
        blog_list = response.xpath('//div[@class="blog-posts hfeed"]/div//div[@class="blog-posts hfeed"]/div')
        for blog in blog_list:
            title = response.xpath('./h3/a/text()').extract_first()
            time = response.xpath('./h2/span/text()').extract_first()
            
            yield {'title': title, 'time': time}
