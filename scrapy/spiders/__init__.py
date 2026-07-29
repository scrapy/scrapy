"""
Base class for Scrapy spiders

See documentation in docs/topics/spiders.rst
"""

from __future__ import annotations

import logging
import warnings
from typing import TYPE_CHECKING, Any, cast

from scrapy import signals
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.http import Request, Response
from scrapy.utils.trackref import object_ref
from scrapy.utils.url import url_is_from_spider

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from twisted.internet.defer import Deferred

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.http.request import CallbackT
    from scrapy.settings import BaseSettings
    from scrapy.utils.log import SpiderLoggerAdapter


class Spider(object_ref):
    """Base class that any spider must subclass.

    It provides a default :meth:`start` implementation that sends
    requests based on the :attr:`start_urls` class attribute and calls the
    :meth:`parse` method for each response.

    Like :ref:`Scrapy components <topics-components>`, spiders are
    :ref:`initialized from the crawler <from-crawler>`, through
    :meth:`~scrapy.Spider.from_crawler`, and can be :ref:`configured through
    settings <component-settings>`, which they may also override through
    :attr:`custom_settings` or :meth:`~scrapy.Spider.update_settings`.
    """

    #: The name of this spider.
    #:
    #: Every spider needs one: :class:`Spider` raises :exc:`ValueError` on
    #: initialization if it has no name. You usually define it as a class
    #: attribute, but you can also pass it at initialization time instead, e.g.
    #: ``CrawlerProcess.crawl(MySpider, name="myspider")`` when :ref:`running
    #: Scrapy from a script <run-from-script>`.
    #:
    #: The name is also how Scrapy locates a spider: the default :ref:`spider
    #: loader <topics-api-spiderloader>` indexes the spiders of your project by
    #: name, which is what allows the :command:`crawl` command to find them,
    #: and the :command:`runspider` command ignores spider classes that have no
    #: name. Names should hence be unique within a project; the default spider
    #: loader warns about duplicates and keeps only one of the matching spider
    #: classes. Nothing prevents you from running more than one instance of the
    #: same spider, though, and a custom spider loader (see
    #: :setting:`SPIDER_LOADER_CLASS`) may map names to spider classes in a
    #: completely different way.
    #:
    #: If the spider scrapes a single domain, a common practice is to name the
    #: spider after that domain, replacing dots with underscores. For example, a
    #: spider that crawls ``books.toscrape.com`` would often be called
    #: ``books_toscrape_com``.
    name: str

    #: Settings that override the project-wide configuration when running this
    #: spider. It must be defined as a class attribute, since the settings are
    #: updated before instantiation.
    #:
    #: See :ref:`topics-settings-ref` for a list of built-in settings.
    #:
    #: .. seealso:: :meth:`~scrapy.Spider.update_settings`, a more verbose but
    #:    more flexible alternative, which allows setting values based on other
    #:    settings or on spider attributes, using priorities other than
    #:    ``'spider'``, and extending the settings of a base spider class.
    #:
    #:    :ref:`spider-settings`
    custom_settings: dict[str, Any] | None = None

    #: Start URLs. See :meth:`start`.
    start_urls: list[str]

    #: This attribute is set by the :meth:`~scrapy.Spider.from_crawler` class
    #: method after initializing the class, and links to the
    #: :class:`~scrapy.crawler.Crawler` object to which this spider instance is
    #: bound.
    #:
    #: Crawlers encapsulate a lot of components in the project for their single
    #: entry access (such as extensions, middlewares, signals managers, etc).
    #: See :ref:`topics-api-crawler` for details.
    crawler: Crawler

    #: Configuration for running this spider.
    #: See :ref:`topics-settings` for details.
    settings: BaseSettings

    def __init__(self, name: str | None = None, **kwargs: Any):
        if name is not None:
            self.name: str = name
        elif not getattr(self, "name", None):
            raise ValueError(f"{type(self).__name__} must have a name")
        self.__dict__.update(kwargs)
        if not hasattr(self, "start_urls"):
            self.start_urls: list[str] = []

    @property
    def logger(self) -> SpiderLoggerAdapter:
        """Python logger created with the spider's :attr:`name`.

        Use it to send log messages. See :ref:`topics-logging-from-spiders` for
        details.
        """
        # circular import
        from scrapy.utils.log import SpiderLoggerAdapter  # noqa: PLC0415

        logger = logging.getLogger(self.name)
        return SpiderLoggerAdapter(logger, {"spider": self})

    def log(self, message: Any, level: int = logging.DEBUG, **kw: Any) -> None:
        """Log the given message at the given log level

        This helper wraps a log call to the logger within the spider, but you
        can use it directly (e.g. Spider.logger.info('msg')) or use any other
        Python logger too.
        """
        warnings.warn(
            "Spider.log() is deprecated, use methods of Spider.logger instead.",
            ScrapyDeprecationWarning,
            stacklevel=2,
        )
        self.logger.log(level, message, **kw)

    @classmethod
    def from_crawler(cls, crawler: Crawler, *args: Any, **kwargs: Any) -> Self:
        """Return a new spider instance bound to *crawler*.

        You probably won't need to override this directly because the default
        implementation acts as a proxy to the ``__init__()`` method, calling
        it with the given arguments *args* and named arguments *kwargs*, which
        is how :ref:`spider arguments <spiderargs>` reach a spider.

        Nonetheless, this method sets the :attr:`crawler` and :attr:`settings`
        attributes in the new instance so they can be accessed later inside the
        spider's code.

        .. seealso:: :ref:`from-crawler`

        .. versionchanged:: 2.11

            The settings in ``crawler.settings`` can now be modified in this
            method, which is handy if you want to modify them based on
            arguments. As a consequence, these settings aren't the final values
            as they can be modified later by e.g. :ref:`add-ons
            <topics-addons>`. For the same reason, most of the
            :class:`~scrapy.crawler.Crawler` attributes aren't initialized at
            this point.

            The settings are final and those
            :class:`~scrapy.crawler.Crawler` attributes are initialized by the
            time the :meth:`start` method runs and the :signal:`engine_started`
            signal is sent, which is the earliest point where your spider code
            can rely on them.
        """
        spider = cls(*args, **kwargs)
        spider._set_crawler(crawler)
        return spider

    def _set_crawler(self, crawler: Crawler) -> None:
        self.crawler = crawler
        self.settings = crawler.settings
        crawler.signals.connect(self.close, signals.spider_closed)

    async def start(self) -> AsyncIterator[Any]:
        """Yield the initial :class:`~scrapy.Request` objects to send.

        .. versionadded:: 2.13

        For example:

        .. code-block:: python

            from scrapy import Request, Spider


            class MySpider(Spider):
                name = "myspider"

                async def start(self):
                    yield Request("https://toscrape.com/")

        The default implementation reads URLs from :attr:`start_urls` and
        yields a request for each with :attr:`~scrapy.Request.dont_filter`
        enabled. It is functionally equivalent to:

        .. code-block:: python

            async def start(self):
                for url in self.start_urls:
                    yield Request(url, dont_filter=True)

        You can also yield :ref:`items <topics-items>`. For example:

        .. code-block:: python

            async def start(self):
                yield {"foo": "bar"}

        To write spiders that work on Scrapy versions lower than 2.13,
        define also a synchronous ``start_requests()`` method that returns an
        iterable. For example:

        .. code-block:: python

            def start_requests(self):
                yield Request("https://toscrape.com/")

        .. seealso:: :ref:`start-requests`
        """
        for url in self.start_urls:
            yield Request(url, dont_filter=True)

    def _parse(self, response: Response, **kwargs: Any) -> Any:
        return self.parse(response, **kwargs)

    if TYPE_CHECKING:
        parse: CallbackT
    else:

        def parse(self, response: Response, **kwargs: Any) -> Any:
            """Handle *response*, returning scraped data and/or more URLs to
            follow.

            Scrapy calls this method for the responses of requests that do not
            define a callback. Other request callbacks have the same
            requirements as this method.

            It must return a :class:`~scrapy.Request` object, an :ref:`item
            object <topics-items>`, an iterable of :class:`~scrapy.Request`
            objects and/or :ref:`item objects <topics-items>`, or ``None``.
            """
            raise NotImplementedError(
                f"{self.__class__.__name__}.parse callback is not defined"
            )

    @classmethod
    def update_settings(cls, settings: BaseSettings) -> None:
        """Modify *settings*, the settings of the spider.

        This method is called during the initialization of a spider instance.
        It can add or update the spider's configuration values. It is a class
        method, meaning that it is called on the :class:`~scrapy.Spider` class
        and allows all instances of the spider to share the same configuration.

        While per-spider settings can be set in :attr:`custom_settings`, using
        this method allows you to dynamically add, remove or change settings
        based on other settings, spider attributes or other factors, and to use
        setting priorities other than ``'spider'``. Also, it's easy to extend
        this method in a subclass by overriding it, while doing the same with
        :attr:`custom_settings` can be hard.

        For example, suppose a spider needs to modify :setting:`FEEDS`:

        .. code-block:: python

            import scrapy


            class MySpider(scrapy.Spider):
                name = "myspider"
                custom_feed = {
                    "/home/user/documents/items.json": {
                        "format": "json",
                        "indent": 4,
                    }
                }

                @classmethod
                def update_settings(cls, settings):
                    super().update_settings(settings)
                    settings.setdefault("FEEDS", {}).update(cls.custom_feed)
        """
        settings.setdict(cls.custom_settings or {}, priority="spider")

    @classmethod
    def handles_request(cls, request: Request) -> bool:
        return url_is_from_spider(request.url, cls)

    @staticmethod
    def close(spider: Spider, reason: str) -> Deferred[None] | None:
        closed = getattr(spider, "closed", None)
        if callable(closed):
            return cast("Deferred[None] | None", closed(reason))
        return None

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.name!r} at 0x{id(self):0x}>"


# Top-level imports
from scrapy.spiders.crawl import CrawlSpider, Rule
from scrapy.spiders.feed import CSVFeedSpider, XMLFeedSpider
from scrapy.spiders.sitemap import SitemapSpider

__all__ = [
    "CSVFeedSpider",
    "CrawlSpider",
    "Rule",
    "SitemapSpider",
    "Spider",
    "XMLFeedSpider",
]
