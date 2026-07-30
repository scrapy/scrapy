from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING

from .base import BaseDownloadHandler

if TYPE_CHECKING:
    from scrapy.crawler import Crawler
    from scrapy.settings import BaseSettings


class BaseHttpDownloadHandler(BaseDownloadHandler, ABC):
    """Base class for built-in HTTP download handlers."""

    @staticmethod
    def _max_per_host_concurrency(settings: BaseSettings) -> int:
        """Highest per-host concurrency the throttler may admit: the per-domain
        limit, the default ``other``-scope limit, and any explicit per-scope
        concurrency.

        Per-scope concurrency is read from both :setting:`THROTTLING_SCOPES` and
        the deprecated :setting:`DOWNLOAD_SLOTS`, since the throttler honors a
        limit coming from either one (see
        :meth:`~scrapy.throttler.Throttler._merge_download_slots`).

        Since :setting:`CONCURRENT_REQUESTS` caps the total number of requests
        in flight, no host can ever exceed it, so it is also the upper bound of
        the result.
        """
        global_concurrency = settings.getint("CONCURRENT_REQUESTS")
        candidates = [
            settings.getint("CONCURRENT_REQUESTS_PER_DOMAIN"),
            settings.getint("THROTTLING_SCOPE_CONCURRENCY"),
        ]
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
