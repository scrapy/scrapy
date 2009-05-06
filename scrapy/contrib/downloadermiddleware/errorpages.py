from scrapy.core.exceptions import HttpException

class ErrorPagesMiddleware(object):
    """This middleware allows the spiders to receive error (non 200) responses,
    the same way the receive normal responses"""

    def process_exception(self, request, exception, spider):
        if isinstance(exception, HttpException):
            statuses = getattr(spider, 'handle_httpstatus_list', None)
            httpstatus = exception.response.status
            if statuses and httpstatus in statuses:
                return exception.response

