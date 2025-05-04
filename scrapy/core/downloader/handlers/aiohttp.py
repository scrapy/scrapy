import asyncio
from typing import Self
import aiohttp

from scrapy.core.downloader.contextfactory import load_context_factory_from_settings
from scrapy.crawler import Crawler
from scrapy.settings import Settings
from twisted.internet import reactor
from scrapy.utils.reactor import is_asyncio_reactor_installed



class AiohttpHandler:

    def __init__(self, settings: Settings, crawler: Crawler):
        if(not is_asyncio_reactor_installed or settings.get):
            raise Exception("Wrong reactor config")
        
        self._pool =
        self._crawler = crawler
        

            

    def download_request(request):
        d = deferred_download_request(request)
        return d

    def deferred_download_request(self, request) -> Deferred[Response]:
        return defer.fromCoroutine(_download(request))

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls(crawler.settings, crawler)
    
    async def _download_request(request):
        """pure aiohttp function for separation of concerns and all"""
        session = aiohttp.ClientSession()
        async with session:
            async with session.get(url= request) as response:
                return await response
    