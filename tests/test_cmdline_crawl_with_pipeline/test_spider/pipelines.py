# -*- coding: utf-8 -*-

# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: https://docs.scrapy.org/en/latest/topics/item-pipeline.html


class TestSpiderPipeline(object):

    def open_spider(self, spider):
        pass

    def process_item(self, item, spider):
        return item


class TestSpiderExceptionPipeline(object):

    def open_spider(self, spider):
        raise Exception('exception')

    def process_item(self, item, spider):
        return item
