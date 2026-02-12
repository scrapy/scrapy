"""``httpx``-based HTTP(S) download handler. Currently not recommended for production use."""

from __future__ import annotations

import ipaddress
import logging
import ssl
from http.cookiejar import Cookie, CookieJar
from io import BytesIO
from typing import TYPE_CHECKING, Any, NoReturn, TypedDict

import httpx

from scrapy import Request, signals
from scrapy.exceptions import (
    CannotResolveHostError,
    DownloadCancelledError,
    DownloadConnectionRefusedError,
    DownloadFailedError,
    DownloadTimeoutError,
    NotConfigured,
    ResponseDataLossError,
    UnsupportedURLSchemeError,
)
from scrapy.http import Headers, Response
from scrapy.utils._download_handlers import (
    BaseHttpDownloadHandler,
    check_stop_download,
    get_dataloss_msg,
    get_maxsize_msg,
    get_warnsize_msg,
    make_response,
)
from scrapy.utils.asyncio import is_asyncio_available
from scrapy.utils.ssl import _log_sslobj_debug_info, _make_ssl_context

if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager
    from http.client import HTTPResponse
    from ipaddress import IPv4Address, IPv6Address
    from urllib.request import Request as ULRequest

    from httpcore import AsyncNetworkStream

    from scrapy.crawler import Crawler


logger = logging.getLogger(__name__)


class _BaseResponseArgs(TypedDict):
    status: int
    url: str
    headers: Headers
    ip_address: IPv4Address | IPv6Address
    protocol: str


# workaround for (and from) https://github.com/encode/httpx/issues/2992
class _NullCookieJar(CookieJar):  # pragma: no cover
    """A CookieJar that rejects all cookies."""

    def extract_cookies(self, response: HTTPResponse, request: ULRequest) -> None:
        pass

    def set_cookie(self, cookie: Cookie) -> None:
        pass


