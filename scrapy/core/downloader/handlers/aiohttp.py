import asyncio
from typing import Self

import aiohttp
from twisted.internet.defer import Deferred

from scrapy import responsetypes
from scrapy.crawler import Crawler
from scrapy.http.headers import Headers
from scrapy.http.request import Request
from scrapy.http.response import Response
from scrapy.settings import Settings
from scrapy.spiders import Spider
from scrapy.utils.reactor import (
    set_asyncio_event_loop,
    verify_installed_reactor,
)


class AiohttpHandler:
    def __init__(self, settings: Settings, crawler: Crawler):
        verify_installed_reactor(
            "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
        )

        self.loop = set_asyncio_event_loop(None)

        self.connector = aiohttp.TCPConnector(
            limit_per_host=settings.getint("CONCURRENT_REQUESTS_PER_DOMAIN"),
            loop=self.loop,
        )
        self.session = aiohttp.ClientSession(connector=self.connector, loop=self.loop)
        self._crawler = (
            crawler  # idk about this just added bc all other major components do this
        )

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls(crawler.settings, crawler)

    def download_request(self, request: Request, spider: Spider) -> Deferred[Response]:
        return Deferred.fromFuture(
            asyncio.ensure_future(self._download_request(request))
        )

    async def _download_request(self, request: Request):
        """download through aiohttp interface"""

        proxy = request.meta.get("proxy")
        url = request.url
        method = request.method
        body = request.body
        headers = None if request.headers is None else request.headers.to_unicode_dict()
        if isinstance(request.cookies, dict):
            cookies = request.cookies
        else:
            cookies = {
                str(item["name"]): str(item["value"]) for item in request.cookies
            }
        body = request.body
        # encoding = None if request.method == "GET" else request.encoding

        self.session.cookie_jar.update_cookies(cookies)

        async with self.session.request(
            url=url,
            method=method,
            proxy=proxy,
            data=body,
            headers=headers,
            allow_redirects=False,
        ) as response:
            body = await response.read()
            status = response.status
            new_headers = Headers(response.raw_headers)

            respcls = responsetypes.responsetypes.from_args(
                headers=new_headers, url=request.url
            )
            return respcls(
                url=request.url, status=status, headers=new_headers, body=body
            )

    def close(self):
        return Deferred.fromFuture(asyncio.ensure_future(self.session.close()))

    async def _close(self):
        await self.session.close()
