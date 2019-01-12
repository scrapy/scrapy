"""
RetryMiddleware is used to retry temporary issues or bans where the response has to be
processed by spider before been retried.

You can issue a retry request by raising a `scrapy.exceptions.RetryRequest` exception inside a spider callback
"""

from scrapy.exceptions import RetryRequest
from scrapy.utils.retry import RetryHandler


class RetryMiddleware(object):

    def process_spider_output(self, response, result, spider):
        # work around until this is fixed https://github.com/scrapy/scrapy/issues/220
        try:
            for x in result:
                yield x
        except RetryRequest as e:
            res = self.process_spider_exception(response, e, spider)
            if res:
                for r in res:
                    yield r

    def process_spider_exception(self, response, exception, spider):
        if isinstance(exception, RetryRequest):
            request = response.request
            retry_handler = RetryHandler(spider, request)
            if retry_handler.is_exhausted():
                retry_handler.record_retry_failure(exception)
                return None
            else:
                new_req = retry_handler.make_retry_request()
                retry_handler.record_retry(new_req, exception)
                return [new_req]

        return None
