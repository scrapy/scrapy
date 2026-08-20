from __future__ import annotations

import ipaddress
import ssl
import time
from socket import gaierror
from typing import TYPE_CHECKING, Any, ClassVar
from weakref import WeakSet

from scrapy.exceptions import (
    CannotResolveHostError,
    DownloadConnectionRefusedError,
    DownloadFailedError,
    DownloadTimeoutError,
    NotConfigured,
    UnsupportedURLSchemeError,
)
from scrapy.http import Headers
from scrapy.http.response.websocket import WebSocketResponse
from scrapy.utils._download_handlers import make_response, normalize_bind_address
from scrapy.utils.asyncio import is_asyncio_available
from scrapy.utils.httpobj import urlparse_cached
from scrapy.utils.ssl import (
    _log_sslobj_debug_info,
    _make_insecure_ssl_ctx,
    _make_ssl_context,
)

from ._base_http import BaseHttpDownloadHandler

if TYPE_CHECKING:
    from scrapy import Request
    from scrapy.crawler import Crawler
    from scrapy.http import Response


HAS_WEBSOCKETS = True

try:
    from websockets.asyncio.client import ClientConnection, connect
    from websockets.exceptions import (
        InvalidProxyStatus,
        InvalidStatus,
        InvalidURI,
        WebSocketException,
    )
except ImportError:
    HAS_WEBSOCKETS = False
else:

    class _Connect(connect):
        """Connector that reports redirects instead of following them, leaving
        them to :class:`~scrapy.downloadermiddlewares.redirect.RedirectMiddleware`."""

        def process_redirect(self, exc: Exception) -> Exception:
            return exc


class WebSocketDownloadHandler(BaseHttpDownloadHandler):
    """Download handler for WebSocket connections."""

    lazy = True

    _DEFAULT_CONNECT_TIMEOUT: ClassVar[float] = 10

    def __init__(self, crawler: Crawler):
        if not HAS_WEBSOCKETS:
            raise NotConfigured(
                f"{type(self).__name__} requires the websockets extra to be"
                f" installed (pip install scrapy[websockets])."
            )
        if not is_asyncio_available():  # pragma: no cover
            raise NotConfigured(
                f"{type(self).__name__} requires the asyncio support. Make"
                f" sure that you have either enabled the asyncio Twisted"
                f" reactor in the TWISTED_REACTOR setting or disabled the"
                f" TWISTED_REACTOR_ENABLED setting. See the asyncio"
                f" documentation of Scrapy for more information."
            )
        super().__init__(crawler)
        self._verify_certificates: bool = crawler.settings.getbool(
            "DOWNLOAD_VERIFY_CERTIFICATES"
        )
        self._ssl_context: ssl.SSLContext = _make_ssl_context(crawler.settings)
        self._compression: str | None = (
            "deflate" if crawler.settings.getbool("COMPRESSION_ENABLED") else None
        )
        self._connections: WeakSet[ClientConnection] = WeakSet()

    async def download_request(self, request: Request) -> Response:
        timeout: float = (
            request.meta.get("download_timeout") or self._DEFAULT_CONNECT_TIMEOUT
        )
        maxsize: int = request.meta.get("download_maxsize", self._default_maxsize)
        kwargs: dict[str, Any] = {}
        if urlparse_cached(request).scheme == "wss":
            kwargs["ssl"] = self._ssl_context
        proxy = self._extract_proxy_url_with_creds(request)
        if proxy and proxy.startswith("https:") and not self._verify_certificates:
            kwargs["proxy_ssl"] = _make_insecure_ssl_ctx()

        start_time = time.monotonic()
        try:
            connection = await _Connect(
                request.url,
                additional_headers=self._request_headers(request).to_tuple_list(),
                # Scrapy sets its own User-Agent header.
                user_agent_header=None,
                # HttpProxyMiddleware is the only source of proxies, so the
                # environment variables that the library reads by default must
                # not be taken into account here.
                proxy=proxy,
                open_timeout=timeout,
                # A max_size of None disables the limit, which is what a
                # DOWNLOAD_MAXSIZE of 0 means.
                max_size=maxsize or None,
                compression=self._compression,
                local_addr=normalize_bind_address(
                    request.meta.get("bindaddress") or self._bind_address
                ),
                **kwargs,
            )
        except InvalidStatus as e:
            return self._make_rejection_response(request, e)
        except TimeoutError as e:
            raise DownloadTimeoutError(
                f"Getting {request.url} took longer than {timeout} seconds."
            ) from e
        except InvalidURI as e:
            raise UnsupportedURLSchemeError(str(e)) from e
        except InvalidProxyStatus as e:
            raise DownloadConnectionRefusedError(str(e)) from e
        except OSError as e:
            if isinstance(e, gaierror):
                raise CannotResolveHostError(str(e)) from e
            raise DownloadConnectionRefusedError(str(e)) from e
        except WebSocketException as e:
            raise DownloadFailedError(str(e)) from e
        finally:
            request.meta["download_latency"] = time.monotonic() - start_time

        # A successful handshake always leaves its response behind.
        assert connection.response is not None
        self._connections.add(connection)
        if self._tls_verbose_logging:
            self._log_tls_info(connection)
        return WebSocketResponse(
            url=request.url,
            status=connection.response.status_code,
            headers=Headers(connection.response.headers.raw_items()),
            certificate=self._get_certificate(connection),
            ip_address=self._get_ip_address(connection),
            protocol="http/1.1",
            connection=connection,
        )

    @staticmethod
    def _make_rejection_response(request: Request, exc: InvalidStatus) -> Response:
        """Turn a handshake response that is not a protocol switch into a
        regular response, so that middlewares such as the redirect and retry
        ones can handle it."""
        return make_response(
            url=request.url,
            status=exc.response.status_code,
            headers=Headers(exc.response.headers.raw_items()),
            body=bytes(exc.response.body),
        )

    @staticmethod
    def _get_ssl_object(connection: ClientConnection) -> ssl.SSLObject | None:
        ssl_object = connection.transport.get_extra_info("ssl_object")
        return ssl_object if isinstance(ssl_object, ssl.SSLObject) else None

    @classmethod
    def _get_certificate(cls, connection: ClientConnection) -> bytes | None:
        ssl_object = cls._get_ssl_object(connection)
        return ssl_object.getpeercert(binary_form=True) if ssl_object else None

    @staticmethod
    def _get_ip_address(
        connection: ClientConnection,
    ) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
        remote_address = connection.remote_address
        return ipaddress.ip_address(remote_address[0]) if remote_address else None

    @classmethod
    def _log_tls_info(cls, connection: ClientConnection) -> None:
        if ssl_object := cls._get_ssl_object(connection):  # pragma: no branch
            _log_sslobj_debug_info(ssl_object)

    async def close(self) -> None:
        for connection in list(self._connections):
            await connection.close()
