class SpiderMiddleware(object):
    def process_spider_input(self, response, spider):
        pass

    def process_spider_output(self, response, result, spider):
        return result

    def process_spider_exception(self, repsonse, exception, spider):
        pass

    def process_start_requests(self, start_requests, spider):
        return start_requests

    @classmethod
    def from_crawler(cls, crawler):
        pass
