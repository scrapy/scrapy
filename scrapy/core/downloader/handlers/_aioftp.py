from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
import ssl
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, BinaryIO, ClassVar, NamedTuple
from urllib.parse import unquote, urlsplit

import aioftp
from aioftp.common import SSLSessionBoundContext

from scrapy.exceptions import (
    CannotResolveHostError,
    DownloadConnectionRefusedError,
    DownloadFailedError,
    DownloadTimeoutError,
    NotConfigured,
)
from scrapy.http import Headers
from scrapy.utils._ssl import _log_sslobj_debug_info, _make_ssl_context
from scrapy.utils.httpobj import urlparse_cached

from ._base_streaming import BaseStreamingDownloadHandler, _BaseResponseArgs

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterator

    from scrapy.crawler import Crawler
    from scrapy.http import Response
    from scrapy.http.request import Request


logger = logging.getLogger(__name__)

_TIMEOUT_EXCEPTIONS: tuple[type[Exception], ...] = (asyncio.TimeoutError,)
_CONNECTION_REFUSED_EXCEPTIONS: tuple[type[Exception], ...] = (ConnectionRefusedError,)
_DOWNLOAD_FAILED_EXCEPTIONS: tuple[type[Exception], ...] = (
    aioftp.AIOFTPException,
    ConnectionResetError,
)
_HAS_SOCKS = False
try:
    from python_socks import (
        ProxyConnectionError,
        ProxyError,
        ProxyTimeoutError,
        ProxyType,
    )
    from python_socks.async_.asyncio import Proxy

    _HAS_SOCKS = True
    _TIMEOUT_EXCEPTIONS += (ProxyTimeoutError,)
    _CONNECTION_REFUSED_EXCEPTIONS += (ProxyConnectionError,)
    _DOWNLOAD_FAILED_EXCEPTIONS += (ProxyError,)
except ImportError:  # pragma: no cover
    pass


