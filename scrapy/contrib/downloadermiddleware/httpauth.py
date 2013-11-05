"""
HTTP basic auth downloader middleware

See documentation in docs/topics/downloader-middleware.rst
"""

from w3lib.http import basic_auth_header


class HttpAuthMiddleware(object):
    """Set Basic HTTP Authorization header
    (http_user and http_pass spider class attributes)"""

    def process_request(self, request, spider):
        usr = getattr(spider, 'http_user', '')
        pwd = getattr(spider, 'http_pass', '')
        if (usr or pwd) and 'Authorization' not in request.headers:
            request.headers['Authorization'] = basic_auth_header(usr, pwd)
