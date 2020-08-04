from scrapy.http import Request


class RequestInOrderMiddleware:
    def process_spider_output(self, response, result, spider):
        return (self._preserve_in_order(r, spider) for r in result or ())

    def process_start_requests(self, start_requests, spider):
        return (self._preserve_in_order(r, spider) for r in start_requests or ())

    def _preserve_in_order(self, smth, spider):
        self.__preserve_in_order(smth, spider)
        return smth

    def __preserve_in_order(self, smth, spider):

        if not isinstance(smth, Request):
            return

        request = smth

        if getattr(spider, 'requests_in_order_of_scheduling', None) is None:
            setattr(spider, 'requests_in_order_of_scheduling', list())

        spider.requests_in_order_of_scheduling.append(request)
