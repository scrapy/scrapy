"""
HTTP basic auth downloader middleware

See documentation in docs/topics/downloader-middleware.rst
"""

from w3lib.http import basic_auth_header

from scrapy import signals

from six.moves.urllib.parse import urlparse


class AuthMiddleware(object):
    """Set Basic HTTP Authorization header
    (http_user and http_pass spider class attributes)"""

    @classmethod
    def from_crawler(cls, crawler):
        o = cls()
        crawler.signals.connect(o.spider_opened, signal=signals.spider_opened)
        return o

    def spider_opened(self, spider):
        usr = getattr(spider, 'http_user', '')
        pwd = getattr(spider, 'http_pass', '')
        if usr or pwd:
            self.auth = basic_auth_header(usr, pwd)

    def process_request(self, request, spider):
        auth = getattr(self, 'auth', None)
        if auth and 'Authorization' not in request.headers:
            request.headers['Authorization'] = auth

        # credentials from url are supposed to override spider settings
        url = urlparse(request.url)
        if url.username and url.password:
            if url.scheme.startswith('ftp'):
                request.meta['ftp_user'] = url.username
                request.meta['ftp_password'] = url.password
            elif url.scheme.startswith('http'):
                request.headers['Authorization'] = basic_auth_header(url.username, url.password)

            # no credentials in new url
            new_url = url.scheme + '://' + url.hostname + url.path
            return request.replace(url=new_url)
