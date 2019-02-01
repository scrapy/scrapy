"""
HTTP basic auth downloader middleware

See documentation in docs/topics/downloader-middleware.rst
"""

from w3lib.http import basic_auth_header

from scrapy import signals


class HttpAuthMiddleware(object):
    """This middleware authenticates all requests generated from certain spiders
    using `Basic access authentication`_ (aka. HTTP auth).

    To enable HTTP authentication from certain spiders, set the ``http_user``
    and ``http_pass`` attributes of those spiders.

    Example::

        from scrapy.spiders import CrawlSpider

        class SomeIntranetSiteSpider(CrawlSpider):

            http_user = 'someuser'
            http_pass = 'somepass'
            name = 'intranet.example.com'

            # .. rest of the spider code omitted ...

    .. _Basic access authentication: https://en.wikipedia.org/wiki/Basic_access_authentication
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
        auth = getattr(self, 'auth', None)
        if auth and b'Authorization' not in request.headers:
            request.headers[b'Authorization'] = auth
