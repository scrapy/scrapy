class TestSpiderPipeline:

    def open_spider(self, spider):
        pass

    def process_item(self, item, spider):
        return item


class TestSpiderExceptionPipeline:

    def open_spider(self, spider):
        raise Exception('exception')

    def process_item(self, item, spider):
        return item
