from __future__ import annotations

import base64
import logging
import time
from abc import ABC, abstractmethod
from io import BytesIO
from typing import TYPE_CHECKING, Any, ClassVar, Generic, NoReturn, TypedDict, TypeVar
from urllib.parse import quote, urlsplit

from scrapy import Request, signals
from scrapy.exceptions import (
    DownloadCancelledError,
    NotConfigured,
    ResponseDataLossError,
)
from scrapy.utils._download_handlers import (
    check_stop_download,
    get_dataloss_msg,
    get_maxsize_msg,
    get_warnsize_msg,
    make_response,
    normalize_bind_address,
)
from scrapy.utils.asyncio import is_asyncio_available
from scrapy.utils.url import add_http_if_no_scheme

from ._base_http import BaseHttpDownloadHandler

if TYPE_CHECKING:
    from collections.abc import AsyncIterable
    from contextlib import AbstractAsyncContextManager
    from ipaddress import IPv4Address, IPv6Address

    from _typeshed import SizedBuffer

    # typing.NotRequired requires Python 3.11
    from typing_extensions import NotRequired

    from scrapy.crawler import Crawler
    from scrapy.http import Headers, Response


logger = logging.getLogger(__name__)

_ResponseT = TypeVar("_ResponseT")


class _BaseResponseArgs(TypedDict):
    status: int
    url: str
    headers: Headers
    certificate: NotRequired[Any]
    ip_address: NotRequired[IPv4Address | IPv6Address | None]
    protocol: str | None


