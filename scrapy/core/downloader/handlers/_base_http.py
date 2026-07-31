from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING

from scrapy.throttler import _default_scope_concurrency

from .base import BaseDownloadHandler

if TYPE_CHECKING:
    from scrapy.crawler import Crawler
    from scrapy.settings import BaseSettings


class BaseHttpDownloadHandler(BaseDownloadHandler, ABC):
    """Base class for built-in HTTP download handlers."""

    @staticmethod
    def _max_per_host_concurrency(settings: BaseSettings) -> int:
        """Highest per-host concurrency the throttler may admit: the default
        per-scope limit and any explicit per-scope concurrency.

        The default is whichever of :setting:`THROTTLING_SCOPE_CONCURRENCY` and
        the deprecated :setting:`CONCURRENT_REQUESTS_PER_DOMAIN` the throttler
        actually applies, rather than the highest of the two, so that a
        :setting:`THROTTLING_SCOPE_CONCURRENCY` set below the deprecated
        setting's default is not read as the higher value.

        Per-scope concurrency is read from both :setting:`THROTTLING_SCOPES` and
        the deprecated :setting:`DOWNLOAD_SLOTS`, since the throttler honors a
        limit coming from either one (see
        :meth:`~scrapy.throttler.Throttler._merge_download_slots`).

        Since :setting:`CONCURRENT_REQUESTS` caps the total number of requests
        in flight, no host can ever exceed it, so it is also the upper bound of
        the result.

        This reads the configured values, so a component that raises a scope
        concurrency at run time (through
        :meth:`~scrapy.throttler.ThrottlingScopeManagerProtocol.set_concurrency`),
        or a custom :setting:`THROTTLING_SCOPE_MANAGER` that takes its limit from
        elsewhere, can leave the result below what the throttler admits. That
        only makes the extra requests queue inside the download handler, waiting
        for a connection instead of for the network.
        """
        global_concurrency = settings.getint("CONCURRENT_REQUESTS")
        candidates = [_default_scope_concurrency(settings)]
        candidates += [
            int(scope["concurrency"])
            for setting in ("THROTTLING_SCOPES", "DOWNLOAD_SLOTS")
            for scope in settings.getdict(setting).values()
            if "concurrency" in scope
        ]
        if not global_concurrency:
            return max(candidates)
        return min(max(candidates), global_concurrency)

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
