from __future__ import annotations

import hashlib
import logging
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from scrapy.core.scheduler import Scheduler
from scrapy.dupefilters import BaseDupeFilter, DiskDupeFilter, RFPDupeFilter
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.http import Request
from scrapy.utils.python import to_bytes
from scrapy.utils.test import get_crawler
from tests.spiders import SimpleSpider

if TYPE_CHECKING:
    from scrapy.crawler import Crawler


def _get_dupefilter(
    *,
    crawler: Crawler | None = None,
    settings: dict[str, Any] | None = None,
    open_: bool = True,
) -> BaseDupeFilter:
    if crawler is None:
        crawler = get_crawler(settings_dict=settings)
    scheduler = Scheduler.from_crawler(crawler)
    dupefilter = scheduler.df
    if open_:
        dupefilter.open()
    return dupefilter


class FromCrawlerRFPDupeFilter(RFPDupeFilter):
    @classmethod
    def from_crawler(cls, crawler):
        df = super().from_crawler(crawler)
        df.method = "from_crawler"
        return df


class DirectDupeFilter:
    method = "n/a"


class DupeFilterTestMixin:
    """Tests that every :setting:`DUPEFILTER_CLASS` based on request
    fingerprints must pass, regardless of where it stores them."""

    dupefilter_class: type[BaseDupeFilter]

    def _get_dupefilter(self, **settings: Any) -> BaseDupeFilter:
        return _get_dupefilter(
            settings={"DUPEFILTER_CLASS": self.dupefilter_class, **settings}
        )

    def test_filter(self) -> None:
        dupefilter = self._get_dupefilter()
        r1 = Request("https://example.com/1")
        r2 = Request("https://example.com/2")
        r3 = Request("https://example.com/2")

        assert not dupefilter.request_seen(r1)
        assert dupefilter.request_seen(r1)

        assert not dupefilter.request_seen(r2)
        assert dupefilter.request_seen(r3)

        dupefilter.close("finished")

    def test_jobdir(self, tmp_path: Path) -> None:
        r1 = Request("https://example.com/1")
        r2 = Request("https://example.com/2")

        dupefilter = self._get_dupefilter(JOBDIR=str(tmp_path))
        assert not dupefilter.request_seen(r1)
        dupefilter.close("finished")

        resumed = self._get_dupefilter(JOBDIR=str(tmp_path))
        assert resumed.request_seen(r1)
        assert not resumed.request_seen(r2)
        resumed.close("finished")

    def test_fingerprinter(self) -> None:
        r1 = Request("https://example.com/index.html")
        r2 = Request("https://example.com/INDEX.html")

        dupefilter = self._get_dupefilter()
        assert not dupefilter.request_seen(r1)
        assert not dupefilter.request_seen(r2)
        dupefilter.close("finished")

        class CaseInsensitiveRequestFingerprinter:
            def fingerprint(self, request: Request) -> bytes:
                return hashlib.sha1(to_bytes(request.url.lower())).digest()

        case_insensitive_dupefilter = self._get_dupefilter(
            REQUEST_FINGERPRINTER_CLASS=CaseInsensitiveRequestFingerprinter
        )
        assert not case_insensitive_dupefilter.request_seen(r1)
        assert case_insensitive_dupefilter.request_seen(r2)
        case_insensitive_dupefilter.close("finished")


