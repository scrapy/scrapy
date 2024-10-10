from __future__ import annotations

from typing import TYPE_CHECKING, Any

from w3lib.url import parse_data_uri

from scrapy.http import Response, TextResponse
from scrapy.responsetypes import responsetypes
from scrapy.utils.decorators import defers

if TYPE_CHECKING:
    from scrapy import Request, Spider


class DataURIDownloadHandler:
    lazy = False

    @defers
    def download_request(self, request: Request, spider: Spider) -> Response:
        uri = parse_data_uri(request.url)
        respcls = responsetypes.from_mimetype(uri.media_type)

        resp_kwargs: dict[str, Any] = {}
        if issubclass(respcls, TextResponse) and uri.media_type.split("/")[0] == "text":
            charset = uri.media_type_parameters.get("charset")
            resp_kwargs["encoding"] = charset

        return respcls(url=request.url, body=uri.data, **resp_kwargs)
