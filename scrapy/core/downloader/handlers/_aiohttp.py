from __future__ import annotations

import asyncio
import ipaddress
import logging
import ssl
import sys
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, ClassVar, cast

import aiohttp
import aiohttp.connector
import yarl

from scrapy.exceptions import (
    CannotResolveHostError,
    DownloadConnectionRefusedError,
    DownloadFailedError,
    DownloadTimeoutError,
    ResponseHeadersTooLargeError,
    UnsupportedURLSchemeError,
)
from scrapy.http import Headers
from scrapy.utils._download_handlers import (
    get_headers_maxsize_msg,
    get_headers_warnsize_msg,
)
from scrapy.utils._ssl import _log_sslobj_debug_info, _make_ssl_context
from scrapy.utils.python import _iter_exc_causes

from ._base_streaming import BaseStreamingDownloadHandler, _BaseResponseArgs

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from scrapy import Request
    from scrapy.crawler import Crawler


logger = logging.getLogger(__name__)


class _ClientResponse(aiohttp.ClientResponse):
    """Captures transport data that can be lost after parent ``start()``.

    Workaround for https://github.com/aio-libs/aiohttp/issues/2205.
    """

    _peername: tuple[str, int] | None = None
    _ssl_object: ssl.SSLObject | None = None

    async def start(
        self, connection: aiohttp.connector.Connection
    ) -> aiohttp.ClientResponse:
        transport = connection.transport
        assert transport is not None
        self._peername = transport.get_extra_info("peername")
        ssl_object = transport.get_extra_info("ssl_object")
        if isinstance(ssl_object, ssl.SSLObject):
            self._ssl_object = ssl_object
        return await super().start(connection)


class AiohttpDownloadHandler(BaseStreamingDownloadHandler[_ClientResponse]):
    experimental: ClassVar[bool] = True

    def __init__(self, crawler: Crawler):
        super().__init__(crawler)
        self._ssl_context: ssl.SSLContext = _make_ssl_context(crawler.settings)
        connector = aiohttp.TCPConnector(
            local_addr=self._bind_address,
            # hard limit on simultaneous connections
            limit=self._pool_size_total,
            # hard limit on simultaneous connections per host
            limit_per_host=self._pool_size_per_host,
        )
        # aiohttp limits the size of each line of the response head; the size
        # of the head as a whole is checked in _check_headers_size() once it
        # has been received.
        line_maxsize = self._headers_maxsize or sys.maxsize
        self._session: aiohttp.ClientSession = aiohttp.ClientSession(
            connector=connector,
            cookie_jar=aiohttp.DummyCookieJar(),
            auto_decompress=False,
            response_class=_ClientResponse,
            max_line_size=line_maxsize,
            max_field_size=line_maxsize,
            skip_auto_headers=(
                "Accept",
                "Accept-Encoding",
                "Content-Type",
                "User-Agent",
            ),
        )

    @asynccontextmanager
    async def _make_request(
        self, request: Request, timeout: float
    ) -> AsyncIterator[_ClientResponse]:
        proxy = self._extract_proxy_url_with_creds(request)
        headers = self._request_headers(request).to_tuple_list()
        url: str | yarl.URL = request.url
        if request.meta.get("verbatim_url"):
            # encoded=True disables the percent-encoding normalization that
            # yarl applies to str URLs, so the URL is sent as is
            url = yarl.URL(request.url, encoded=True)
        try:
            async with await self._session.request(
                request.method,
                url,
                data=request.body,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
                ssl=self._ssl_context,
                allow_redirects=False,
                proxy=proxy,
            ) as response:
                self._check_headers_size(response, request)
                yield cast("_ClientResponse", response)
        except (TimeoutError, asyncio.TimeoutError) as e:
            raise DownloadTimeoutError(
                f"Getting {request.url} took longer than {timeout} seconds."
            ) from e
        except (
            aiohttp.InvalidUrlClientError,
            aiohttp.NonHttpUrlClientError,
        ) as e:
            raise UnsupportedURLSchemeError(str(e)) from e
        except aiohttp.ClientConnectorDNSError as e:
            raise CannotResolveHostError(str(e)) from e
        except aiohttp.ClientConnectorError as e:
            raise DownloadConnectionRefusedError(str(e)) from e
        except aiohttp.ClientResponseError as e:
            if any(
                isinstance(cause, aiohttp.http_exceptions.LineTooLong)
                for cause in _iter_exc_causes(e)
            ):
                raise ResponseHeadersTooLargeError(
                    get_headers_maxsize_msg(None, self._headers_maxsize, request.url)
                ) from e
            raise DownloadFailedError(str(e)) from e
        except aiohttp.ClientError as e:
            raise DownloadFailedError(str(e)) from e

    def _check_headers_size(
        self, response: aiohttp.ClientResponse, request: Request
    ) -> None:
        size = sum(len(name) + len(value) + 4 for name, value in response.raw_headers)
        if self._headers_maxsize and size > self._headers_maxsize:
            raise ResponseHeadersTooLargeError(
                get_headers_maxsize_msg(size, self._headers_maxsize, request.url)
            )
        if self._headers_warnsize and size > self._headers_warnsize:
            logger.warning(
                get_headers_warnsize_msg(size, self._headers_warnsize, request.url)
            )

    @staticmethod
    def _extract_headers(response: _ClientResponse) -> Headers:
        return Headers(list(response.headers.items()))

    @staticmethod
    def _build_base_response_args(
        response: _ClientResponse,
        request: Request,
        headers: Headers,
    ) -> _BaseResponseArgs:
        version = response.version
        protocol_version = (
            f"HTTP/{version.major}.{version.minor}" if version else "HTTP/1.1"
        )
        assert response._peername is not None
        ip_address = ipaddress.ip_address(response._peername[0])
        if response._ssl_object is not None:
            cert = response._ssl_object.getpeercert(binary_form=True)
        else:  # HTTP
            cert = None
        return {
            "status": response.status,
            "url": request.url,
            "headers": headers,
            "certificate": cert,
            "ip_address": ip_address,
            "protocol": protocol_version,
        }

    def _log_tls_info(self, response: _ClientResponse, request: Request) -> None:
        assert response._ssl_object is not None
        _log_sslobj_debug_info(response._ssl_object)

    @staticmethod
    def _iter_body_chunks(response: _ClientResponse) -> AsyncIterator[bytes]:
        return response.content.iter_any()

    @staticmethod
    def _is_dataloss_exception(exc: Exception) -> bool:
        return isinstance(exc, aiohttp.ClientPayloadError)

    async def close(self) -> None:
        await self._session.close()
