from typing import Any, Dict

from w3lib.url import parse_data_uri

from scrapy import Request, Spider
from scrapy.http import Response, TextResponse
from scrapy.utils.decorators import defers
from scrapy.utils.response import get_response_class


class DataURIDownloadHandler:
    lazy = False

    @defers
    def download_request(self, request: Request, spider: Spider) -> Response:
        uri = parse_data_uri(request.url)
        respcls = get_response_class(
            body=uri.data,
            declared_mime_types=(uri.media_type.encode(),),
        )

        resp_kwargs: Dict[str, Any] = {}
        if issubclass(respcls, TextResponse) and uri.media_type.split("/")[0] == "text":
            charset = uri.media_type_parameters.get("charset")
            resp_kwargs["encoding"] = charset

        return respcls(url=request.url, body=uri.data, **resp_kwargs)
