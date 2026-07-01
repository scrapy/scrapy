"""
Sticky Meta Params Spider Middleware

See documentation in docs/topics/spider-middleware.rst
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from scrapy.exceptions import NotConfigured
from scrapy.spidermiddlewares.base import BaseSpiderMiddleware

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.http import Request, Response


class StickyMetaParamsMiddleware(BaseSpiderMiddleware):
    """Copy a configurable list of :attr:`Request.meta <scrapy.http.Request.meta>`
    keys from a response into the follow-up requests of its callback.

    The keys to copy are read from the :setting:`STICKY_META_KEYS` setting.
    Keys already present in a follow-up request are not overwritten.
    """

    def __init__(self, sticky_meta_keys: list[str]):  # pylint: disable=super-init-not-called
        self.sticky_meta_keys: list[str] = sticky_meta_keys

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        sticky_meta_keys = crawler.settings.getlist("STICKY_META_KEYS")
        if not sticky_meta_keys:
            raise NotConfigured
        return cls(sticky_meta_keys)

    def get_processed_request(
        self, request: Request, response: Response | None
    ) -> Request | None:
        if response is None:
            return request
        for key in self.sticky_meta_keys:
            if key in response.meta and key not in request.meta:
                request.meta[key] = response.meta[key]
        return request
