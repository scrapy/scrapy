"""
DefaultHeaders downloader middleware

See documentation in docs/ref/downloader-middleware.rst
"""

from scrapy.conf import settings

class DefaultHeadersMiddleware(object):

    def __init__(self):
        self.default_headers = settings.get('DEFAULT_REQUEST_HEADERS')

    def process_request(self, request, spider):
        for k, v in self.default_headers.iteritems():
            if v:
                request.headers.setdefault(k, v)
