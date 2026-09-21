from __future__ import annotations

import asyncio
import ipaddress
import socket
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, ClassVar, NamedTuple
from urllib.parse import unquote

import aioftp

from scrapy.exceptions import (
    CannotResolveHostError,
    DownloadConnectionRefusedError,
    DownloadFailedError,
    DownloadTimeoutError,
    NotConfigured,
)
from scrapy.http import Headers
from scrapy.utils._ssl import _log_sslobj_debug_info, _make_ssl_context
from scrapy.utils.asyncgen import as_async_generator
from scrapy.utils.httpobj import urlparse_cached

from ._base_streaming import BaseStreamingDownloadHandler, _BaseResponseArgs

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterator
    from ssl import SSLContext

    from scrapy.crawler import Crawler
    from scrapy.http.request import Request


class _AioftpResponse(NamedTuple):
    status: int  # mapped to common HTTP status codes
    control: aioftp.ThrottleStreamIO
    data: aioftp.DataConnectionThrottleStreamIO | None


class AioftpDownloadHandler(BaseStreamingDownloadHandler[_AioftpResponse]):
    experimental: ClassVar[bool] = True
    supports_proxies: ClassVar[bool] = False

    def __init__(self, crawler: Crawler):
        super().__init__(crawler)
        if not crawler.settings.getbool("FTP_PASSIVE_MODE", True):
            raise NotConfigured(
                "Cannot disable FTP_PASSIVE_MODE when using AioftpDownloadHandler"
            )
        self.user: str = crawler.settings.get("FTP_USER", aioftp.DEFAULT_USER)
        self.password: str = crawler.settings.get("FTP_PASSWORD", aioftp.DEFAULT_PASSWORD)
        self._ssl_context: SSLContext = _make_ssl_context(crawler.settings)

    @asynccontextmanager
    async def _make_request(
        self, request: Request, timeout: float
    ) -> AsyncGenerator[_AioftpResponse]:
        url = urlparse_cached(request)
        assert url.hostname

        client = aioftp.Client(
            socket_timeout=timeout,
            connection_timeout=timeout,
            path_timeout=timeout,
            ssl=self._ssl_context if url.scheme == "ftps" and url.port == 990 else None,
        )
        try:
            await client.connect(url.hostname, url.port or 21)
            if url.scheme == "ftps" and url.port != 990:
                await client.upgrade_to_tls(self._ssl_context)
            await client.login(self.user, self.password)

            try:
                async with client.download_stream(unquote(url.path)) as data_stream:
                    yield _AioftpResponse(200, client.stream, data_stream)
            except aioftp.StatusCodeError as e:
                if e.received_codes[0].matches("4xx"):  # Transient Negative Completion
                    yield _AioftpResponse(500, client.stream, None)
                elif e.received_codes[0].matches("550"):  # File unavailable
                    yield _AioftpResponse(404, client.stream, None)
                else:
                    raise

            await client.quit()
        except asyncio.TimeoutError as e:
            raise DownloadTimeoutError(
                f"Getting {request.url} took longer than {timeout} seconds."
            ) from e
        except ConnectionRefusedError as e:
            raise DownloadConnectionRefusedError(str(e)) from e
        except socket.gaierror as e:
            raise CannotResolveHostError(str(e)) from e
        except aioftp.AIOFTPException as e:
            raise DownloadFailedError(str(e)) from e
        finally:
            client.close()

    @staticmethod
    def _extract_headers(response: _AioftpResponse) -> Headers:
        return Headers(())

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
    def _iter_body_chunks(response: _AioftpResponse) -> AsyncIterator[bytes]:
        if response.data is None:
            return as_async_generator(())
        return response.data.iter_by_block()

    @staticmethod
    def _is_dataloss_exception(exc: Exception) -> bool:
        return False

    def _log_tls_info(self, response: _AioftpResponse, request: Request) -> None:
        for conn in (response.control, response.data):
            if conn and (ssl_object := conn.writer.get_extra_info("ssl_object")):
                _log_sslobj_debug_info(ssl_object)
