from typing import Self
import httpx
from twisted.internet.defer import ensureDeferred

from scrapy.crawler import Crawler
from scrapy.http import HtmlResponse, JsonResponse, Response
from scrapy.settings import BaseSettings


class HTTPXDownloadHandler:
    def __init__(self, settings: BaseSettings, crawler=None):
        self.settings = settings

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls(crawler.settings, crawler)

    def download_request(self, request, spider):
        return ensureDeferred(self._download(request))

    async def _download(self, request):
        async with httpx.AsyncClient() as client:
            resp = await client.request(
                method=request.method,
                url=str(request.url),
                headers=request.headers.to_unicode_dict(),
                content=request.body or None,
                timeout=10,
            )
            content_type = resp.headers.get("content-type", "").lower()
            response_cls = Response
            if "text/html" in content_type:
                response_cls = HtmlResponse
            elif "application/json" in content_type or "json" in content_type:
                response_cls = JsonResponse
            return response_cls(
                url=str(request.url),
                status=resp.status_code,
                headers=resp.headers,
                body=resp.content,
                request=request,
            )
