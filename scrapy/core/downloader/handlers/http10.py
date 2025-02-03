"""Download handlers for http and https schemes"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.misc import build_from_crawler, load_object
from scrapy.utils.python import to_unicode

if TYPE_CHECKING:
    from twisted.internet.defer import Deferred
    from twisted.internet.interfaces import IConnector

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy import Request, Spider
    from scrapy.core.downloader.contextfactory import ScrapyClientContextFactory
    from scrapy.core.downloader.webclient import ScrapyHTTPClientFactory
    from scrapy.crawler import Crawler
    from scrapy.http import Response
    from scrapy.settings import BaseSettings


class HTTP10DownloadHandler:
    lazy = False

    def __init__(self, settings: BaseSettings, crawler: Crawler):
        warnings.warn(
            "HTTP10DownloadHandler is deprecated and will be removed in a future Scrapy version.",
            category=ScrapyDeprecationWarning,
            stacklevel=2,
        )
        self.HTTPClientFactory: type[ScrapyHTTPClientFactory] = load_object(
            settings["DOWNLOADER_HTTPCLIENTFACTORY"]
        )
        self.ClientContextFactory: type[ScrapyClientContextFactory] = load_object(
            settings["DOWNLOADER_CLIENTCONTEXTFACTORY"]
        )
        self._settings: BaseSettings = settings
        self._crawler: Crawler = crawler

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls(crawler.settings, crawler)

    def download_request(self, request: Request, spider: Spider) -> Deferred[Response]:
        """Return a deferred for the HTTP download"""
        factory = self.HTTPClientFactory(request)
        self._connect(factory)
        return factory.deferred

    def _connect(self, factory: ScrapyHTTPClientFactory) -> IConnector:
        from twisted.internet import reactor

        host, port = to_unicode(factory.host), factory.port
        if factory.scheme == b"https":
            client_context_factory = build_from_crawler(
                self.ClientContextFactory,
                self._crawler,
            )
            return reactor.connectSSL(host, port, factory, client_context_factory)
        return reactor.connectTCP(host, port, factory)
