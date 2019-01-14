"""
RetryMiddleware is used to retry temporary issues or bans where the response has to be
processed by spider before been retried.

You can issue a retry request by raising a `scrapy.exceptions.RetryRequest` exception inside a spider callback
"""
import logging

from scrapy.exceptions import RetryRequest
from scrapy.utils.retry import RetryHandler, is_retrying_enabled_on_request


logger = logging.getLogger(__name__)


class RetryMiddleware(object):

    def __init__(self, settings):
        self.enabled = settings.getbool('RETRY_ENABLED')

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings)

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
            if not self.enabled:
                logger.debug(
                    "Found a retry request but request retrying is disabled: %(request)s",
                    {'request': request},
                    extra={'spider': spider}
                )
                return None

            if not is_retrying_enabled_on_request(request):
                logger.debug(
                    "Found a retry request on a request that has retrying disabled: %(request)s",
                    {'request': request},
                    extra={'spider': spider}
                )
                return None

            retry_handler = RetryHandler(spider, request)
            if retry_handler.is_exhausted():
                retry_handler.record_retry_failure(exception)
                return None
            else:
                new_req = retry_handler.make_retry_request()
                retry_handler.record_retry(new_req, exception)
                return [new_req]

        return None
