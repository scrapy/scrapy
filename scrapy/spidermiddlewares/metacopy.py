from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from scrapy.spidermiddlewares.base import BaseSpiderMiddleware

if TYPE_CHECKING:
    from scrapy.crawler import Crawler
    from scrapy.http import Request, Response


logger = logging.getLogger(__name__)


class MetaCopyDetectionMiddleware(BaseSpiderMiddleware):
    """Warn when a spider yields a request with internal meta keys that should
    not be copied from response.meta, or when two requests share the same meta
    dict object.

    Each warning is emitted at most once per crawl.
    """

    _INTERNAL_KEYS: frozenset[str] = frozenset(
        {
            "_auth_proxy",
            "_dont_cache",
            "_scheme_proxy",
            "download_latency",
            "redirect_reasons",
            "redirect_times",
            "redirect_ttl",
            "redirect_urls",
            "retry_times",
        }
    )

    def __init__(self, crawler: Crawler) -> None:
        super().__init__(crawler)
        skip = frozenset(crawler.settings.getlist("META_COPY_WARN_SKIP_KEYS", []))
        self._keys: frozenset[str] = self._INTERNAL_KEYS - skip
        self._warned: bool = False

    def get_processed_request(
        self, request: Request, response: Response | None
    ) -> Request | None:
        if response is None:
            return request

        if not self._warned:
            found = self._keys & request.meta.keys()
            if found:
                spider_name = type(self.crawler.spider).__name__
                logger.warning(
                    f"{spider_name} yielded a request containing internal "
                    f"meta keys that were likely copied from response.meta "
                    f"and should not be forwarded to new requests: "
                    f"{sorted(found)}. See the MetaCopyDetectionMiddleware "
                    f"documentation for more information. Source response: "
                    f"{response}, target request: {request}",
                    extra={"spider": self.crawler.spider},
                )
                self._warned = True

        return request
