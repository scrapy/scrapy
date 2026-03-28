from __future__ import annotations

from typing import TYPE_CHECKING

from scrapy.core.downloader.handlers.base import BaseDownloadHandler
from scrapy.core.downloader.handlers.http11 import HTTP11DownloadHandler
from scrapy.exceptions import NotConfigured
from scrapy.utils.boto import is_botocore_available
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.misc import build_from_crawler

if TYPE_CHECKING:
    from scrapy import Request
    from scrapy.crawler import Crawler
    from scrapy.http import Response


class S3DownloadHandler(BaseDownloadHandler):
    lazy = True

    def __init__(self, crawler: Crawler):
        if not is_botocore_available():
            raise NotConfigured("missing botocore library")

        super().__init__(crawler)
        aws_access_key_id = crawler.settings["AWS_ACCESS_KEY_ID"]
        aws_secret_access_key = crawler.settings["AWS_SECRET_ACCESS_KEY"]
        aws_session_token = crawler.settings["AWS_SESSION_TOKEN"]
        self.anon = not aws_access_key_id and not aws_secret_access_key
        self._signer = None
        if not self.anon:
            import botocore.auth  # noqa: PLC0415
            import botocore.credentials  # noqa: PLC0415

            SignerCls = botocore.auth.AUTH_TYPE_MAPS["s3"]
            # botocore.auth.BaseSigner doesn't have an __init__() with args, only subclasses do
            self._signer = SignerCls(  # type: ignore[call-arg]
                botocore.credentials.Credentials(
                    aws_access_key_id, aws_secret_access_key, aws_session_token
                )
            )

        _http_handler = build_from_crawler(HTTP11DownloadHandler, crawler)
        self._download_http = _http_handler.download_request

    async def download_request(self, request: Request) -> Response:
        p = urlparse_cached(request)
        scheme = "https" if request.meta.get("is_secure") else "http"
        bucket = p.hostname
        path = p.path + "?" + p.query if p.query else p.path
        url = f"{scheme}://{bucket}.s3.amazonaws.com{path}"
        if self.anon:
            request = request.replace(url=url)
        else:
            import botocore.awsrequest  # noqa: PLC0415

            awsrequest = botocore.awsrequest.AWSRequest(
                method=request.method,
                url=f"{scheme}://s3.amazonaws.com/{bucket}{path}",
                headers=request.headers.to_unicode_dict(),
                data=request.body,
            )
            assert self._signer
            self._signer.add_auth(awsrequest)
            request = request.replace(url=url, headers=awsrequest.headers.items())
        return await self._download_http(request)
