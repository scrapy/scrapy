"""Download handlers for http and https schemes"""
import logging
import asyncio

import aiohttp
from twisted.internet import defer

from scrapy.http import Headers
from scrapy.responsetypes import responsetypes

logger = logging.getLogger(__name__)


class HTTPDownloadHandler(object):

    def __init__(self, settings):
        self.settings = settings

    def download_request(self, request, spider):
        return _force_deferred(self._download_request(request, spider))

    async def _download_request(self, request, spider):
        """Return a deferred for the HTTP download"""
        headers=list((k.decode('latin1'), v.decode('latin1'))
                     for k, vs in request.headers.items()
                     for v in vs)

        jar = aiohttp.DummyCookieJar()
        async with aiohttp.ClientSession(auto_decompress=False, cookie_jar=jar) as session:
            aioresponse = await session.request(
                method=request.method,
                url=request.url,
                data=request.body,
                allow_redirects=False,
                headers=headers,
            )
            body = await aioresponse.read()
            status = aioresponse.status
            headers = Headers(aioresponse.raw_headers)
        respcls = responsetypes.from_args(headers=headers, url=request.url)
        return respcls(url=request.url, status=status, headers=headers, body=body)


def _force_deferred(coro):
    dfd = defer.Deferred().addCallback(lambda f: f.result())
    future = asyncio.ensure_future(coro)
    future.add_done_callback(dfd.callback)
    return dfd
