"""
HTTP basic auth downloader middleware

See documentation in docs/topics/downloader-middleware.rst
"""
import warnings

from w3lib.http import basic_auth_header

from scrapy import signals
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.httpobj import urlparse_cached
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
            if not hasattr(spider, "http_auth_domain"):
                warnings.warn(
                    "Using HttpAuthMiddleware without http_auth_domain is deprecated and can cause security "
                    "problems if the spider makes requests to several different domains. http_auth_domain "
                    "will be set to the domain of the first request, please set it to the correct value "
                    "explicitly.",
                    category=ScrapyDeprecationWarning,
                )
                self.domain_unset = True
            else:
                self.domain = spider.http_auth_domain
                self.domain_unset = False

    def process_request(self, request, spider):
        auth = getattr(self, "auth", None)
        if auth and b"Authorization" not in request.headers:
            domain = urlparse_cached(request).hostname
            if self.domain_unset:
                self.domain = domain
                self.domain_unset = False
            if not self.domain or url_is_from_any_domain(request.url, [self.domain]):
                request.headers[b"Authorization"] = auth
