from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from w3lib.url import file_uri_to_path

from scrapy.responsetypes import responsetypes
from scrapy.utils.decorators import defers

if TYPE_CHECKING:
    from scrapy import Request, Spider
    from scrapy.http import Response


class FileDownloadHandler:
    lazy = False

    @defers
    def download_request(self, request: Request, spider: Spider) -> Response:
        filepath = file_uri_to_path(request.url)
        body = Path(filepath).read_bytes()
        respcls = responsetypes.from_args(filename=filepath, body=body)
        return respcls(url=request.url, body=body)
