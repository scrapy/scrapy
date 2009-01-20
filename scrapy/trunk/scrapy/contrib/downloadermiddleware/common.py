"""
Common downloader middleare

See documentation in docs/ref/downloader-middleware.rst
"""

from scrapy.conf import settings

class CommonMiddleware(object):

    def __init__(self):
        self.header_accept = settings.get('REQUEST_HEADER_ACCEPT')
        self.header_accept_language = settings.get('REQUEST_HEADER_ACCEPT_LANGUAGE')

    def process_request(self, request, spider):
        request.headers.setdefault('Accept', self.header_accept)
        request.headers.setdefault('Accept-Language', self.header_accept_language)
        if request.method == 'POST':
            request.headers.setdefault('Content-Type', 'application/x-www-form-urlencoded')
            if request.body:
                request.headers.setdefault('Content-Length', '%d' % len(request.body))

