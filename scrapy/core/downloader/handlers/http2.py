from __future__ import annotations

from time import time
from typing import TYPE_CHECKING
from urllib.parse import urldefrag

from twisted.internet.error import TimeoutError
from twisted.web.client import URI

from scrapy.core.downloader.contextfactory import load_context_factory_from_settings
from scrapy.core.downloader.webclient import _parse
from scrapy.core.http2.agent import H2Agent, H2ConnectionPool, ScrapyProxyH2Agent
from scrapy.utils.python import to_bytes

if TYPE_CHECKING:
    from twisted.internet.base import DelayedCall
    from twisted.internet.defer import Deferred
    from twisted.web.iweb import IPolicyForHTTPS

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.http import Request, Response
    from scrapy.settings import Settings
    from scrapy.spiders import Spider


class H2DownloadHandler:
    def __init__(self, settings: Settings, crawler: Crawler):
        self._crawler = crawler

        from twisted.internet import reactor

        self._pool = H2ConnectionPool(reactor, settings)
        self._context_factory = load_context_factory_from_settings(settings, crawler)

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls(crawler.settings, crawler)

    def download_request(self, request: Request, spider: Spider) -> Deferred[Response]:
        agent = ScrapyH2Agent(
            context_factory=self._context_factory,
            pool=self._pool,
            crawler=self._crawler,
        )
        return agent.download_request(request, spider)

    def close(self) -> None:
        self._pool.close_connections()


class ScrapyH2Agent:
    _Agent = H2Agent
    _ProxyAgent = ScrapyProxyH2Agent

    def __init__(
        self,
        context_factory: IPolicyForHTTPS,
        pool: H2ConnectionPool,
        connect_timeout: int = 10,
        bind_address: bytes | None = None,
        crawler: Crawler | None = None,
    ) -> None:
        self._context_factory = context_factory
        self._connect_timeout = connect_timeout
        self._bind_address = bind_address
        self._pool = pool
        self._crawler = crawler

    def _get_agent(self, request: Request, timeout: float | None) -> H2Agent:
        from twisted.internet import reactor

        bind_address = request.meta.get("bindaddress") or self._bind_address
        proxy = request.meta.get("proxy")
        if proxy:
            _, _, proxy_host, proxy_port, proxy_params = _parse(proxy)
            scheme = _parse(request.url)[0]

            if scheme == b"https":
                # ToDo
                raise NotImplementedError(
                    "Tunneling via CONNECT method using HTTP/2.0 is not yet supported"
                )
            return self._ProxyAgent(
                reactor=reactor,
                context_factory=self._context_factory,
                proxy_uri=URI.fromBytes(to_bytes(proxy, encoding="ascii")),
                connect_timeout=timeout,
                bind_address=bind_address,
                pool=self._pool,
            )

        return self._Agent(
            reactor=reactor,
            context_factory=self._context_factory,
            connect_timeout=timeout,
            bind_address=bind_address,
            pool=self._pool,
        )

    def download_request(self, request: Request, spider: Spider) -> Deferred[Response]:
        from twisted.internet import reactor

        timeout = request.meta.get("download_timeout") or self._connect_timeout
        agent = self._get_agent(request, timeout)

        start_time = time()
        d = agent.request(request, spider)
        d.addCallback(self._cb_latency, request, start_time)

        timeout_cl = reactor.callLater(timeout, d.cancel)
        d.addBoth(self._cb_timeout, request, timeout, timeout_cl)
        return d

    @staticmethod
    def _cb_latency(
        response: Response, request: Request, start_time: float
    ) -> Response:
        request.meta["download_latency"] = time() - start_time
        return response

    @staticmethod
    def _cb_timeout(
        response: Response, request: Request, timeout: float, timeout_cl: DelayedCall
    ) -> Response:
        if timeout_cl.active():
            timeout_cl.cancel()
            return response

        url = urldefrag(request.url)[0]
        raise TimeoutError(f"Getting {url} took longer than {timeout} seconds.")
