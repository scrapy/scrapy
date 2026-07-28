from __future__ import annotations

from typing import Any

from scrapy.http.request import NO_CALLBACK, Request
from scrapy.pipelines.media import MediaPipeline
from scrapy.utils.spider import DefaultSpider

# required by persist_file() and stat_file(), but as some stores don't use the argument
# we can pass this singleton to keep type hints correct
DUMMY_SPIDER_INFO = MediaPipeline.SpiderInfo(DefaultSpider())


async def mocked_download_func(request: Request) -> Any:
    assert request.callback is NO_CALLBACK
    response = request.meta.get("response")
    if callable(response):
        response = await response()
    if isinstance(response, Exception):
        raise response
    return response
