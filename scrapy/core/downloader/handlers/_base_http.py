from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING

from scrapy.utils._download_handlers import get_header_order, normalize_header_order

from .base import BaseDownloadHandler

if TYPE_CHECKING:
    from scrapy import Request
    from scrapy.crawler import Crawler


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
        self._header_order: tuple[bytes, ...] = normalize_header_order(
            crawler.settings.getlist("REQUEST_HEADER_ORDER")
        )

    def _get_header_order(self, request: Request) -> tuple[bytes, ...]:
        return get_header_order(request, self._header_order)