class _ProxyClient(aioftp.Client):
    """An :class:`aioftp.Client` that opens its connections through
    *proxy*."""

    def __init__(self, proxy: Proxy, **kwargs: Any):
        super().__init__(**kwargs)
        self._proxy = proxy

    async def _open_connection(
        self, host: str, port: int
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        ssl_context = self.ssl
        if self._stream is not None and (
            ssl_object := self._stream.writer.get_extra_info("ssl_object")
        ):
            # data connections reuse the TLS session of the control connection
            ssl_context = SSLSessionBoundContext(
                ssl.PROTOCOL_TLS_CLIENT,
                context=ssl_object.context,
                session=ssl_object.session,
            )
        sock = await self._proxy.connect(host, port, timeout=self.connection_timeout)
        return await asyncio.open_connection(
            sock=sock,
            ssl=ssl_context or None,
            server_hostname=host if ssl_context else None,
        )


class _AioftpResponse(NamedTuple):
    status: int  # mapped to common HTTP status codes
    control: aioftp.ThrottleStreamIO
    data: aioftp.DataConnectionThrottleStreamIO | None


class AioftpDownloadHandler(BaseStreamingDownloadHandler[_AioftpResponse]):
    lazy = True
    experimental: ClassVar[bool] = True

    def __init__(self, crawler: Crawler):
        super().__init__(crawler)
        # aioftp only supports passive mode
        if not crawler.settings.getbool("FTP_PASSIVE_MODE"):
            raise NotConfigured(
                f"{type(self).__name__} does not support disabling FTP_PASSIVE_MODE."
            )
        self._user: str = crawler.settings["FTP_USER"]
        self._password: str = crawler.settings["FTP_PASSWORD"]
        self._ssl_context: ssl.SSLContext = _make_ssl_context(crawler.settings)

    @asynccontextmanager
    async def _make_request(
        self, request: Request, timeout: float
    ) -> AsyncGenerator[_AioftpResponse]:
        url = urlparse_cached(request)
        assert url.hostname
        if not request.meta.get("ftp_passive", True):
            logger.error(
                f"{type(self).__name__} does not support active mode, so the"
                f" 'ftp_passive' request meta key will be ignored for {request}."
            )

        implicit_tls = url.scheme == "ftps" and url.port == 990
        client_kwargs: dict[str, Any] = {
            "socket_timeout": timeout,
            "connection_timeout": timeout,
            "ssl": self._ssl_context if implicit_tls else None,
        }
        proxy = self._get_proxy(request)
        client = (
            _ProxyClient(proxy, **client_kwargs)
            if proxy
            else aioftp.Client(**client_kwargs)
        )
        try:
            await client.connect(url.hostname, url.port or 21)
            if url.scheme == "ftps" and not implicit_tls:
                await client.upgrade_to_tls(self._ssl_context)
            await client.login(
                request.meta.get("ftp_user", self._user),
                request.meta.get("ftp_password", self._password),
            )
            reader, writer = await client.get_passive_connection()
            data = aioftp.DataConnectionThrottleStreamIO(
                client, reader, writer, throttles={}, timeout=timeout
            )
            try:
                await client.command(f"RETR {unquote(url.path)}", "1xx")
            except aioftp.StatusCodeError as e:
                data.close()
                status = 404 if e.received_codes[-1].matches("550") else 503
                yield _AioftpResponse(status, client.stream, None)
            else:
                try:
                    yield _AioftpResponse(200, client.stream, data)
                finally:
                    data.close()
        except _TIMEOUT_EXCEPTIONS as e:
            raise DownloadTimeoutError(
                f"Getting {request.url} took longer than {timeout} seconds."
            ) from e
        except _CONNECTION_REFUSED_EXCEPTIONS as e:
            raise DownloadConnectionRefusedError(str(e)) from e
        except socket.gaierror as e:
            raise CannotResolveHostError(str(e)) from e
        except _DOWNLOAD_FAILED_EXCEPTIONS as e:
            raise DownloadFailedError(str(e)) from e
        finally:
            client.close()

    def _get_proxy(self, request: Request) -> Proxy | None:
        proxy_url = self._extract_proxy_url_with_creds(request)
        if not proxy_url:
            return None
        parts = urlsplit(proxy_url)
        if parts.scheme not in ("socks4", "socks5"):
            raise NotImplementedError(
                f"{type(self).__name__} only supports SOCKS proxies, got {proxy_url!r}."
            )
        if not _HAS_SOCKS:  # pragma: no cover
            raise ValueError(
                f"SOCKS proxy support in {type(self).__name__} requires the"
                f" 'ftp-socks' extra to be installed."
            )
        assert parts.hostname
        return Proxy(
            ProxyType.SOCKS4 if parts.scheme == "socks4" else ProxyType.SOCKS5,
            parts.hostname,
            parts.port or 1080,
            unquote(parts.username) if parts.username else None,
            unquote(parts.password) if parts.password else None,
        )

    @staticmethod
    def _local_filename(response: _AioftpResponse, request: Request) -> bytes | None:
        if response.data is None:
            return None
        return request.meta.get("ftp_local_filename")

    def _open_body_buffer(
        self, response: _AioftpResponse, request: Request
    ) -> BinaryIO:
        if local_filename := self._local_filename(response, request):
            return Path(local_filename.decode()).open("wb")
        return super()._open_body_buffer(response, request)

    def _get_body(
        self, buffer: BinaryIO, response: _AioftpResponse, request: Request
    ) -> bytes:
        if local_filename := self._local_filename(response, request):
            return local_filename
        return super()._get_body(buffer, response, request)

    async def _read_response(
        self, response: _AioftpResponse, request: Request
    ) -> Response:
        result = await super()._read_response(response, request)
        if response.data is not None:
            self._add_ftp_headers(result, response, request)
        return result

    def _add_ftp_headers(
        self, result: Response, response: _AioftpResponse, request: Request
    ) -> None:
        if local_filename := self._local_filename(response, request):
            size = Path(local_filename.decode()).stat().st_size
        else:
            size = len(result.body)
        result.headers.update({"Local Filename": local_filename or b"", "Size": size})

    @staticmethod
    def _extract_headers(response: _AioftpResponse) -> Headers:
        return Headers()

    @staticmethod
    def _build_base_response_args(
        response: _AioftpResponse,
        request: Request,
        headers: Headers,
    ) -> _BaseResponseArgs:
        peername = response.control.writer.get_extra_info("peername")
        ssl_object = response.control.writer.get_extra_info("ssl_object")
        cert = ssl_object.getpeercert(binary_form=True) if ssl_object else None
        return {
            "status": response.status,
            "url": request.url,
            "certificate": cert,
            "protocol": "FTP",
            "ip_address": ipaddress.ip_address(peername[0]),
            "headers": headers,
        }

    @staticmethod
    async def _iter_body_chunks(response: _AioftpResponse) -> AsyncIterator[bytes]:
        if response.data is None:
            return
        async for chunk in response.data.iter_by_block():
            yield chunk
        # raises StatusCodeError if the server reports a failed transfer
        await response.data.finish()

    @staticmethod
    def _is_dataloss_exception(exc: Exception) -> bool:
        return isinstance(exc, aioftp.StatusCodeError)

    def _log_tls_info(self, response: _AioftpResponse, request: Request) -> None:
        if ssl_object := response.control.writer.get_extra_info("ssl_object"):
            _log_sslobj_debug_info(ssl_object)
