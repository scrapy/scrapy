# -*- coding: utf-8 -*-

# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy


class InternshalaItem(scrapy.Item):
    # define the fields for your item here like:
    internship_type = scrapy.Field()
    company_name = scrapy.Field()
    stipend = scrapy.Field()
    location = scrapy.Field()
    time_frame = scrapy.Field()
    pass
