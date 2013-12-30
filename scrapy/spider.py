"""
Base class for Scrapy spiders

See documentation in docs/topics/spiders.rst
"""
from scrapy import log
from scrapy.http import Request
from scrapy.utils.trackref import object_ref
from scrapy.utils.url import url_is_from_spider
from scrapy.utils.deprecate import create_deprecated_class


class Spider(object_ref):
    """Base class for scrapy spiders. All spiders must inherit from this
    class.
    """

    name = None

    def __init__(self, name=None, **kwargs):
        if name is not None:
            self.name = name
        elif not getattr(self, 'name', None):
            raise ValueError("%s must have a name" % type(self).__name__)
        self.__dict__.update(kwargs)
        if not hasattr(self, 'start_urls'):
            self.start_urls = []

    def log(self, message, level=log.DEBUG, **kw):
        """Log the given messages at the given log level. Always use this
        method to send log messages from your spider
        """
        log.msg(message, spider=self, level=level, **kw)

    def set_crawler(self, crawler):
        assert not hasattr(self, '_crawler'), "Spider already bounded to %s" % crawler
        self._crawler = crawler

    @property
    def crawler(self):
        assert hasattr(self, '_crawler'), "Spider not bounded to any crawler"
        return self._crawler

    @property
    def settings(self):
        return self.crawler.settings

    def start_requests(self):
        for url in self.start_urls:
            yield self.make_requests_from_url(url)

    def make_requests_from_url(self, url):
        return Request(url, dont_filter=True)

    def parse(self, response):
        raise NotImplementedError

    @classmethod
    def handles_request(cls, request):
        return url_is_from_spider(request.url, cls)

    def __str__(self):
        return "<%s %r at 0x%0x>" % (type(self).__name__, self.name, id(self))

    __repr__ = __str__


BaseSpider = create_deprecated_class('BaseSpider', Spider)


class ObsoleteClass(object):
    def __init__(self, message):
        self.message = message

    def __getattr__(self, name):
        raise AttributeError(self.message)

spiders = ObsoleteClass("""
"from scrapy.spider import spiders" no longer works - use "from scrapy.project import crawler" and then access crawler.spiders attribute"
""")

