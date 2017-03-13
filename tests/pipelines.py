"""
Some pipelines used for testing
"""
from scrapy import ItemPipeline


class LegacyZeroDivisionErrorPipeline(object):

    def open_spider(self, spider):
        a = 1/0

    def process_item(self, item, spider):
        return item


class ZeroDivisionErrorPipeline(ItemPipeline):

    def open_spider(self, spider):
        a = 1/0

    def process_item(self, item, spider):
        return item
