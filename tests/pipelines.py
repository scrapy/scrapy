"""
Some pipelines used for testing
"""


class ZeroDivisionErrorPipeline:

    def open_spider(self, spider):
        a = 1 / 0

    def process_item(self, item, spider):
        return item


class ProcessWithZeroDivisionErrorPipiline:

    def process_item(self, item, spider):
        1 / 0