class HttpxDownloadHandler(BaseHttpDownloadHandler):
    _DEFAULT_CONNECT_TIMEOUT = 10

    def __init__(self, crawler: Crawler):
        # we don't run extra-deps tests with the non-asyncio reactor
        if not is_asyncio_available():  # pragma: no cover
            raise NotConfigured(
                f"{type(self).__name__} requires the asyncio support. Make"
                f" sure that you have either enabled the asyncio Twisted"
                f" reactor in the TWISTED_REACTOR setting or disabled the"
                f" TWISTED_ENABLED setting. See the asyncio documentation"
                f" of Scrapy for more information."
            )
        super().__init__(crawler)
        logger.warning(
            "HttpxDownloadHandler is experimental and is not recommented for production use."
        )
        self._tls_verbose_logging: bool = self.crawler.settings.getbool(
            "DOWNLOADER_CLIENT_TLS_VERBOSE_LOGGING"
        )
        self._client = httpx.AsyncClient(
            verify=_make_ssl_context(crawler.settings), cookies=_NullCookieJar()
        )

    async def download_request(self, request: Request) -> Response:
        self._warn_unsupported_meta(request.meta)

        timeout: float = request.meta.get(
            "download_timeout", self._DEFAULT_CONNECT_TIMEOUT
        )

        try:
            async with self._get_httpx_response(request, timeout) as httpx_response:
                return await self._read_response(httpx_response, request)
        except httpx.TimeoutException as e:
            raise DownloadTimeoutError(
                f"Getting {request.url} took longer than {timeout} seconds."
            ) from e
        except httpx.UnsupportedProtocol as e:
            raise UnsupportedURLSchemeError(str(e)) from e
        except httpx.ConnectError as e:
            if "Name or service not known" in str(e) or "getaddrinfo failed" in str(e):
                raise CannotResolveHostError(str(e)) from e
            raise DownloadConnectionRefusedError(str(e)) from e
        except httpx.NetworkError as e:
            raise DownloadFailedError(str(e)) from e
        except httpx.RemoteProtocolError as e:
            raise DownloadFailedError(str(e)) from e

    def _warn_unsupported_meta(self, meta: dict[str, Any]) -> None:
        if meta.get("bindaddress"):
            # configurable only per-client:
            # https://github.com/encode/httpx/issues/755#issuecomment-2746121794
            logger.error(
                f"The 'bindaddress' request meta key is not supported by"
                f" {type(self).__name__} and will be ignored."
            )
        if meta.get("proxy"):
            # configurable only per-client:
            # https://github.com/encode/httpx/issues/486
            logger.error(
                f"The 'proxy' request meta key is not supported by"
                f" {type(self).__name__} and will be ignored."
            )

    def _get_httpx_response(
        self, request: Request, timeout: float
    ) -> AbstractAsyncContextManager[httpx.Response]:
        return self._client.stream(
            request.method,
            request.url,
            content=request.body,
            headers=request.headers.to_tuple_list(),
            timeout=timeout,
        )

    async def _read_response(
        self, httpx_response: httpx.Response, request: Request
    ) -> Response:
        maxsize: int = request.meta.get("download_maxsize", self._default_maxsize)
        warnsize: int = request.meta.get("download_warnsize", self._default_warnsize)

        content_length = httpx_response.headers.get("Content-Length")
        expected_size = int(content_length) if content_length is not None else None
        if maxsize and expected_size and expected_size > maxsize:
            self._cancel_maxsize(expected_size, maxsize, request, expected=True)

        reached_warnsize = False
        if warnsize and expected_size and expected_size > warnsize:
            reached_warnsize = True
            logger.warning(
                get_warnsize_msg(expected_size, warnsize, request, expected=True)
            )

        headers = Headers(httpx_response.headers.multi_items())
        network_stream: AsyncNetworkStream = httpx_response.extensions["network_stream"]

        make_response_base_args: _BaseResponseArgs = {
            "status": httpx_response.status_code,
            "url": request.url,
            "headers": headers,
            "ip_address": self._get_server_ip(network_stream),
            "protocol": httpx_response.http_version,
        }

        self._log_tls_info(network_stream)

        if stop_download := check_stop_download(
            signals.headers_received,
            self.crawler,
            request,
            headers=headers,
            body_length=expected_size,
        ):
            return make_response(
                **make_response_base_args,
                stop_download=stop_download,
            )

        response_body = BytesIO()
        bytes_received = 0
        try:
            async for chunk in httpx_response.aiter_raw():
                response_body.write(chunk)
                bytes_received += len(chunk)

                if stop_download := check_stop_download(
                    signals.bytes_received, self.crawler, request, data=chunk
                ):
                    return make_response(
                        **make_response_base_args,
                        body=response_body.getvalue(),
                        stop_download=stop_download,
                    )

                if maxsize and bytes_received > maxsize:
                    response_body.truncate(0)
                    self._cancel_maxsize(
                        bytes_received, maxsize, request, expected=False
                    )

                if warnsize and bytes_received > warnsize and not reached_warnsize:
                    reached_warnsize = True
                    logger.warning(
                        get_warnsize_msg(
                            bytes_received, warnsize, request, expected=False
                        )
                    )
        except httpx.RemoteProtocolError as e:
            # special handling of the dataloss case
            if (
                "peer closed connection without sending complete message body"
                not in str(e)
            ):
                raise
            fail_on_dataloss: bool = request.meta.get(
                "download_fail_on_dataloss", self._fail_on_dataloss
            )
            if not fail_on_dataloss:
                return make_response(
                    **make_response_base_args,
                    body=response_body.getvalue(),
                    flags=["dataloss"],
                )
            self._log_dataloss_warning(request.url)
            raise ResponseDataLossError(str(e)) from e

        return make_response(
            **make_response_base_args,
            body=response_body.getvalue(),
        )

    @staticmethod
    def _get_server_ip(network_stream: AsyncNetworkStream) -> IPv4Address | IPv6Address:
        extra_server_addr = network_stream.get_extra_info("server_addr")
        return ipaddress.ip_address(extra_server_addr[0])

    def _log_tls_info(self, network_stream: AsyncNetworkStream) -> None:
        if not self._tls_verbose_logging:
            return
        extra_ssl_object = network_stream.get_extra_info("ssl_object")
        if isinstance(extra_ssl_object, ssl.SSLObject):
            _log_sslobj_debug_info(extra_ssl_object)

    def _log_dataloss_warning(self, url: str) -> None:
        if self._fail_on_dataloss_warned:
            return
        logger.warning(get_dataloss_msg(url))
        self._fail_on_dataloss_warned = True

    @staticmethod
    def _cancel_maxsize(
        size: int, limit: int, request: Request, *, expected: bool
    ) -> NoReturn:
        warning_msg = get_maxsize_msg(size, limit, request, expected=expected)
        logger.warning(warning_msg)
        raise DownloadCancelledError(warning_msg)

    async def close(self):
        await self._client.aclose()
