"""``httpx``-based HTTP(S) download handler. Currently not recommended for production use."""

from __future__ import annotations

import ipaddress
import ssl
from contextlib import asynccontextmanager
from socket import gaierror
from typing import TYPE_CHECKING, ClassVar

from scrapy.exceptions import (
    CannotResolveHostError,
    DownloadConnectionRefusedError,
    DownloadFailedError,
    DownloadTimeoutError,
    NotConfigured,
    UnsupportedURLSchemeError,
)
from scrapy.http import Headers
from scrapy.utils._download_handlers import NullCookieJar
from scrapy.utils.python import _iter_exc_causes
from scrapy.utils.ssl import (
    _log_sslobj_debug_info,
    _make_insecure_ssl_ctx,
    _make_ssl_context,
)

from ._base_streaming import BaseStreamingDownloadHandler, _BaseResponseArgs

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from httpcore import AsyncNetworkStream

    from scrapy import Request
    from scrapy.crawler import Crawler


HAS_SOCKS = HAS_HTTP2 = False

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment]
else:
    # a small hack to avoid importing these optional extras unconditionally

    DOWNLOAD_FAILED_EXCEPTIONS: tuple[type[BaseException], ...] = (
        httpx.RequestError,
        httpx.InvalidURL,
    )

    try:
        import h2.exceptions

        HAS_HTTP2 = True
        DOWNLOAD_FAILED_EXCEPTIONS += (h2.exceptions.InvalidBodyLengthError,)
    except ImportError:  # pragma: no cover
        pass

    try:
        import socksio.exceptions

        HAS_SOCKS = True
        DOWNLOAD_FAILED_EXCEPTIONS += (socksio.exceptions.ProtocolError,)
    except ImportError:  # pragma: no cover
        pass


if TYPE_CHECKING:
    _Base = BaseStreamingDownloadHandler[httpx.Response]
else:
    _Base = BaseStreamingDownloadHandler


