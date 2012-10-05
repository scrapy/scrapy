"""
HttpError Spider Middleware

See documentation in docs/topics/spider-middleware.rst
"""
from scrapy.exceptions import IgnoreRequest


class HttpError(IgnoreRequest):
    """A non-200 response was filtered"""

    def __init__(self, response, *args, **kwargs):
        self.response = response
        super(HttpError, self).__init__(*args, **kwargs)


class HttpErrorMiddleware(object):

    def process_spider_input(self, response, spider):
        if 200 <= response.status < 300: # common case
            return
        meta = response.meta
        if 'handle_httpstatus_all' in meta:
            return
        if 'handle_httpstatus_list' in meta:
            allowed_statuses = meta['handle_httpstatus_list']
        else:
            allowed_statuses = getattr(spider, 'handle_httpstatus_list', ())
        if response.status in allowed_statuses:
            return
        raise HttpError(response, 'Ignoring non-200 response')

    def process_spider_exception(self, response, exception, spider):
        if isinstance(exception, HttpError):
            return []
