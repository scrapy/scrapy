from __future__ import annotations

import ipaddress
import logging
import ssl
from io import BytesIO
from typing import TYPE_CHECKING, TypedDict

import httpx

from scrapy import Request, signals
from scrapy.exceptions import (
    CannotResolveHostError,
    DownloadCancelledError,
    DownloadConnectionRefusedError,
    DownloadFailedError,
    DownloadTimeoutError,
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
    from ipaddress import IPv4Address, IPv6Address

    from scrapy.crawler import Crawler


logger = logging.getLogger(__name__)


class _BaseResponseArgs(TypedDict):
    status: int
    url: str
    headers: Headers
    ip_address: IPv4Address | IPv6Address
    protocol: str


# TODO: improve this
# # workaround for (and from) https://github.com/encode/httpx/issues/2992
# class _AsyncDisableCookiesTransport(httpx.AsyncBaseTransport):
#     def __init__(self, transport: httpx.AsyncBaseTransport):
#         self.transport = transport
#
#     async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
#         response = await self.transport.handle_async_request(request)
#         response.headers.pop("set-cookie", None)
#         return response
#
#     async def aclose(self) -> None:
#         await self.transport.aclose()


class HttpxDownloadHandler(BaseHttpDownloadHandler):
    _DEFAULT_CONNECT_TIMEOUT = 10

    def __init__(self, crawler: Crawler):
        if not is_asyncio_available():
            raise ValueError(
                "HttpxDownloadHandler requires the asyncio Twisted "
                "reactor. Make sure you have it configured in the "
                "TWISTED_REACTOR setting. See the asyncio documentation "
                "of Scrapy for more information."
            )
        super().__init__(crawler)
        self._tls_verbose_logging: bool = self.crawler.settings.getbool(
            "DOWNLOADER_CLIENT_TLS_VERBOSE_LOGGING"
        )
        self._client = httpx.AsyncClient(verify=_make_ssl_context(crawler.settings))
        # # the following AsyncClient args need to be passed to the transport instead:
        # # verify, cert, trust_env, http1, http2, limits
        # self._client = httpx.AsyncClient(
        #     transport=_AsyncDisableCookiesTransport(
        #         httpx.AsyncHTTPTransport(verify=_make_ssl_context(crawler.settings))
        #     ),
        # )

    async def download_request(self, request: Request) -> Response:  # pylint: disable=too-many-statements
        maxsize = request.meta.get("download_maxsize", self._default_maxsize)
        warnsize = request.meta.get("download_warnsize", self._default_warnsize)
        timeout = request.meta.get("download_timeout", self._DEFAULT_CONNECT_TIMEOUT)
        bindaddress = request.meta.get("bindaddress")
        if bindaddress:
            # configurable only per-client:
            # https://github.com/encode/httpx/issues/755#issuecomment-2746121794
            logger.error(
                f"The 'bindaddress' request meta key is not supported by {type(self).__name__}."
            )
        proxy = request.meta.get("proxy")
        if proxy:
            # configurable only per-client:
            # https://github.com/encode/httpx/issues/486
            logger.error(
                f"The 'proxy' request meta key is not supported by {type(self).__name__}."
            )
        fail_on_dataloss = request.meta.get(
            "download_fail_on_dataloss", self._fail_on_dataloss
        )
        response_body = BytesIO()
        bytes_received = 0
        reached_warnsize = False

        try:
            async with self._client.stream(
                request.method,
                request.url,
                content=request.body,
                headers=request.headers.to_tuple_list(),
                timeout=timeout,
            ) as httpx_response:
                content_length = httpx_response.headers.get("Content-Length")
                expected_size = (
                    int(content_length) if content_length is not None else None
                )
                if maxsize and expected_size and expected_size > maxsize:
                    warning_msg = get_maxsize_msg(
                        expected_size, maxsize, request, expected=True
                    )
                    logger.warning(warning_msg)
                    raise DownloadCancelledError(warning_msg)
                if warnsize and expected_size and expected_size > warnsize:
                    reached_warnsize = True
                    logger.warning(
                        get_warnsize_msg(
                            expected_size, warnsize, request, expected=True
                        )
                    )

                status = httpx_response.status_code
                headers = Headers(httpx_response.headers.multi_items())
                protocol = httpx_response.http_version
                network_stream = httpx_response.extensions["network_stream"]
                extra_server_addr = network_stream.get_extra_info("server_addr")
                server_ip = ipaddress.ip_address(extra_server_addr[0])

                if self._tls_verbose_logging:
                    extra_ssl_object = network_stream.get_extra_info("ssl_object")
                    if isinstance(extra_ssl_object, ssl.SSLObject):
                        _log_sslobj_debug_info(extra_ssl_object)

                make_response_base_args: _BaseResponseArgs = {
                    "status": status,
                    "url": request.url,
                    "headers": headers,
                    "ip_address": server_ip,
                    "protocol": protocol,
                }

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
                            warning_msg = get_maxsize_msg(
                                bytes_received, maxsize, request, expected=False
                            )
                            logger.warning(warning_msg)
                            response_body.truncate(0)
                            raise DownloadCancelledError(warning_msg)

                        if (
                            warnsize
                            and bytes_received > warnsize
                            and not reached_warnsize
                        ):
                            reached_warnsize = True
                            logger.warning(
                                get_warnsize_msg(
                                    bytes_received, warnsize, request, expected=False
                                )
                            )
                except httpx.RemoteProtocolError as e:
                    if (
                        "peer closed connection without sending complete message body"
                        not in str(e)
                    ):
                        raise
                    if not fail_on_dataloss:
                        return make_response(
                            **make_response_base_args,
                            body=response_body.getvalue(),
                            flags=["dataloss"],
                        )
                    if not self._fail_on_dataloss_warned:
                        logger.warning(get_dataloss_msg(request.url))
                        self._fail_on_dataloss_warned = True
                    raise ResponseDataLossError(str(e)) from e

            return make_response(
                **make_response_base_args,
                body=response_body.getvalue(),
            )
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

    async def close(self):
        await self._client.aclose()
