"""
Base class for Scrapy spiders

See documentation in docs/topics/spiders.rst
"""
import logging
from typing import Optional, List

from scrapy import signals
from scrapy.http import Request
from scrapy.http.cookies import CookieJar
from scrapy.utils.trackref import object_ref
from scrapy.utils.url import url_is_from_spider


class Spider(object_ref):
    """Base class for scrapy spiders. All spiders must inherit from this
    class.
    """

    name: Optional[str] = None
    custom_settings: Optional[dict] = None
    _cookie_jar: Optional[CookieJar] = None

    def __init__(self, name=None, **kwargs):
        if name is not None:
            self.name = name
        elif not getattr(self, 'name', None):
            raise ValueError(f"{type(self).__name__} must have a name")
        self.__dict__.update(kwargs)
        if not hasattr(self, 'start_urls'):
            self.start_urls = []

    @property
    def logger(self):
        logger = logging.getLogger(self.name)
        return logging.LoggerAdapter(logger, {'spider': self})

    def log(self, message, level=logging.DEBUG, **kw):
        """Log the given message at the given log level

        This helper wraps a log call to the logger within the spider, but you
        can use it directly (e.g. Spider.logger.info('msg')) or use any other
        Python logger too.
        """
        self.logger.log(level, message, **kw)

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = cls(*args, **kwargs)
        spider._set_crawler(crawler)
        return spider

    def _set_crawler(self, crawler):
        self.crawler = crawler
        self.settings = crawler.settings
        crawler.signals.connect(self.close, signals.spider_closed)

    def start_requests(self):
        if not self.start_urls and hasattr(self, 'start_url'):
            raise AttributeError(
                "Crawling could not start: 'start_urls' not found "
                "or empty (but found 'start_url' attribute instead, "
                "did you miss an 's'?)")
        for url in self.start_urls:
            yield Request(url, dont_filter=True)

    def _parse(self, response, **kwargs):
        return self.parse(response, **kwargs)

    def parse(self, response, **kwargs):
        raise NotImplementedError(f'{self.__class__.__name__}.parse callback is not defined')

    @classmethod
    def update_settings(cls, settings):
        settings.setdict(cls.custom_settings or {}, priority='spider')

    @classmethod
    def handles_request(cls, request):
        return url_is_from_spider(request.url, cls)

    @staticmethod
    def close(spider, reason):
        closed = getattr(spider, 'closed', None)
        if callable(closed):
            return closed(reason)

    def __str__(self):
        return f"<{type(self).__name__} {self.name!r} at 0x{id(self):0x}>"

    __repr__ = __str__

    def set_cookie_jar(self, cj: CookieJar):
        self._cookie_jar = cj

    def save_cookies(self):  # todo should return sesssion Id
        # TODO
        pass

    def initialize_cookiejar(self, session_id):
        # TODO
        pass

    def add_cookie(self, cookie):
        self._cookie_jar.set_cookie(cookie)

    def get_cookie(self, name):
        return self._cookie_jar.get_cookie(name)

    def get_cookies(self, names: List[str] = None, return_type=list):
        if isinstance(return_type, list):
            cookies_list = self._cookie_jar.list_from_cookiejar()
            if names is not None:
                return list(filter(lambda cookie: cookie.name in names, cookies_list))
            return cookies_list
        else:
            cookies_dict = self._cookie_jar.dict_from_cookiejar()
            if names is not None:
                return {name: cookies_dict[name] for name in names}
            return cookies_dict

    def clear_cookies(self):
        self._cookie_jar = CookieJar()


# Top-level imports
from scrapy.spiders.crawl import CrawlSpider, Rule
from scrapy.spiders.feed import XMLFeedSpider, CSVFeedSpider
from scrapy.spiders.sitemap import SitemapSpider
