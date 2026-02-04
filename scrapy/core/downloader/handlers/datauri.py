from __future__ import annotations

from typing import TYPE_CHECKING, Any

from w3lib.url import parse_data_uri

from scrapy.core.downloader.handlers.base import BaseDownloadHandler
from scrapy.http import Response, TextResponse
from scrapy.responsetypes import responsetypes

if TYPE_CHECKING:
    from scrapy import Request


class DataURIDownloadHandler(BaseDownloadHandler):
    async def download_request(self, request: Request) -> Response:
        uri = parse_data_uri(request.url)
        respcls = responsetypes.from_mimetype(uri.media_type)

        resp_kwargs: dict[str, Any] = {}
        if issubclass(respcls, TextResponse) and uri.media_type.split("/")[0] == "text":
            charset = uri.media_type_parameters.get("charset")
            resp_kwargs["encoding"] = charset

        return respcls(url=request.url, body=uri.data, **resp_kwargs)
