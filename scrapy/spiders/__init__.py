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
    from collections.abc import AsyncIterator, Iterable

    from twisted.internet.defer import Deferred

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.http.request import CallbackT
    from scrapy.settings import BaseSettings, _SettingsKeyT
    from scrapy.utils.log import SpiderLoggerAdapter


class Spider(object_ref):
    """Base class that any spider must subclass.

    It provides a default :meth:`start` implementation that sends
    requests based on the :attr:`start_urls` class attribute and calls the
    :meth:`parse` method for each response.
    """

    name: str
    custom_settings: dict[_SettingsKeyT, Any] | None = None

    #: Start URLs. See :meth:`start`.
    start_urls: list[str]

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
        from scrapy.utils.log import SpiderLoggerAdapter

        logger = logging.getLogger(self.name)
        return SpiderLoggerAdapter(logger, {"spider": self})

    def log(self, message: Any, level: int = logging.DEBUG, **kw: Any) -> None:
        """Log the given message at the given log level

        This helper wraps a log call to the logger within the spider, but you
        can use it directly (e.g. Spider.logger.info('msg')) or use any other
        Python logger too.
        """
        self.logger.log(level, message, **kw)

    @classmethod
    def from_crawler(cls, crawler: Crawler, *args: Any, **kwargs: Any) -> Self:
        spider = cls(*args, **kwargs)
        spider._set_crawler(crawler)
        return spider

    def _set_crawler(self, crawler: Crawler) -> None:
        self.crawler: Crawler = crawler
        self.settings: BaseSettings = crawler.settings
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
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore", category=ScrapyDeprecationWarning, module=r"^scrapy\.spiders$"
            )
            for item_or_request in self.start_requests():
                yield item_or_request

    def start_requests(self) -> Iterable[Any]:
        warnings.warn(
            (
                "The Spider.start_requests() method is deprecated, use "
                "Spider.start() instead. If you are calling "
                "super().start_requests() from a Spider.start() override, "
                "iterate super().start() instead."
            ),
            ScrapyDeprecationWarning,
            stacklevel=2,
        )
        if not self.start_urls and hasattr(self, "start_url"):
            raise AttributeError(
                "Crawling could not start: 'start_urls' not found "
                "or empty (but found 'start_url' attribute instead, "
                "did you miss an 's'?)"
            )
        for url in self.start_urls:
            yield Request(url, dont_filter=True)

    def _parse(self, response: Response, **kwargs: Any) -> Any:
        return self.parse(response, **kwargs)

    if TYPE_CHECKING:
        parse: CallbackT
    else:

        def parse(self, response: Response, **kwargs: Any) -> Any:
            raise NotImplementedError(
                f"{self.__class__.__name__}.parse callback is not defined"
            )

    @classmethod
    def update_settings(cls, settings: BaseSettings) -> None:
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
