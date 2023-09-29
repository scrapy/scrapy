from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Set
from warnings import warn

from twisted.internet.defer import Deferred

from scrapy.http.request import Request
from scrapy.settings import BaseSettings
from scrapy.spiders import Spider
from scrapy.utils.deprecate import ScrapyDeprecationWarning
from scrapy.utils.job import job_dir
from scrapy.utils.request import (
    RequestFingerprinter,
    RequestFingerprinterProtocol,
    referer_str,
)

if TYPE_CHECKING:
    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler


class BaseDupeFilter:
    @classmethod
    def from_settings(cls, settings: BaseSettings) -> Self:
        return cls()

    def request_seen(self, request: Request) -> bool:
        return False

    def open(self) -> Optional[Deferred]:
        pass

    def close(self, reason: str) -> Optional[Deferred]:
        pass

    def log(self, request: Request, spider: Spider) -> None:
        """Log that a request has been filtered"""
        pass


class RFPDupeFilter(BaseDupeFilter):
    """Request Fingerprint duplicates filter"""

    def __init__(
        self,
        path: Optional[str] = None,
        debug: bool = False,
        *,
        fingerprinter: Optional[RequestFingerprinterProtocol] = None,
    ) -> None:
        self.file = None
        self.fingerprinter: RequestFingerprinterProtocol = (
            fingerprinter or RequestFingerprinter()
        )
        self.fingerprints: Set[str] = set()
        self.logdupes = True
        self.debug = debug
        self.logger = logging.getLogger(__name__)
        if path:
            self.file = Path(path, "requests.seen").open("a+", encoding="utf-8")
            self.file.seek(0)
            self.fingerprints.update(x.rstrip() for x in self.file)

    @classmethod
    def from_settings(
        cls,
        settings: BaseSettings,
        *,
        fingerprinter: Optional[RequestFingerprinterProtocol] = None,
    ) -> Self:
        debug = settings.getbool("DUPEFILTER_DEBUG")
        try:
            return cls(job_dir(settings), debug, fingerprinter=fingerprinter)
        except TypeError:
            warn(
                "RFPDupeFilter subclasses must either modify their '__init__' "
                "method to support a 'fingerprinter' parameter or reimplement "
                "the 'from_settings' class method.",
                ScrapyDeprecationWarning,
            )
            result = cls(job_dir(settings), debug)
            result.fingerprinter = fingerprinter or RequestFingerprinter()
            return result

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        assert crawler.request_fingerprinter
        try:
            return cls.from_settings(
                crawler.settings,
                fingerprinter=crawler.request_fingerprinter,
            )
        except TypeError:
            warn(
                "RFPDupeFilter subclasses must either modify their overridden "
                "'__init__' method and 'from_settings' class method to "
                "support a 'fingerprinter' parameter, or reimplement the "
                "'from_crawler' class method.",
                ScrapyDeprecationWarning,
            )
            result = cls.from_settings(crawler.settings)
            result.fingerprinter = crawler.request_fingerprinter
            return result

    def request_seen(self, request: Request) -> bool:
        fp = self.request_fingerprint(request)
        if fp in self.fingerprints:
            return True
        self.fingerprints.add(fp)
        if self.file:
            self.file.write(fp + "\n")
        return False

    def request_fingerprint(self, request: Request) -> str:
        return self.fingerprinter.fingerprint(request).hex()

    def close(self, reason: str) -> None:
        if self.file:
            self.file.close()

    def log(self, request: Request, spider: Spider) -> None:
        if self.debug:
            msg = "Filtered duplicate request: %(request)s (referer: %(referer)s)"
            args = {"request": request, "referer": referer_str(request)}
            self.logger.debug(msg, args, extra={"spider": spider})
        elif self.logdupes:
            msg = (
                "Filtered duplicate request: %(request)s"
                " - no more duplicates will be shown"
                " (see DUPEFILTER_DEBUG to show all duplicates)"
            )
            self.logger.debug(msg, {"request": request}, extra={"spider": spider})
            self.logdupes = False

        assert spider.crawler.stats
        spider.crawler.stats.inc_value("dupefilter/filtered", spider=spider)
