"""
HTTP/FTP Authorization downloader middleware

See documentation in docs/topics/downloader-middleware.rst
"""
from six.moves.urllib.parse import urlunparse

from w3lib.http import basic_auth_header

from scrapy import signals
from scrapy.utils.httpobj import urlparse_cached


def credstrip_url(parsed_url):
    """Strip username and password from an urlparse'd URL"""
    return urlunparse((
        parsed_url.scheme,
        parsed_url.netloc.split('@')[-1],
        parsed_url.path,
        parsed_url.params,
        parsed_url.query,
        parsed_url.fragment))


class AuthMiddleware(object):
    """
    Populate authorization credentials for HTTP and FTP requests.

    For http(s):// requests, set Basic HTTP Authorization header,
    either from http_user and http_pass spider attributes,
    or from URL netloc parsing.

    Also handle FTP credentials from ftp://user:password@... URLs,
    populating request's meta accordingly.
    """

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
        url = urlparse_cached(request)
        if url.scheme.startswith('http'):
            # do not override Auth header set priorly
            if 'Authorization' in request.headers:
                return

            new_url = None
            # credentials from URL override spider attributes
            if url.username or url.password:
                auth = basic_auth_header(url.username, url.password)

                # no credentials in new url
                new_url = credstrip_url(url)

            else:
                auth = getattr(self, 'auth', None)

            if auth:
                request.headers['Authorization'] = auth
                if new_url:
                    return request.replace(url=new_url)

        elif url.scheme.startswith('ftp'):
            if url.username or url.password:
                # priorly set credentials take precedence
                request.meta.setdefault('ftp_user', url.username)
                request.meta.setdefault('ftp_password', url.password)

                # no credentials in new url
                return request.replace(url=credstrip_url(url))
