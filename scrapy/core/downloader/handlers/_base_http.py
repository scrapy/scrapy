from __future__ import annotations

import base64
import logging
import sys
from abc import ABC
from typing import TYPE_CHECKING
from urllib.parse import quote, urlsplit

from scrapy.utils._download_handlers import normalize_bind_address
from scrapy.utils.url import _add_http_if_no_scheme

from .base import BaseDownloadHandler

try:
    # stdlib's resource module is only available on unix platforms
    import resource
except ImportError:
    resource = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from scrapy import Request
    from scrapy.crawler import Crawler
    from scrapy.http import Headers
    from scrapy.settings import BaseSettings


logger = logging.getLogger(__name__)

# The number of sockets that select() accepts in CPython's Windows build; see
# FD_SETSIZE in Modules/selectmodule.c.
_FD_SETSIZE = 512

# Room left for the sockets that a Windows crawl registers with the event loop
# outside of download handlers, e.g. the asyncio self-pipe and the telnet
# console.
_WINDOWS_RESERVED_SOCKETS = 32


def _auto_connection_limit() -> int:
    if sys.platform == "win32":
        return _FD_SETSIZE - _WINDOWS_RESERVED_SOCKETS
    soft_limit: int = resource.getrlimit(resource.RLIMIT_NOFILE)[0]
    if soft_limit == resource.RLIM_INFINITY:
        return 0
    return soft_limit // 2


def _get_connection_limit(settings: BaseSettings) -> int:
    limit = settings.get("CONCURRENT_CONNECTIONS_PER_HANDLER")
    limit = _auto_connection_limit() if limit is None else int(limit)
    concurrent_requests = settings.getint("CONCURRENT_REQUESTS")
    if 0 < limit < concurrent_requests:
        logger.warning(
            f"CONCURRENT_CONNECTIONS_PER_HANDLER ({limit}) is lower than"
            f" CONCURRENT_REQUESTS ({concurrent_requests}), which keeps the"
            f" crawl from reaching the configured concurrency."
        )
    return limit


class BaseHttpDownloadHandler(BaseDownloadHandler, ABC):
    """Base class for built-in HTTP download handlers."""

    def __init__(self, crawler: Crawler):
        super().__init__(crawler)
        self._default_maxsize: int = crawler.settings.getint("DOWNLOAD_MAXSIZE")
        self._default_warnsize: int = crawler.settings.getint("DOWNLOAD_WARNSIZE")
        self._fail_on_dataloss: bool = crawler.settings.getbool(
            "DOWNLOAD_FAIL_ON_DATALOSS"
        )
        self._tls_verbose_logging: bool = crawler.settings.getbool(
            "DOWNLOADER_CLIENT_TLS_VERBOSE_LOGGING"
        )
        self._fail_on_dataloss_warned: bool = False
        self._bind_address: tuple[str, int] | None = normalize_bind_address(
            crawler.settings.get("DOWNLOAD_BIND_ADDRESS")
        )
        self._proxy_auth_encoding: str = crawler.settings.get("HTTPPROXY_AUTH_ENCODING")
        # these are useful for many handlers but used in different ways by them
        self._pool_size_total: int = _get_connection_limit(crawler.settings)
        self._pool_size_per_host: int = crawler.settings.getint(
            "CONCURRENT_REQUESTS_PER_DOMAIN"
        )
        self._keepalive_timeout: float = crawler.settings.getfloat(
            "CONNECTION_KEEPALIVE_TIMEOUT"
        )

    @staticmethod
    def _request_headers(request: Request) -> Headers:
        """Get a prepared copy of the request headers.

        This removes the Proxy-Authorization header.
        """
        headers = request.headers.copy()
        headers.pop(b"Proxy-Authorization", None)
        return headers

    def _utf8_request_headers(self, request: Request) -> list[tuple[str, str]]:
        """Get a prepared copy of the request headers as ``(name, value)`` str
        pairs, for libraries that can only send UTF-8.

        Bytes that are not valid UTF-8 are replaced with U+FFFD, with a
        warning.
        """
        pairs: list[tuple[str, str]] = []
        for name, values in self._request_headers(request).items():
            for value in values:
                try:
                    pairs.append((name.decode(), value.decode()))
                except UnicodeDecodeError:
                    str_name = name.decode(errors="replace")
                    logger.warning(
                        f"The {str_name} header of {request} is not valid UTF-8,"
                        f" which {type(self).__name__} cannot send. Sending it"
                        f" with U+FFFD in place of the invalid bytes."
                    )
                    pairs.append((str_name, value.decode(errors="replace")))
        return pairs

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
    def _extract_proxy(request: Request) -> tuple[str | None, str | None]:
        """Return a tuple of the proxy URL with a scheme and the value of the
        Proxy-Authorization header.

        This is useful for handlers that take the proxy headers separately.
        """
        proxy: str | None = request.meta.get("proxy")
        if not proxy:
            return None, None
        proxy = _add_http_if_no_scheme(proxy)
        auth_header: bytes | None = request.headers.get(b"Proxy-Authorization")
        return proxy, auth_header.decode("ascii") if auth_header else None

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