class BaseStreamingDownloadHandler(BaseHttpDownloadHandler, ABC, Generic[_ResponseT]):
    """A base class for HTTP download handlers that follow the streaming logic flow."""

    _DEFAULT_CONNECT_TIMEOUT: ClassVar[float] = 10
    experimental: ClassVar[bool] = False
    requires_asyncio: ClassVar[bool] = True
    # require subclasses to disable proxies explicitly with an explanation
    supports_proxies: ClassVar[bool] = True
    supports_per_request_bindaddress: ClassVar[bool] = False

    def __init__(self, crawler: Crawler):
        if self.requires_asyncio and not is_asyncio_available():  # pragma: no cover
            raise NotConfigured(
                f"{type(self).__name__} requires the asyncio support. Make"
                f" sure that you have either enabled the asyncio Twisted"
                f" reactor in the TWISTED_REACTOR setting or disabled the"
                f" TWISTED_REACTOR_ENABLED setting. See the asyncio documentation"
                f" of Scrapy for more information."
            )
        self._check_deps_installed()
        super().__init__(crawler)
        if self.experimental:
            logger.warning(
                f"{type(self).__name__} is experimental and is not recommended for production use."
            )
        self._bind_address = normalize_bind_address(
            crawler.settings.get("DOWNLOAD_BIND_ADDRESS")
        )
        self._proxy_auth_encoding: str = crawler.settings.get("HTTPPROXY_AUTH_ENCODING")
        # these are useful for many handlers but used in different ways by them
        self._pool_size_total: int = crawler.settings.getint("CONCURRENT_REQUESTS")
        self._pool_size_per_host: int = crawler.settings.getint(
            "CONCURRENT_REQUESTS_PER_DOMAIN"
        )

    @staticmethod
    @abstractmethod
    def _check_deps_installed() -> None:
        """Raise NotConfigured if the required deps are not installed."""
        raise NotImplementedError

    @abstractmethod
    def _make_request(
        self, request: Request, timeout: float
    ) -> AbstractAsyncContextManager[_ResponseT]:
        """Return an async context manager yielding the library-specific response.

        Exceptions raised by the library should be reraised as Scrapy-specific ones.
        """
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def _extract_headers(response: _ResponseT) -> Headers:
        """Convert library-specific response headers to a
        :class:`~scrapy.http.headers.Headers` object."""
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def _build_base_response_args(
        response: _ResponseT, request: Request, headers: Headers
    ) -> _BaseResponseArgs:
        """Build kwargs for :func:`scrapy.utils._download_handlers.make_response`."""
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def _iter_body_chunks(response: _ResponseT) -> AsyncIterable[SizedBuffer]:
        """Return an async iterable yielding body chunks from the response."""
        raise NotImplementedError

    @staticmethod
    @abstractmethod
    def _is_dataloss_exception(exc: Exception) -> bool:
        """Return True if ``exc`` represents dataloss."""
        raise NotImplementedError

    def _log_tls_info(self, response: _ResponseT, request: Request) -> None:
        """Log TLS connection details, if possible."""

    async def download_request(self, request: Request) -> Response:
        if not self.supports_proxies and request.meta.get("proxy"):
            raise NotImplementedError(f"{type(self).__name__} doesn't support proxies.")
        if not self.supports_per_request_bindaddress and request.meta.get(
            "bindaddress"
        ):
            logger.error(
                f"The 'bindaddress' request meta key is not supported by"
                f" {type(self).__name__} and will be ignored."
            )
        timeout: float = request.meta.get(
            "download_timeout", self._DEFAULT_CONNECT_TIMEOUT
        )
        start_time = time.monotonic()
        async with self._make_request(request, timeout) as response:
            request.meta["download_latency"] = time.monotonic() - start_time
            return await self._read_response(response, request)

    async def _read_response(self, response: _ResponseT, request: Request) -> Response:
        maxsize: int = request.meta.get("download_maxsize", self._default_maxsize)
        warnsize: int = request.meta.get("download_warnsize", self._default_warnsize)

        headers = self._extract_headers(response)
        content_length = headers.get("Content-Length")
        expected_size = int(content_length) if content_length is not None else None
        if maxsize and expected_size and expected_size > maxsize:
            self._cancel_maxsize(expected_size, maxsize, request, expected=True)

        reached_warnsize = False
        if warnsize and expected_size and expected_size > warnsize:
            reached_warnsize = True
            logger.warning(
                get_warnsize_msg(expected_size, warnsize, request, expected=True)
            )

        make_response_base_args = self._build_base_response_args(
            response, request, headers
        )

        if self._tls_verbose_logging:
            self._log_tls_info(response, request)

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
            async for chunk in self._iter_body_chunks(response):
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
        except Exception as e:
            if not self._is_dataloss_exception(e):
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
            if not self._fail_on_dataloss_warned:
                logger.warning(get_dataloss_msg(request.url))
                self._fail_on_dataloss_warned = True
            raise ResponseDataLossError(str(e)) from e

        return make_response(
            **make_response_base_args,
            body=response_body.getvalue(),
        )

    def _get_bind_address_host(self) -> str | None:
        """Return the host portion of the bind address.

        Needed for handlers that don't support the bind port.
        """
        if self._bind_address is None:
            return None
        host, port = self._bind_address
        if port != 0:
            logger.warning(
                "DOWNLOAD_BIND_ADDRESS specifies a port (%s), but %s does not "
                "support binding to a specific local port. Ignoring the port "
                "and binding only to %r.",
                port,
                type(self).__name__,
                host,
            )
        return host

    @staticmethod
    def _cancel_maxsize(
        size: int, limit: int, request: Request, *, expected: bool
    ) -> NoReturn:
        warning_msg = get_maxsize_msg(size, limit, request, expected=expected)
        logger.warning(warning_msg)
        raise DownloadCancelledError(warning_msg)

    @staticmethod
    def _extract_proxy(request: Request) -> tuple[str | None, str | None]:
        """Return a tuple of the proxy URL with a scheme and the value of the
        Proxy-Authorization header.

        This is useful for handlers that take the proxy headers separately.
        """
        proxy: str | None = request.meta.get("proxy")
        if not proxy:
            return None, None
        proxy = add_http_if_no_scheme(proxy)
        auth_header: list[bytes] | None = request.headers.pop(
            b"Proxy-Authorization", None
        )
        return proxy, auth_header[0].decode("ascii") if auth_header else None

    def _extract_proxy_url_with_creds(self, request: Request) -> str | None:
        """Return the proxy URL with the userinfo added based on the
        Proxy-Authorization header.

        This is useful for handlers that cannot take the proxy headers
        separately.
        """
        proxy_url, auth_header = self._extract_proxy(request)
        if proxy_url is None or auth_header is None:
            return proxy_url
        scheme, token = auth_header.split(" ", 1)
        if scheme != "Basic":
            raise ValueError(
                f"Expected Basic auth in Proxy-Authorization, got {scheme}"
            )
        user, password = (
            base64.b64decode(token).decode(self._proxy_auth_encoding).split(":", 1)
        )
        parts = urlsplit(proxy_url)
        netloc = f"{quote(user)}:{quote(password)}@{parts.netloc}"
        return parts._replace(netloc=netloc).geturl()
