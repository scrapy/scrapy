import asyncio
from typing import Self
import aiohttp

from scrapy import responsetypes
from scrapy.core.downloader.contextfactory import load_context_factory_from_settings
from scrapy.crawler import Crawler
from scrapy.http.headers import Headers
from scrapy.http.request import Request
from scrapy.http.response import Response
from scrapy.settings import Settings

from twisted.internet import Deferred
from twisted.internet.defer import ensureDeferred
from scrapy.spiders import Spider
from scrapy.utils.reactor import is_asyncio_reactor_installed
import ssl



class AiohttpHandler:

    def __init__(self, settings: Settings, crawler: Crawler):

        if(not is_asyncio_reactor_installed):
            raise Exception("Wrong reactor config")
        
        ssl_create_context = ssl.create_default_context()
        self.connector = aiohttp.TCPConnector(
            ssl_context= ssl_create_context,
            limit_per_host = settings.getint(
            "CONCURRENT_REQUESTS_PER_DOMAIN"
            )
            )
        self.session = aiohttp.ClientSession(
            connector= self.connector
        )
        self._crawler = crawler #idk about this just added bc all other major components do this

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls(crawler.settings, crawler)

    def download_request(self, request: Request, spider: Spider) -> Deferred[Response]:
        d = ensureDeferred(self._download_request(request))
        return d
    
    async def _download_request(self, request: Request):
        """download through aiohttp interface"""

        proxy = request.meta.get("proxy")
        url = request.url
        method = request.method 
        headers = request.headers.to_unicode_dict
        if(isinstance(request.cookies, dict)):
            cookies = request.cookies
        else:
            cookies = dict(map(lambda item: (item.name, item.value), request.cookies))
        body = request.body 
        encoding = request.encoding 

        self.session.cookie_jar.update_cookies(cookies)

        async with self.session.get(
            url=url,
            method = method,
            headers = headers,
            body = body,
            encoding = encoding,
            proxy = proxy,
            allow_redirects=False
        ) as response:
            
            body = await response.read()
            status = response.status
            headers = Headers(response.raw_headers) 

            respcls = responsetypes.from_args(headers=headers, url=request.url)
            return respcls(url=request.url, status=status, headers=headers, body=body)

    def close(self):
        task = asyncio.ensure_future(self._close())
        return

    async def _close(self):
        await self.session.close()
    