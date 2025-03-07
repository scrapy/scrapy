import hashlib
import shutil
import sys
import tempfile
from pathlib import Path
from warnings import catch_warnings

from testfixtures import LogCapture

from scrapy.core.scheduler import Scheduler
from scrapy.dupefilters import BaseDupeFilter, RFPDupeFilter
from scrapy.exceptions import ScrapyDeprecationWarning
from scrapy.http import Request
from scrapy.utils.python import to_bytes
from scrapy.utils.test import get_crawler
from tests.spiders import SimpleSpider


def _get_dupefilter(*, crawler=None, settings=None, open=True):
    if crawler is None:
        crawler = get_crawler(settings_dict=settings)
    scheduler = Scheduler.from_crawler(crawler)
    dupefilter = scheduler.df
    if open:
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


class TestRFPDupeFilter:
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

    def test_filter(self):
        dupefilter = _get_dupefilter()
        r1 = Request("http://scrapytest.org/1")
        r2 = Request("http://scrapytest.org/2")
        r3 = Request("http://scrapytest.org/2")

        assert not dupefilter.request_seen(r1)
        assert dupefilter.request_seen(r1)

        assert not dupefilter.request_seen(r2)
        assert dupefilter.request_seen(r3)

        dupefilter.close("finished")

    def test_dupefilter_path(self):
        r1 = Request("http://scrapytest.org/1")
        r2 = Request("http://scrapytest.org/2")

        path = tempfile.mkdtemp()
        try:
            df = _get_dupefilter(settings={"JOBDIR": path}, open=False)
            try:
                df.open()
                assert not df.request_seen(r1)
                assert df.request_seen(r1)
            finally:
                df.close("finished")

            df2 = _get_dupefilter(settings={"JOBDIR": path}, open=False)
            assert df != df2
            try:
                df2.open()
                assert df2.request_seen(r1)
                assert not df2.request_seen(r2)
                assert df2.request_seen(r2)
            finally:
                df2.close("finished")
        finally:
            shutil.rmtree(path)

    def test_request_fingerprint(self):
        """Test if customization of request_fingerprint method will change
        output of request_seen.

        """
        dupefilter = _get_dupefilter()
        r1 = Request("http://scrapytest.org/index.html")
        r2 = Request("http://scrapytest.org/INDEX.html")

        assert not dupefilter.request_seen(r1)
        assert not dupefilter.request_seen(r2)

        dupefilter.close("finished")

        class RequestFingerprinter:
            def fingerprint(self, request):
                fp = hashlib.sha1()
                fp.update(to_bytes(request.url.lower()))
                return fp.digest()

        settings = {"REQUEST_FINGERPRINTER_CLASS": RequestFingerprinter}
        case_insensitive_dupefilter = _get_dupefilter(settings=settings)

        assert not case_insensitive_dupefilter.request_seen(r1)
        assert case_insensitive_dupefilter.request_seen(r2)

        case_insensitive_dupefilter.close("finished")

    def test_seenreq_newlines(self):
        r"""Checks against adding duplicate \r to
        line endings on Windows platforms."""

        r1 = Request("http://scrapytest.org/1")

        path = tempfile.mkdtemp()
        crawler = get_crawler(settings_dict={"JOBDIR": path})
        try:
            scheduler = Scheduler.from_crawler(crawler)
            df = scheduler.df
            df.open()
            df.request_seen(r1)
            df.close("finished")

            with Path(path, "requests.seen").open("rb") as seen_file:
                line = next(seen_file).decode()
                assert not line.endswith("\r\r\n")
                if sys.platform == "win32":
                    assert line.endswith("\r\n")
                else:
                    assert line.endswith("\n")

        finally:
            shutil.rmtree(path)

    def test_log(self):
        with LogCapture() as log:
            settings = {
                "DUPEFILTER_DEBUG": False,
                "DUPEFILTER_CLASS": FromCrawlerRFPDupeFilter,
            }
            crawler = get_crawler(SimpleSpider, settings_dict=settings)
            spider = SimpleSpider.from_crawler(crawler)
            dupefilter = _get_dupefilter(crawler=crawler)

            r1 = Request("http://scrapytest.org/index.html")
            r2 = Request("http://scrapytest.org/index.html")

            dupefilter.log(r1, spider)
            dupefilter.log(r2, spider)

            assert crawler.stats.get_value("dupefilter/filtered") == 2
            log.check_present(
                (
                    "scrapy.dupefilters",
                    "DEBUG",
                    "Filtered duplicate request: <GET http://scrapytest.org/index.html> - no more"
                    " duplicates will be shown (see DUPEFILTER_DEBUG to show all duplicates)",
                )
            )

            dupefilter.close("finished")

    def test_log_debug(self):
        with LogCapture() as log:
            settings = {
                "DUPEFILTER_DEBUG": True,
                "DUPEFILTER_CLASS": FromCrawlerRFPDupeFilter,
            }
            crawler = get_crawler(SimpleSpider, settings_dict=settings)
            spider = SimpleSpider.from_crawler(crawler)
            dupefilter = _get_dupefilter(crawler=crawler)

            r1 = Request("http://scrapytest.org/index.html")
            r2 = Request(
                "http://scrapytest.org/index.html",
                headers={"Referer": "http://scrapytest.org/INDEX.html"},
            )

            dupefilter.log(r1, spider)
            dupefilter.log(r2, spider)

            assert crawler.stats.get_value("dupefilter/filtered") == 2
            log.check_present(
                (
                    "scrapy.dupefilters",
                    "DEBUG",
                    "Filtered duplicate request: <GET http://scrapytest.org/index.html> (referer: None)",
                )
            )
            log.check_present(
                (
                    "scrapy.dupefilters",
                    "DEBUG",
                    "Filtered duplicate request: <GET http://scrapytest.org/index.html>"
                    " (referer: http://scrapytest.org/INDEX.html)",
                )
            )

            dupefilter.close("finished")

    def test_log_debug_default_dupefilter(self):
        with LogCapture() as log:
            settings = {
                "DUPEFILTER_DEBUG": True,
            }
            crawler = get_crawler(SimpleSpider, settings_dict=settings)
            spider = SimpleSpider.from_crawler(crawler)
            dupefilter = _get_dupefilter(crawler=crawler)

            r1 = Request("http://scrapytest.org/index.html")
            r2 = Request(
                "http://scrapytest.org/index.html",
                headers={"Referer": "http://scrapytest.org/INDEX.html"},
            )

            dupefilter.log(r1, spider)
            dupefilter.log(r2, spider)

            assert crawler.stats.get_value("dupefilter/filtered") == 2
            log.check_present(
                (
                    "scrapy.dupefilters",
                    "DEBUG",
                    "Filtered duplicate request: <GET http://scrapytest.org/index.html> (referer: None)",
                )
            )
            log.check_present(
                (
                    "scrapy.dupefilters",
                    "DEBUG",
                    "Filtered duplicate request: <GET http://scrapytest.org/index.html>"
                    " (referer: http://scrapytest.org/INDEX.html)",
                )
            )

            dupefilter.close("finished")


class TestBaseDupeFilter:
    def test_log_deprecation(self):
        dupefilter = _get_dupefilter(
            settings={"DUPEFILTER_CLASS": BaseDupeFilter},
        )
        with catch_warnings(record=True) as warning_list:
            dupefilter.log(None, None)
        assert len(warning_list) == 1
        assert (
            str(warning_list[0].message)
            == "Calling BaseDupeFilter.log() is deprecated."
        )
        assert warning_list[0].category == ScrapyDeprecationWarning
