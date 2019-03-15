import logging

from scrapy import Request
from scrapy.utils.retry import RetryHandler


logger = logging.getLogger(__name__)


class RetryMiddleware(object):
    """
    RetryMiddleware is used to retry requests that have temporary issues or bans where the response has to be
    processed by spider before been retried.

    You can retry a request by calling :meth:`retry_request <scrapy.http.Response.retry_request>` method on a
    :class:`Response <scrapy.http.Response>` instance and yielding the returned :class:`Request <scrapy.http.Request>`
    that is marked to be retried.

    example::

        def parse(self, response):
            if self.needs_to_be_retried(response):
                yield response.retry_request('Invalid response')

    RetryMiddleware can be configured through the following settings which are
    also used in :class:`RetryDownloaderMiddleware <scrapy.downloadermiddlewares.retry.RetryMiddleware>`.

    * :setting:`RETRY_ENABLED`
    * :setting:`RETRY_TIMES`
    * :setting:`RETRY_PRIORITY_ADJUST`
    """

    def __init__(self, settings):
        self.enabled = settings.getbool('RETRY_ENABLED')

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings)

    def process_spider_output(self, response, result, spider):
        for x in result:
            if isinstance(x, Request):
                if x.is_marked_for_retry():
                    if not self.enabled:
                        logger.debug(
                            "Dropping retry request because request retrying is disabled: %(request)s",
                            {'request': x},
                            extra={'spider': spider}
                        )
                        continue

                    reason = x.get_retry_reason() or 'Retry Requested'
                    retry_handler = RetryHandler(spider, x)
                    if retry_handler.is_exhausted():
                        retry_handler.record_retry_failure(reason)
                    else:
                        new_req = retry_handler.make_retry_request()
                        retry_handler.record_retry(new_req, reason)
                        new_req.unmark_as_retry()
                        yield new_req
                else:
                    yield x
            else:
                yield x
