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
        """Return a deferred for the HTTP download"""
        headers=list((k.decode('latin1'), v.decode('latin1'))
                     for k, vs in request.headers.items()
                     for v in vs)

        dfd = _force_deferred(
            aiohttp.request(
                method=request.method,
                url=request.url,
                data=request.body,
                allow_redirects=False,
                headers=headers,
            ))

        def _on_response(aioresponse):
            return _force_deferred(aioresponse.read()).addCallback(
                _on_body, aioresponse=aioresponse)

        def _on_body(body, aioresponse):
            url = request.url
            status = aioresponse.status
            headers = Headers(
                (k.encode('latin1'), [v.encode('latin1')])
                for k, v in aioresponse.headers.items()
            )
            respcls = responsetypes.from_args(headers=headers, url=url)
            return respcls(url=url, status=status, headers=headers, body=body,
                           flags=[])

        return dfd.addCallback(_on_response)


def _force_deferred(coro):
    dfd = defer.Deferred().addCallback(lambda f: f.result())
    future = asyncio.async(coro)
    future.add_done_callback(dfd.callback)
    return dfd
