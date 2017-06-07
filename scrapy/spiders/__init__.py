"""
Base class for Scrapy spiders

See documentation in docs/topics/spiders.rst
"""
import logging
import warnings

from scrapy import signals
from scrapy.http import Request
from scrapy.utils.trackref import object_ref
from scrapy.utils.url import url_is_from_spider
from scrapy.utils.deprecate import create_deprecated_class
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.deprecate import method_is_overridden

# 所有爬虫的基类，用户定义的爬虫必须从这个类继承
class Spider(object_ref):
    """Base class for scrapy spiders. All spiders must inherit from this
    class.
    """
	
	# 定义Spider名字的字符串，用于定位并初始化spider，必须唯一
	# 一般做法是该网站加后缀_spider
    name = None
    custom_settings = None

	# 初始化爬虫的名字和start_urls这两个值
    def __init__(self, name=None, **kwargs):
        if name is not None:
            self.name = name
        elif not getattr(self, 'name', None):
            raise ValueError("%s must have a name" % type(self).__name__)
        self.__dict__.update(kwargs)
		# spider最开始从该列表开始进行爬取，后续的url将从获得的数据中提取
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

    def set_crawler(self, crawler):
        warnings.warn("set_crawler is deprecated, instantiate and bound the "
                      "spider to this crawler with from_crawler method "
                      "instead.",
                      category=ScrapyDeprecationWarning, stacklevel=2)
        assert not hasattr(self, 'crawler'), "Spider already bounded to a " \
                                             "crawler"
        self._set_crawler(crawler)

    def _set_crawler(self, crawler):
        self.crawler = crawler
        self.settings = crawler.settings
        crawler.signals.connect(self.close, signals.spider_closed)

	# 读取start_urls内的所有地址，调用make_requests_from_url()为每个地址生成一个Request对象后返回这些对象的迭代器。
	# 交给Scrapy下载并返回response
	# 该方法仅仅调用一次
    def start_requests(self):
        cls = self.__class__
        if method_is_overridden(cls, Spider, 'make_requests_from_url'):
            warnings.warn(
                "Spider.make_requests_from_url method is deprecated; it "
                "won't be called in future Scrapy releases. Please "
                "override Spider.start_requests method instead (see %s.%s)." % (
                    cls.__module__, cls.__name__
                ),
            )
            for url in self.start_urls:
                yield self.make_requests_from_url(url)
        else:
            for url in self.start_urls:
                yield Request(url, dont_filter=True)

	# 生成Request对象的函数，默认的回调函数是parse(),提交方法是GET方法
    def make_requests_from_url(self, url):
        """ This method is deprecated. """
        return Request(url, dont_filter=True)

	# 解析response内容，并返回Item或Requests(需指定回调函数)。用户必须实现这个类
	# Item传给Item pipline去做持久化 ， 
	# Requests交由Scrapy下载，并由指定的回调函数处理.一直进行循环，直到处理完所有的数据为止。
    def parse(self, response):
        raise NotImplementedError

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
        return "<%s %r at 0x%0x>" % (type(self).__name__, self.name, id(self))

    __repr__ = __str__


BaseSpider = create_deprecated_class('BaseSpider', Spider)


class ObsoleteClass(object):
    def __init__(self, message):
        self.message = message

    def __getattr__(self, name):
        raise AttributeError(self.message)

spiders = ObsoleteClass(
    '"from scrapy.spider import spiders" no longer works - use '
    '"from scrapy.spiderloader import SpiderLoader" and instantiate '
    'it with your project settings"'
)

# Top-level imports
from scrapy.spiders.crawl import CrawlSpider, Rule
from scrapy.spiders.feed import XMLFeedSpider, CSVFeedSpider
from scrapy.spiders.sitemap import SitemapSpider
