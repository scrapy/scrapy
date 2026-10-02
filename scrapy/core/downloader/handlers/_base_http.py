from __future__ import annotations

import logging
import sys
from abc import ABC
from typing import TYPE_CHECKING

from .base import BaseDownloadHandler

try:
    # stdlib's resource module is only available on unix platforms
    import resource
except ImportError:
    resource = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from scrapy.crawler import Crawler
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
        # these are useful for many handlers but used in different ways by them
        self._pool_size_total: int = _get_connection_limit(crawler.settings)
        self._pool_size_per_host: int = crawler.settings.getint(
            "CONCURRENT_REQUESTS_PER_DOMAIN"
        )
        self._keepalive_timeout: float = crawler.settings.getfloat(
            "CONNECTION_KEEPALIVE_TIMEOUT"
        )
