from __future__ import annotations

from typing import TYPE_CHECKING, Any

from scrapy.core.downloader.handlers.http import HTTPDownloadHandler
from scrapy.exceptions import NotConfigured
from scrapy.utils.boto import is_botocore_available
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.misc import build_from_crawler

if TYPE_CHECKING:
    from twisted.internet.defer import Deferred

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy import Request, Spider
    from scrapy.crawler import Crawler
    from scrapy.http import Response
    from scrapy.settings import BaseSettings


class S3DownloadHandler:
    def __init__(
        self,
        settings: BaseSettings,
        *,
        crawler: Crawler,
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
        aws_session_token: str | None = None,
        httpdownloadhandler: type[HTTPDownloadHandler] = HTTPDownloadHandler,
        **kw: Any,
    ):
        if not is_botocore_available():
            raise NotConfigured("missing botocore library")

        if not aws_access_key_id:
            aws_access_key_id = settings["AWS_ACCESS_KEY_ID"]
        if not aws_secret_access_key:
            aws_secret_access_key = settings["AWS_SECRET_ACCESS_KEY"]
        if not aws_session_token:
            aws_session_token = settings["AWS_SESSION_TOKEN"]

        # If no credentials could be found anywhere,
        # consider this an anonymous connection request by default;
        # unless 'anon' was set explicitly (True/False).
        anon = kw.get("anon")
        if anon is None and not aws_access_key_id and not aws_secret_access_key:
            kw["anon"] = True
        self.anon = kw.get("anon")

        self._signer = None
        import botocore.auth
        import botocore.credentials

        kw.pop("anon", None)
        if kw:
            raise TypeError(f"Unexpected keyword arguments: {kw}")
        if not self.anon:
            assert aws_access_key_id is not None
            assert aws_secret_access_key is not None
            SignerCls = botocore.auth.AUTH_TYPE_MAPS["s3"]
            # botocore.auth.BaseSigner doesn't have an __init__() with args, only subclasses do
            self._signer = SignerCls(  # type: ignore[call-arg]
                botocore.credentials.Credentials(
                    aws_access_key_id, aws_secret_access_key, aws_session_token
                )
            )

        _http_handler = build_from_crawler(
            httpdownloadhandler,
            crawler,
        )
        self._download_http = _http_handler.download_request

    @classmethod
    def from_crawler(cls, crawler: Crawler, **kwargs: Any) -> Self:
        return cls(crawler.settings, crawler=crawler, **kwargs)

    def download_request(self, request: Request, spider: Spider) -> Deferred[Response]:
        p = urlparse_cached(request)
        scheme = "https" if request.meta.get("is_secure") else "http"
        bucket = p.hostname
        path = p.path + "?" + p.query if p.query else p.path
        url = f"{scheme}://{bucket}.s3.amazonaws.com{path}"
        if self.anon:
            request = request.replace(url=url)
        else:
            import botocore.awsrequest

            awsrequest = botocore.awsrequest.AWSRequest(
                method=request.method,
                url=f"{scheme}://s3.amazonaws.com/{bucket}{path}",
                headers=request.headers.to_unicode_dict(),
                data=request.body,
            )
            assert self._signer
            self._signer.add_auth(awsrequest)
            request = request.replace(url=url, headers=awsrequest.headers.items())
        return self._download_http(request, spider)
