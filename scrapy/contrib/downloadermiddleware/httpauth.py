"""
HTTP basic auth downloader middleware

See documentation in docs/topics/downloader-middleware.rst
"""

from w3lib.http import basic_auth_header
from scrapy.utils.python import WeakKeyCache


class HttpAuthMiddleware(object):
    """Set Basic HTTP Authorization header
    (http_user and http_pass spider class attributes)"""

    def __init__(self):
        self._cache = WeakKeyCache(self._authorization)

    def _authorization(self, spider):
        usr = getattr(spider, 'http_user', '')
        pwd = getattr(spider, 'http_pass', '')
        if usr or pwd:
            return basic_auth_header(usr, pwd)

    def process_request(self, request, spider):
        auth = self._cache[spider]
        if auth and 'Authorization' not in request.headers:
            request.headers['Authorization'] = auth
