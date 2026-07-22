from __future__ import annotations

from typing import TYPE_CHECKING

from w3lib.url import parse_data_uri

from scrapy.core.downloader.handlers.base import BaseDownloadHandler
from scrapy.http import Response, TextResponse
from scrapy.utils.response import get_response_class

if TYPE_CHECKING:
    from scrapy import Request


class DataURIDownloadHandler(BaseDownloadHandler):
    async def download_request(self, request: Request) -> Response:
        uri = parse_data_uri(request.url)
        respcls = get_response_class(
            body=uri.data,
            declared_mime_type=uri.media_type.encode(),
        )

        if issubclass(respcls, TextResponse) and uri.media_type.split("/")[0] == "text":
            charset = uri.media_type_parameters.get("charset")
            return respcls(url=request.url, body=uri.data, encoding=charset)

        return respcls(url=request.url, body=uri.data)
