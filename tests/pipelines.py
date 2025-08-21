"""
Some pipelines used for testing
"""


class ZeroDivisionErrorPipeline:
    def open_spider(self):
        1 / 0

    def process_item(self, item):
        return item


class ProcessWithZeroDivisionErrorPipeline:
    def process_item(self, item):
        1 / 0
