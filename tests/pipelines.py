"""
Some pipelines used for testing
"""
from scrapy import BaseItemPipeline


class LegacyZeroDivisionErrorPipeline(object):

    def open_spider(self, spider):
        a = 1/0

    def process_item(self, item, spider):
        return item


class ZeroDivisionErrorPipeline(BaseItemPipeline):

    def open_spider(self, spider):
        a = 1/0

    def process_item(self, item, spider):
        return item
