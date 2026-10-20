from __future__ import annotations

import ipaddress
import socket
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
    UnsupportedURLSchemeError,
)
from scrapy.http import Headers
from scrapy.utils._download_handlers import get_proxy_headers
from scrapy.utils._ssl import _log_sslobj_debug_info, _make_ssl_context

from ._base_streaming import BaseStreamingDownloadHandler, _BaseResponseArgs

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from aiohttp.abc import ResolveResult
    from aiohttp.client_proto import ResponseHandler
    from aiohttp.client_reqrep import ClientRequest
    from aiohttp.tracing import Trace

    from scrapy import Request
    from scrapy.crawler import Crawler


class _AsyncResolver(aiohttp.AsyncResolver):
    """Resolves only the host and sets the requested port on the results.

    Workaround for https://github.com/c-ares/c-ares/issues/1374.
    """

    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[ResolveResult]:
        results = await super().resolve(host, 0, family)
        for result in results:
            result["port"] = port
        return results


class _TCPConnector(aiohttp.TCPConnector):
    """Counts idle connections toward the connection limit, closing the least
    recently used one when a new connection would otherwise exceed it."""

    async def _create_connection(
        self,
        req: ClientRequest,
        traces: list[Trace],
        timeout: aiohttp.ClientTimeout,  # noqa: ASYNC109
    ) -> ResponseHandler:
        # the connection about to be created is already counted in _acquired
        while (
            self._limit
            and len(self._acquired) + sum(map(len, self._conns.values())) > self._limit
        ):
            self._evict()
        return await super()._create_connection(req, traces, timeout)

    def _evict(self) -> None:
        _, key = min((conns[0][1], key) for key, conns in self._conns.items())
        protocol, _ = self._conns[key].popleft()
        if not self._conns[key]:
            del self._conns[key]
        protocol.close()


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
    lazy = True

    def __init__(self, crawler: Crawler):
        super().__init__(crawler)
        self._ssl_context: ssl.SSLContext = _make_ssl_context(crawler.settings)
        self._resolver: _AsyncResolver | None = (
            _AsyncResolver() if sys.platform == "win32" else None
        )
        connector = _TCPConnector(
            resolver=self._resolver,
            local_addr=self._bind_address,
            # hard limit on open connections, idle ones included
            limit=self._pool_size_total,
            # hard limit on simultaneous connections per host
            limit_per_host=self._pool_size_per_host,
            keepalive_timeout=self._keepalive_timeout or None,
            force_close=not self._keepalive_timeout,
        )
        self._session: aiohttp.ClientSession = aiohttp.ClientSession(
            connector=connector,
            cookie_jar=aiohttp.DummyCookieJar(),
            auto_decompress=False,
            response_class=_ClientResponse,
            skip_auto_headers=(
                "Accept",
                "Accept-Encoding",
                "Content-Type",
                "User-Agent",
            ),
        )

    @asynccontextmanager
    async def _make_request(
        self,
        request: Request,
        timeout: float,  # noqa: ASYNC109
    ) -> AsyncIterator[_ClientResponse]:
        proxy = self._extract_proxy_url_with_creds(request)
        proxy_headers = get_proxy_headers(request)
        headers = self._utf8_request_headers(request)
        if proxy_headers and not request.url.startswith("https:"):
            # without a tunnel the proxy reads the request headers, so the
            # headers meant for it travel among them, and it is up to the proxy
            # not to pass them on to the target server
            headers.extend(proxy_headers)
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
                proxy_headers=dict(proxy_headers) or None,
            ) as response:
                yield cast("_ClientResponse", response)
        except TimeoutError as e:
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
        except aiohttp.ClientError as e:
            raise DownloadFailedError(str(e)) from e

    @staticmethod
    def _extract_headers(response: _ClientResponse) -> Headers:
        return Headers(response.raw_headers)

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

    @staticmethod
    def _is_timeout_exception(exc: Exception) -> bool:
        return isinstance(exc, TimeoutError)

    async def close(self) -> None:
        await self._session.close()
        if self._resolver is not None:
            await self._resolver.close()
