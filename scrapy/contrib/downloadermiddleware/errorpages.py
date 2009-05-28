import warnings

from scrapy.core.exceptions import IgnoreRequest
from scrapy.utils.response import response_status_message

class ErrorPagesMiddleware(object):
    """This middleware filters out responses with status code others than 2XX
    or defined in spider handle_httpstatus_list attribute.

    TODO: move this mw to spidermiddleware and remove me
    """

    def __init__(self):
        warnings.warn("scrapy.contrib.downloadermiddleware.errorpages.ErrorPagesMiddleware downloader middleware is deprecated - use scrapy.contrib.spidermiddleware.httperror.HttpErrorMiddleware spider middleware instead",
            DeprecationWarning, stacklevel=2)

    def process_response(self, request, response, spider):
        status = response.status
        if 200 <= status < 300 or status in getattr(spider, 'handle_httpstatus_list', []):
            return response
        else:
            raise IgnoreRequest(response_status_message(status))

