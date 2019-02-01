"""
HttpError Spider Middleware

See documentation in docs/topics/spider-middleware.rst
"""
import logging

from scrapy.exceptions import IgnoreRequest

logger = logging.getLogger(__name__)


class HttpError(IgnoreRequest):
    """A non-200 response was filtered"""

    def __init__(self, response, *args, **kwargs):
        self.response = response
        super(HttpError, self).__init__(*args, **kwargs)


class HttpErrorMiddleware(object):
    """Filter out unsuccessful (erroneous) HTTP responses so that spiders don't
    have to deal with them, which (most of the time) imposes an overhead,
    consumes more resources, and makes the spider logic more complex.

    According to the `HTTP standard`_, successful responses are those whose
    status codes are in the 200-300 range.

    .. _HTTP standard: https://www.w3.org/Protocols/rfc2616/rfc2616-sec10.html

    If you still want to process response codes outside that range, you can
    specify which response codes the spider is able to handle using the
    ``handle_httpstatus_list`` spider attribute or
    :setting:`HTTPERROR_ALLOWED_CODES` setting.

    For example, if you want your spider to handle 404 responses you can do
    this::

        class MySpider(CrawlSpider):
            handle_httpstatus_list = [404]

    .. reqmeta:: handle_httpstatus_list

    .. reqmeta:: handle_httpstatus_all

    The ``handle_httpstatus_list`` key of :attr:`Request.meta
    <scrapy.http.Request.meta>` can also be used to specify which response codes to
    allow on a per-request basis. You can also set the meta key ``handle_httpstatus_all``
    to ``True`` if you want to allow any response code for a request.

    Keep in mind, however, that it's usually a bad idea to handle non-200
    responses, unless you really know what you're doing.

    For more information see: `HTTP Status Code Definitions`_.

    .. _HTTP Status Code Definitions: https://www.w3.org/Protocols/rfc2616/rfc2616-sec10.html

    This spider middleware has the following settings:

    .. setting:: HTTPERROR_ALLOWED_CODES

    .. rubric:: HTTPERROR_ALLOWED_CODES

    Default: ``[]``

    Pass all responses with non-200 status codes contained in this list.

    .. setting:: HTTPERROR_ALLOW_ALL

    .. rubric:: HTTPERROR_ALLOW_ALL

    Default: ``False``

    Pass all responses, regardless of its status code.
    """

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings)

    def __init__(self, settings):
        self.handle_httpstatus_all = settings.getbool('HTTPERROR_ALLOW_ALL')
        self.handle_httpstatus_list = settings.getlist('HTTPERROR_ALLOWED_CODES')

    def process_spider_input(self, response, spider):
        if 200 <= response.status < 300:  # common case
            return
        meta = response.meta
        if 'handle_httpstatus_all' in meta:
            return
        if 'handle_httpstatus_list' in meta:
            allowed_statuses = meta['handle_httpstatus_list']
        elif self.handle_httpstatus_all:
            return
        else:
            allowed_statuses = getattr(spider, 'handle_httpstatus_list', self.handle_httpstatus_list)
        if response.status in allowed_statuses:
            return
        raise HttpError(response, 'Ignoring non-200 response')

    def process_spider_exception(self, response, exception, spider):
        if isinstance(exception, HttpError):
            spider.crawler.stats.inc_value('httperror/response_ignored_count')
            spider.crawler.stats.inc_value(
                'httperror/response_ignored_status_count/%s' % response.status
            )
            logger.info(
                "Ignoring response %(response)r: HTTP status code is not handled or not allowed",
                {'response': response}, extra={'spider': spider},
            )
            return []
