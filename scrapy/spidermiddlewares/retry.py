"""
RetryMiddleware is used to retry temporary issues or bans where the response has to be
processed by spider before been retried.

You can return a `scrapy.http.request.retry.RetryRequest` from a spider callback to retry a request
"""
import logging

from scrapy.utils.retry import RetryHandler
from scrapy.http import RetryRequest


logger = logging.getLogger(__name__)


class RetryMiddleware(object):

    def __init__(self, settings):
        self.enabled = settings.getbool('RETRY_ENABLED')

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings)

    def process_spider_output(self, response, result, spider):
        for x in result:
            if isinstance(x, RetryRequest):
                original_request = x.request
                if not self.enabled:
                    logger.debug(
                        "Found a retry request but request retrying is disabled: %(request)s",
                        {'request': original_request},
                        extra={'spider': spider}
                    )
                    continue

                reason = x.reason or 'Retry Request'
                retry_handler = RetryHandler(spider, original_request)
                if retry_handler.is_exhausted():
                    retry_handler.record_retry_failure(reason)
                    continue
                else:
                    new_req = retry_handler.make_retry_request()
                    retry_handler.record_retry(new_req, reason)
                    yield new_req
            else:
                yield x