class HttpxDownloadHandler(_Base):
    experimental: ClassVar[bool] = True

    def __init__(self, crawler: Crawler):
        super().__init__(crawler)
        self._verify_certificates: bool = crawler.settings.getbool(
            "DOWNLOAD_VERIFY_CERTIFICATES"
        )
        self._enable_h2: bool = crawler.settings.getbool("HTTPX_HTTP2_ENABLED")
        if self._enable_h2 and not HAS_HTTP2:  # pragma: no cover
            raise NotConfigured(
                f"HTTP/2 support in {type(self).__name__} requires the 'httpx[http2]' extra to be installed."
            )
        self._ssl_context: ssl.SSLContext = _make_ssl_context(crawler.settings)
        self._bind_host: str | None = self._get_bind_address_host()
        self._limits: httpx.Limits = httpx.Limits(
            # hard limit on simultaneous connections
            max_connections=self._pool_size_total,
            # total number of idle connections in the pool (extra ones are closed)
            max_keepalive_connections=self._pool_size_total,
        )

        self._default_client: httpx.AsyncClient = self._make_client()
        # httpx doesn't support per-request proxies: https://github.com/encode/httpx/discussions/3183,
        # so we keep a pool of clients per proxy URL. LRU eviction can be added here if needed.
        self._proxy_clients: dict[str, httpx.AsyncClient] = {}

    @staticmethod
    def _check_deps_installed() -> None:
        if httpx is None:  # pragma: no cover
            raise NotConfigured(
                "HttpxDownloadHandler requires the httpx library to be installed."
            )

    def _make_client(self, proxy_url: str | None = None) -> httpx.AsyncClient:
        if proxy_url:
            if proxy_url.startswith("https:") and not self._verify_certificates:
                proxy_ssl_context = _make_insecure_ssl_ctx()
            else:
                proxy_ssl_context = None
            proxy = httpx.Proxy(proxy_url, ssl_context=proxy_ssl_context)
        else:
            proxy = None

        client = httpx.AsyncClient(
            cookies=NullCookieJar(),
            transport=httpx.AsyncHTTPTransport(
                verify=self._ssl_context,
                local_address=self._bind_host,
                http2=self._enable_h2,
                limits=self._limits,
                trust_env=False,
                proxy=proxy,
            ),
        )
        # https://github.com/encode/httpx/discussions/1566
        for header_name in ("accept", "accept-encoding", "user-agent"):
            client.headers.pop(header_name, None)
        return client

    def _get_client(self, proxy_url: str | None) -> httpx.AsyncClient:
        if proxy_url is None:
            return self._default_client
        if cached := self._proxy_clients.get(proxy_url):
            return cached
        client = self._make_client(proxy_url)
        self._proxy_clients[proxy_url] = client
        return client

    @asynccontextmanager
    async def _make_request(
        self, request: Request, timeout: float
    ) -> AsyncIterator[httpx.Response]:
        proxy = self._extract_proxy_url_with_creds(request)
        if proxy and proxy.startswith("socks") and not HAS_SOCKS:  # pragma: no cover
            raise ValueError(
                f"SOCKS proxy support in {type(self).__name__} requires the 'httpx[socks]' extra to be installed."
            )
        client = self._get_client(proxy)

        try:
            async with client.stream(
                request.method,
                request.url,
                content=request.body,
                headers=request.headers.to_tuple_list(),
                timeout=timeout,
            ) as response:
                yield response
        except httpx.TimeoutException as e:
            raise DownloadTimeoutError(
                f"Getting {request.url} took longer than {timeout} seconds."
            ) from e
        except httpx.UnsupportedProtocol as e:
            raise UnsupportedURLSchemeError(str(e)) from e
        except httpx.ConnectError as e:
            if any(isinstance(c, gaierror) for c in _iter_exc_causes(e)):
                raise CannotResolveHostError(str(e)) from e
            raise DownloadConnectionRefusedError(str(e)) from e
        except httpx.ProxyError as e:
            raise DownloadConnectionRefusedError(str(e)) from e
        except DOWNLOAD_FAILED_EXCEPTIONS as e:
            raise DownloadFailedError(str(e)) from e

    @staticmethod
    def _extract_headers(response: httpx.Response) -> Headers:
        return Headers(response.headers.multi_items())

    @staticmethod
    def _build_base_response_args(
        response: httpx.Response,
        request: Request,
        headers: Headers,
    ) -> _BaseResponseArgs:
        network_stream: AsyncNetworkStream = response.extensions["network_stream"]
        server_addr = network_stream.get_extra_info("server_addr")
        ip_address = ipaddress.ip_address(server_addr[0])
        ssl_object = network_stream.get_extra_info("ssl_object")
        if isinstance(ssl_object, ssl.SSLObject):
            cert = ssl_object.getpeercert(binary_form=True)
        else:
            cert = None
        return {
            "status": response.status_code,
            "url": request.url,
            "headers": headers,
            "certificate": cert,
            "ip_address": ip_address,
            "protocol": response.http_version,
        }

    @staticmethod
    def _iter_body_chunks(response: httpx.Response) -> AsyncIterator[bytes]:
        return response.aiter_raw()

    @staticmethod
    def _is_dataloss_exception(exc: Exception) -> bool:
        return isinstance(
            exc, httpx.RemoteProtocolError
        ) and "peer closed connection without sending complete message body" in str(exc)

    def _log_tls_info(self, response: httpx.Response, request: Request) -> None:
        network_stream: AsyncNetworkStream = response.extensions["network_stream"]
        extra_ssl_object = network_stream.get_extra_info("ssl_object")
        if isinstance(extra_ssl_object, ssl.SSLObject):
            _log_sslobj_debug_info(extra_ssl_object)

    async def close(self) -> None:
        await self._default_client.aclose()
        for client in self._proxy_clients.values():
            await client.aclose()
