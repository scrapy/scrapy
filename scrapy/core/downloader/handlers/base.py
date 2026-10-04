from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from scrapy import Request
    from scrapy.crawler import Crawler
    from scrapy.http import Response


class BaseDownloadHandler(ABC):
    """Optional base class for download handlers."""

    lazy: bool = False

    def __init__(self, crawler: Crawler):
        self.crawler = crawler

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls(crawler)

    @abstractmethod
    async def download_request(self, request: Request) -> Response:
        raise NotImplementedError

    async def close(self) -> None:  # noqa: B027
        pass
