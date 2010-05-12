"""
HttpError Spider Middleware

See documentation in docs/topics/spider-middleware.rst
"""
from scrapy.core.exceptions import IgnoreRequest


class HttpErrorException(IgnoreRequest):
    """A non-200 response was filtered"""

    def __init__(self, response, *args, **kwargs):
        self.response = response
        super(HttpErrorException, self).__init__(*args, **kwargs)


class HttpErrorMiddleware(object):

    def process_spider_input(self, response, spider):
        if 200 <= response.status < 300: # common case
            return
        if 'handle_httpstatus_list' in response.request.meta:
            allowed_statuses = response.request.meta['handle_httpstatus_list']
        else:
            allowed_statuses = getattr(spider, 'handle_httpstatus_list', ())
        if response.status in allowed_statuses:
            return
        raise HttpErrorException(response, 'Ignoring non-200 response')

