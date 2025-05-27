from __future__ import annotations

from typing import TYPE_CHECKING

import aiohttp

from scrapy import responsetypes
from scrapy.http.headers import Headers
from scrapy.utils.defer import deferred_from_coro
from scrapy.utils.reactor import (
    is_asyncio_reactor_installed,
    set_asyncio_event_loop,
)

if TYPE_CHECKING:
    from twisted.internet.defer import Deferred
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.http.request import Request
    from scrapy.http.response import Response
    from scrapy.spiders import Spider


class AiohttpDownloadHandler:
    def __init__(self, crawler: Crawler):
        if not is_asyncio_reactor_installed():
            raise ValueError(
                "AiohttpDownloadHandler requires the asyncio Twisted "
                "reactor. Make sure you have it configured in the "
                "TWISTED_REACTOR setting. See the asyncio documentation "
                "of Scrapy for more information."
            )

        self.loop = set_asyncio_event_loop(None)

        settings = crawler.settings

        self.connector = aiohttp.TCPConnector(
            limit_per_host=settings.getint("CONCURRENT_REQUESTS_PER_DOMAIN"),
            loop=self.loop,
        )
        self.session = aiohttp.ClientSession(connector=self.connector, loop=self.loop)
        self._crawler = crawler

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls(crawler)

    def download_request(self, request: Request, spider: Spider) -> Deferred[Response]:
        return deferred_from_coro(self._download_request(request))

    async def _download_request(self, request: Request):
        """download through aiohttp interface"""

        proxy = request.meta.get("proxy")
        timeout = aiohttp.ClientTimeout(total=request.meta.get("download_timeout"))

        url = request.url
        method = request.method
        body = request.body
        headers = None if request.headers is None else request.headers.to_unicode_dict()

        async with self.session.request(
            url=url,
            method=method,
            proxy=proxy,
            data=body,
            headers=headers,
            allow_redirects=False,
            timeout=timeout,
            ssl=False,
        ) as response:
            body = await response.read()
            status = response.status
            new_headers = Headers(response.raw_headers)

            respcls = responsetypes.responsetypes.from_args(
                headers=new_headers, url=request.url, body=body
            )
            protocol = f"HTTP/{response.version.major}.{response.version.minor}"
            return respcls(
                url=request.url,
                status=status,
                headers=new_headers,
                body=body,
                protocol=protocol,
            )

    def close(self):
        return deferred_from_coro(self.session.close())
