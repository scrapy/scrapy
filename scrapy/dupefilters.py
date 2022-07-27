import logging
import os
from typing import Optional, Set, Type, TypeVar
from warnings import warn

from twisted.internet.defer import Deferred

from scrapy.http.request import Request
from scrapy.settings import BaseSettings
from scrapy.spiders import Spider
from scrapy.utils.deprecate import ScrapyDeprecationWarning
from scrapy.utils.job import job_dir
from scrapy.utils.request import referer_str, RequestFingerprinter


BaseDupeFilterTV = TypeVar("BaseDupeFilterTV", bound="BaseDupeFilter")


class BaseDupeFilter:
    @classmethod
    def from_settings(cls: Type[BaseDupeFilterTV], settings: BaseSettings) -> BaseDupeFilterTV:
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


RFPDupeFilterTV = TypeVar("RFPDupeFilterTV", bound="RFPDupeFilter")


class RFPDupeFilter(BaseDupeFilter):
    """Request Fingerprint duplicates filter"""

    def __init__(
        self,
        path: Optional[str] = None,
        debug: bool = False,
        *,
        fingerprinter=None,
    ) -> None:
        self.file = None
        self.fingerprinter = fingerprinter or RequestFingerprinter()
        self.fingerprints: Set[str] = set()
        self.logdupes = True
        self.debug = debug
        self.logger = logging.getLogger(__name__)
        if path:
            self.file = open(os.path.join(path, 'requests.seen'), 'a+')
            self.file.seek(0)
            self.fingerprints.update(x.rstrip() for x in self.file)

    @classmethod
    def from_settings(cls: Type[RFPDupeFilterTV], settings: BaseSettings, *, fingerprinter=None) -> RFPDupeFilterTV:
        debug = settings.getbool('DUPEFILTER_DEBUG')
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
            result.fingerprinter = fingerprinter
            return result

    @classmethod
    def from_crawler(cls, crawler):
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
            self.file.write(fp + '\n')
        return False

    def request_fingerprint(self, request: Request) -> str:
        return self.fingerprinter.fingerprint(request).hex()

    def close(self, reason: str) -> None:
        if self.file:
            self.file.close()

    def log(self, request: Request, spider: Spider) -> None:
        if self.debug:
            msg = "Filtered duplicate request: %(request)s (referer: %(referer)s)"
            args = {'request': request, 'referer': referer_str(request)}
            self.logger.debug(msg, args, extra={'spider': spider})
        elif self.logdupes:
            msg = ("Filtered duplicate request: %(request)s"
                   " - no more duplicates will be shown"
                   " (see DUPEFILTER_DEBUG to show all duplicates)")
            self.logger.debug(msg, {'request': request}, extra={'spider': spider})
            self.logdupes = False

        spider.crawler.stats.inc_value('dupefilter/filtered', spider=spider)
