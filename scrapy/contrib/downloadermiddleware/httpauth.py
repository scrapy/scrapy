"""
HTTP basic auth downloader middleware

See documentation in docs/topics/downloader-middleware.rst
"""

from scrapy.utils.request import request_authenticate

class HttpAuthMiddleware(object):
    """This middleware allows spiders to use HTTP auth in a cleaner way
    (http_user and http_pass spider class attributes)"""

    def process_request(self, request, spider):
        http_user = getattr(spider, 'http_user', '')
        http_pass = getattr(spider, 'http_pass', '')
        if http_user or http_pass:
            request_authenticate(request, http_user, http_pass)
