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


class Spider(object_ref):
    """This is the simplest spider, and the one from which every other spider
    must inherit (including spiders that come bundled with Scrapy, as well as spiders
    that you write yourself). It doesn't provide any special functionality. It just
    provides a default :meth:`start_requests` implementation which sends requests from
    the :attr:`start_urls` spider attribute and calls the spider's method ``parse``
    for each of the resulting responses.

    .. attribute:: allowed_domains

        List of domain names. If defined, any :class:`~scrapy.Request` that the
        spider yields that has a :class:`~scrapy.Request.url` outside the
        specified domains is filtered out.

    .. attribute:: download_maxsize

        Overrides :setting:`DOWNLOAD_MAXSIZE`

    .. attribute:: download_timeout

        Overrides :setting:`DOWNLOAD_TIMEOUT`

    .. attribute:: download_warnsize

        Overrides :setting:`DOWNLOAD_WARNSIZE`
    """

    #: A string which defines the name for this spider. The spider name is how
    #: the spider is located (and instantiated) by Scrapy, so it must be
    #: unique. However, nothing prevents you from instantiating more than one
    #: instance of the same spider. This is the most important spider attribute
    #: and it's required.
    #:
    #: If the spider scrapes a single domain, a common practice is to name the
    #: spider after the domain, with or without the `TLD`_. So, for example, a
    #: spider that crawls ``mywebsite.com`` would often be called
    #: ``mywebsite``.
    #:
    #: .. note:: In Python 2 this must be ASCII only.
    name = None

    #: A dictionary of settings that will be overridden from the project wide
    #: configuration when running this spider. It must be defined as a class
    #: attribute since the settings are updated before instantiation.
    #:
    #: For a list of available built-in settings see:
    #: :ref:`topics-settings-ref`.
    custom_settings = None

    def __init__(self, name=None, **kwargs):
        if name is not None:
            self.name = name
        elif not getattr(self, 'name', None):
            raise ValueError("%s must have a name" % type(self).__name__)
        self.__dict__.update(kwargs)
        if not hasattr(self, 'start_urls'):
            #: A list of URLs where the spider will begin to crawl from, when no
            #: particular URLs are specified. So, the first pages downloaded will be those
            #: listed here. The subsequent :class:`Request <scrapy.Request>` will be generated successively from data
            #: contained in the start URLs.
            self.start_urls = []

    @property
    def logger(self):
        """Python logger created with the Spider's :attr:`name`. You can use it to
        send log messages through it as described on
        :ref:`topics-logging-from-spiders`."""
        logger = logging.getLogger(self.name)
        return logging.LoggerAdapter(logger, {'spider': self})

    def log(self, message, level=logging.DEBUG, **kw):
        """Log the given message at the given log level

        This helper wraps a log call to the logger within the spider, and is
        kept only for backwards compatibility. Use the spider logger directly
        instead (e.g. Spider.logger.info('msg')) or use any other Python
        logger.

        For more information see :ref:`topics-logging-from-spiders`.
        """
        self.logger.log(level, message, **kw)

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        """This is the class method used by Scrapy to create your spiders.

        You probably won't need to override this directly because the default
        implementation acts as a proxy to the class constructor, calling
        it with the given arguments `args` and named arguments `kwargs`.

        Nonetheless, this method sets the :attr:`crawler` and :attr:`settings`
        attributes in the new instance so they can be accessed later inside the
        spider's code.

        :param crawler: crawler to which the spider will be bound
        :type crawler: :class:`~scrapy.crawler.Crawler` instance

        :param args: arguments passed to the class constructor
        :type args: list

        :param kwargs: keyword arguments passed to the class constructor
        :type kwargs: dict
        """
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
        #: This attribute is set by the :meth:`from_crawler` class method after
        #: initializating the class, and links to the
        #: :class:`~scrapy.crawler.Crawler` object to which this spider instance is
        #: bound.
        #:
        #: Crawlers encapsulate a lot of components in the project for their single
        #: entry access (such as extensions, middlewares, signals managers, etc).
        #: See :ref:`topics-api-crawler` to know more about them.
        self.crawler = crawler

        #: Configuration for running this spider. This is a
        #: :class:`~scrapy.settings.Settings` instance, see the
        #: :ref:`topics-settings` topic for a detailed introduction on this subject.
        self.settings = crawler.settings

        crawler.signals.connect(self.close, signals.spider_closed)

    def start_requests(self):
        """This method must return an iterable with the first Requests to crawl for
        this spider. It is called by Scrapy when the spider is opened for
        scraping. Scrapy calls it only once, so it is safe to implement
        :meth:`start_requests` as a generator.

        The default implementation generates ``Request(url, dont_filter=True)``
        for each url in :attr:`~scrapy.Spider.start_urls`.

        If you want to change the Requests used to start scraping a domain, this is
        the method to override. For example, if you need to start by logging in using
        a POST request, you could do::

            class MySpider(scrapy.Spider):
                name = 'myspider'

                def start_requests(self):
                    return [scrapy.FormRequest("http://www.example.com/login",
                                                formdata={'user': 'john', 'pass': 'secret'},
                                                callback=self.logged_in)]

                def logged_in(self, response):
                    # here you would extract links to follow and return Requests for
                    # each of them, with another callback
                    pass
        """
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

    def make_requests_from_url(self, url):
        """ This method is deprecated. """
        return Request(url, dont_filter=True)

    def parse(self, response):
        """This is the default callback used by Scrapy to process downloaded
        responses, when their requests don't specify a callback.

        The ``parse`` method is in charge of processing the response and returning
        scraped data and/or more URLs to follow. Other Requests callbacks have
        the same requirements as the :class:`Spider` class.

        This method, as well as any other Request callback, must return an
        iterable of :class:`Request <scrapy.Request>` and/or
        dicts or :class:`~scrapy.item.Item` objects.

        :param response: the response to parse
        :type response: :class:`Response <scrapy.http.Response>`
        """
        raise NotImplementedError('{}.parse callback is not defined'.format(self.__class__.__name__))

    @classmethod
    def update_settings(cls, settings):
        settings.setdict(cls.custom_settings or {}, priority='spider')

    @classmethod
    def handles_request(cls, request):
        return url_is_from_spider(request.url, cls)

    @staticmethod
    def close(spider, reason):
        """Called when the spider closes. This method provides a shortcut to
        signals.connect() for the :signal:`spider_closed` signal."""
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
