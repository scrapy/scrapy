"""
Some pipelines used for testing
"""


class ZeroDivisionErrorPipeline(object):

    def open_spider(self, spider):
        raise ZeroDivisionError("division by zero")

    def process_item(self, item, spider):
        return item
