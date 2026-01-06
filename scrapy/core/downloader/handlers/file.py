from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from w3lib.url import file_uri_to_path

from scrapy.core.downloader.handlers.base import BaseDownloadHandler
from scrapy.responsetypes import responsetypes

if TYPE_CHECKING:
    from scrapy import Request
    from scrapy.http import Response


class FileDownloadHandler(BaseDownloadHandler):
    async def download_request(self, request: Request) -> Response:
        filepath = file_uri_to_path(request.url)
        body = Path(filepath).read_bytes()
        respcls = responsetypes.from_args(filename=filepath, body=body)
        return respcls(url=request.url, body=body)