class TestRFPDupeFilter(DupeFilterTestMixin):
    dupefilter_class = RFPDupeFilter

    def test_df_from_crawler_scheduler(self):
        settings = {
            "DUPEFILTER_DEBUG": True,
            "DUPEFILTER_CLASS": FromCrawlerRFPDupeFilter,
        }
        crawler = get_crawler(settings_dict=settings)
        scheduler = Scheduler.from_crawler(crawler)
        assert scheduler.df.debug
        assert scheduler.df.method == "from_crawler"

    def test_df_direct_scheduler(self):
        settings = {
            "DUPEFILTER_CLASS": DirectDupeFilter,
        }
        crawler = get_crawler(settings_dict=settings)
        scheduler = Scheduler.from_crawler(crawler)
        assert scheduler.df.method == "n/a"

    def test_seenreq_truncated(self):
        r1 = Request("http://scrapytest.org/1")
        r2 = Request("http://scrapytest.org/2")

        path = tempfile.mkdtemp()
        try:
            df = _get_dupefilter(settings={"JOBDIR": path}, open_=False)
            try:
                df.open()
                df.request_seen(r1)
                df.request_seen(r2)
            finally:
                df.close("finished")

            seen_file = Path(path, "requests.seen")
            seen_file.write_bytes(seen_file.read_bytes()[:-1])

            df2 = _get_dupefilter(settings={"JOBDIR": path}, open_=False)
            try:
                df2.open()
                assert df2.request_seen(r1)
                assert not df2.request_seen(r2)
            finally:
                df2.close("finished")
        finally:
            shutil.rmtree(path)

    def test_log(self, caplog: pytest.LogCaptureFixture) -> None:
        settings = {
            "DUPEFILTER_DEBUG": False,
            "DUPEFILTER_CLASS": FromCrawlerRFPDupeFilter,
        }
        crawler = get_crawler(SimpleSpider, settings_dict=settings)
        spider = SimpleSpider.from_crawler(crawler)
        dupefilter = _get_dupefilter(crawler=crawler)

        r1 = Request("http://scrapytest.org/index.html")
        r2 = Request("http://scrapytest.org/index.html")

        with caplog.at_level(logging.DEBUG):
            dupefilter.log(r1, spider)
            dupefilter.log(r2, spider)

        assert crawler.stats
        assert crawler.stats.get_value("dupefilter/filtered") == 2
        assert (
            "scrapy.dupefilters",
            logging.DEBUG,
            "Filtered duplicate request: <GET http://scrapytest.org/index.html> - no more"
            " duplicates will be shown (see DUPEFILTER_DEBUG to show all duplicates)",
        ) in caplog.record_tuples

        dupefilter.close("finished")

    @pytest.mark.parametrize("df", [None, FromCrawlerRFPDupeFilter])
    def test_log_debug(
        self, caplog: pytest.LogCaptureFixture, df: type[BaseDupeFilter] | None
    ) -> None:
        settings: dict[str, Any] = {
            "DUPEFILTER_DEBUG": True,
        }
        if df:
            settings["DUPEFILTER_CLASS"] = df
        crawler = get_crawler(SimpleSpider, settings_dict=settings)
        spider = SimpleSpider.from_crawler(crawler)
        dupefilter = _get_dupefilter(crawler=crawler)

        r1 = Request("http://scrapytest.org/index.html")
        r2 = Request(
            "http://scrapytest.org/index.html",
            headers={"Referer": "http://scrapytest.org/INDEX.html"},
        )

        with caplog.at_level(logging.DEBUG):
            dupefilter.log(r1, spider)
            dupefilter.log(r2, spider)

        assert crawler.stats
        assert crawler.stats.get_value("dupefilter/filtered") == 2
        assert (
            "scrapy.dupefilters",
            logging.DEBUG,
            "Filtered duplicate request: <GET http://scrapytest.org/index.html> (referer: None)",
        ) in caplog.record_tuples
        assert (
            "scrapy.dupefilters",
            logging.DEBUG,
            "Filtered duplicate request: <GET http://scrapytest.org/index.html>"
            " (referer: http://scrapytest.org/INDEX.html)",
        ) in caplog.record_tuples

        dupefilter.close("finished")

    def test_fingerprints_deprecation(self):
        dupefilter = _get_dupefilter()
        request = Request("http://scrapytest.org/index.html")
        dupefilter.request_seen(request)
        with pytest.warns(
            ScrapyDeprecationWarning,
            match=r"RFPDupeFilter\.fingerprints is deprecated\.",
        ):
            fingerprints = dupefilter.fingerprints
        assert fingerprints == {dupefilter.request_fingerprint(request)}
        dupefilter.close("finished")

    def test_request_fingerprint_override_deprecation(self):
        class LegacyDupeFilter(RFPDupeFilter):
            def request_fingerprint(self, request):
                return hashlib.sha1(to_bytes(request.url.lower())).hexdigest()

        with pytest.warns(
            ScrapyDeprecationWarning,
            match=r"Overriding RFPDupeFilter\.request_fingerprint\(\) is deprecated",
        ):
            dupefilter = _get_dupefilter(
                settings={"DUPEFILTER_CLASS": LegacyDupeFilter}
            )

        assert not dupefilter.request_seen(Request("http://scrapytest.org/index.html"))
        assert dupefilter.request_seen(Request("http://scrapytest.org/INDEX.html"))
        dupefilter.close("finished")


class TestDiskDupeFilter(DupeFilterTestMixin):
    dupefilter_class = DiskDupeFilter

    def test_temporary_database_removed(self) -> None:
        dupefilter = self._get_dupefilter()
        assert isinstance(dupefilter, DiskDupeFilter)
        assert dupefilter._tempdir
        tempdir = Path(dupefilter._tempdir)
        assert tempdir.exists()

        dupefilter.close("finished")
        assert not tempdir.exists()


class TestBaseDupeFilter:
    def test_log_deprecation(self):
        dupefilter = _get_dupefilter(
            settings={"DUPEFILTER_CLASS": BaseDupeFilter},
        )
        with pytest.warns(
            ScrapyDeprecationWarning,
            match=r"Calling BaseDupeFilter\.log\(\) is deprecated.",
        ):
            dupefilter.log(None, None)
