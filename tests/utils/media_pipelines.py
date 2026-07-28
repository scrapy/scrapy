from __future__ import annotations

from typing import Any

from scrapy.http.request import NO_CALLBACK, Request


async def mocked_download_func(request: Request) -> Any:
    assert request.callback is NO_CALLBACK
    response = request.meta.get("response")
    if callable(response):
        response = await response()
    if isinstance(response, Exception):
        raise response
    return response
