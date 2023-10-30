"""
HTTP basic auth downloader middleware

See documentation in docs/topics/downloader-middleware.rst
"""

from w3lib.http import basic_auth_header

from scrapy import signals
from scrapy.utils.url import url_is_from_any_domain


class HttpAuthMiddleware:
    """Set Basic HTTP Authorization header
    (http_user and http_pass spider class attributes)"""

    @classmethod
    def from_crawler(cls, crawler):
        o = cls()
        crawler.signals.connect(o.spider_opened, signal=signals.spider_opened)
        return o

    def spider_opened(self, spider):
        usr = getattr(spider, "http_user", "")
        pwd = getattr(spider, "http_pass", "")
        if usr or pwd:
            self.auth = basic_auth_header(usr, pwd)
            self.domain = spider.http_auth_domain

    def process_request(self, request, spider):
        auth = getattr(self, "auth", None)
        if auth and b"Authorization" not in request.headers:
            if not self.domain or url_is_from_any_domain(request.url, [self.domain]):
                request.headers[b"Authorization"] = auth
