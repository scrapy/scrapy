import asyncio
from typing import Self
import aiohttp

from scrapy.core.downloader.contextfactory import load_context_factory_from_settings
from scrapy.crawler import Crawler
from scrapy.http.request import Request
from scrapy.settings import Settings
from twisted.internet import reactor
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

    def download_request(self, request: Request):
        d = self._download_request(request)
        #needa pick apart client response into the response they use in their code
        return d
    
    async def _download_request(self, request: Request) :
        """pure aiohttp function for separation of concerns and all"""

        proxy = request.meta.get("proxy")
        url = request.url
        method = request.method  # You can change this if needed, e.g., 'POST'
        headers = {'User-Agent': 'my-app', 'Accept-Encoding': 'gzip, deflate'}
        cookies = {'session_id': '1234'}
        body = request.body  # GET requests typically don't have a body, but you can add it for other methods like POST
        encoding = request.encoding  # Can be set in Accept-Encoding or as a custom header


        if proxy:
            pass
        else:
            async with self.session.get(
                url=url,
                method = method,
                headers = headers,
                body = body,
                encoding = encoding
                                        ) as response:
                return await response
            

    def close(self):
        task = asyncio.ensure_future(self._close())
        return

    async def _close(self):
        await self.session.close()
    