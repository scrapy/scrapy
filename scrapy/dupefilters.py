from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING
from warnings import warn

from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.utils.deprecate import method_is_overridden
from scrapy.utils.job import job_dir
from scrapy.utils.request import (
    RequestFingerprinter,
    RequestFingerprinterProtocol,
    referer_str,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from twisted.internet.defer import Deferred

    # typing.Self requires Python 3.11
    from typing_extensions import Self

    from scrapy.crawler import Crawler
    from scrapy.http.request import Request
    from scrapy.spiders import Spider


_SIZE_BYTES = 2


def _read_fingerprints(data: bytes) -> Iterator[bytes]:
    pos = 0
    while pos + _SIZE_BYTES <= len(data):
        size = int.from_bytes(data[pos : pos + _SIZE_BYTES], "big")
        pos += _SIZE_BYTES
        fingerprint = data[pos : pos + size]
        if len(fingerprint) < size:
            # Truncated by an unclean shutdown.
            return
        yield fingerprint
        pos += size


class BaseDupeFilter:
    """Dummy duplicate request filtering class (:setting:`DUPEFILTER_CLASS`)
    that does not filter out any request."""

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        return cls()

    def request_seen(self, request: Request) -> bool:
        return False

    def open(self) -> Deferred[None] | None:
        pass

    def close(self, reason: str) -> Deferred[None] | None:
        pass

    def log(self, request: Request, spider: Spider) -> None:
        """Log that a request has been filtered"""
        warn(
            "Calling BaseDupeFilter.log() is deprecated.",
            ScrapyDeprecationWarning,
            stacklevel=2,
        )


class RFPDupeFilter(BaseDupeFilter):
    """Duplicate request filtering class (:setting:`DUPEFILTER_CLASS`) that
    filters out requests with the canonical
    (:func:`w3lib.url.canonicalize_url`) :attr:`~scrapy.http.Request.url`,
    :attr:`~scrapy.http.Request.method` and :attr:`~scrapy.http.Request.body`.

    Job directory contents
    ======================

    .. warning:: The files that this class generates in the :ref:`job directory
        <job-dir>` are an implementation detail, and may change without a
        warning in a future version of Scrapy. Do not rely on the following
        information for anything other than debugging purposes.

    When using :setting:`JOBDIR`, seen fingerprints are tracked in a binary
    file named :file:`requests.seen` in the :ref:`job directory <job-dir>`,
    where each fingerprint is stored as its big-endian, 2-byte length followed
    by the fingerprint itself.
    """

    def __init__(
        self,
        path: str | None = None,
        debug: bool = False,
        *,
        fingerprinter: RequestFingerprinterProtocol | None = None,
    ) -> None:
        self.file = None
        self.fingerprinter: RequestFingerprinterProtocol = (
            fingerprinter or RequestFingerprinter()
        )
        self._fingerprints: set[bytes] = set()
        self.logdupes = True
        self.debug = debug
        self.logger = logging.getLogger(__name__)
        self._legacy_fingerprint = method_is_overridden(
            type(self), RFPDupeFilter, "request_fingerprint"
        )
        if self._legacy_fingerprint:
            warn(
                "Overriding RFPDupeFilter.request_fingerprint() is deprecated,"
                " set the REQUEST_FINGERPRINTER_CLASS setting instead.",
                ScrapyDeprecationWarning,
                stacklevel=2,
            )
        if path:
            self.file = Path(path, "requests.seen").open("a+b")
            self.file.seek(0)
            self._fingerprints.update(_read_fingerprints(self.file.read()))

    @property
    def fingerprints(self) -> frozenset[str]:
        warn(
            "RFPDupeFilter.fingerprints is deprecated.",
            ScrapyDeprecationWarning,
            stacklevel=2,
        )
        return frozenset(fp.hex() for fp in self._fingerprints)

    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        debug = crawler.settings.getbool("DUPEFILTER_DEBUG")
        return cls(
            job_dir(crawler.settings),
            debug,
            fingerprinter=crawler.request_fingerprinter,
        )

    def request_seen(self, request: Request) -> bool:
        fp = self._fingerprint(request)
        if fp in self._fingerprints:
            return True
        self._fingerprints.add(fp)
        if self.file:
            self.file.write(len(fp).to_bytes(_SIZE_BYTES, "big") + fp)
        return False

    def _fingerprint(self, request: Request) -> bytes:
        if self._legacy_fingerprint:
            return bytes.fromhex(self.request_fingerprint(request))
        return self.fingerprinter.fingerprint(request)

    def request_fingerprint(self, request: Request) -> str:
        """Returns a string that uniquely identifies the specified request."""
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

        spider.crawler.stats.inc_value("dupefilter/filtered")
