import hashlib
import shutil
import sys
import tempfile
from pathlib import Path

from testfixtures import LogCapture
from twisted.internet.defer import inlineCallbacks
from twisted.trial import unittest

from scrapy.core.scheduler import Scheduler
from scrapy.dupefilters import RFPDupeFilter
from scrapy.http import Request
from scrapy.utils.python import to_bytes
from scrapy.utils.test import get_crawler
from tests.spiders import NoRequestsSpider


@inlineCallbacks
def _get_dupefilter(*, crawler=None, settings=None, open=True):
    if crawler is None:
        crawler = get_crawler(NoRequestsSpider, settings_dict=settings)
        yield crawler.crawl()
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


class FromSettingsRFPDupeFilter(RFPDupeFilter):
    @classmethod
    def from_settings(cls, settings, *, fingerprinter=None):
        df = super().from_settings(settings, fingerprinter=fingerprinter)
        df.method = "from_settings"
        return df


class DirectDupeFilter:
    method = "n/a"

    def open(self):
        pass


class RFPDupeFilterTest(unittest.TestCase):
    @inlineCallbacks
    def test_df_from_crawler_scheduler(self):
        settings = {
            "DUPEFILTER_DEBUG": True,
            "DUPEFILTER_CLASS": FromCrawlerRFPDupeFilter,
            "REQUEST_FINGERPRINTER_IMPLEMENTATION": "2.7",
        }
        crawler = get_crawler(NoRequestsSpider, settings_dict=settings)
        yield crawler.crawl()
        scheduler = Scheduler.from_crawler(crawler)
        self.assertTrue(scheduler.df.debug)
        self.assertEqual(scheduler.df.method, "from_crawler")

    @inlineCallbacks
    def test_df_from_settings_scheduler(self):
        settings = {
            "DUPEFILTER_DEBUG": True,
            "DUPEFILTER_CLASS": FromSettingsRFPDupeFilter,
            "REQUEST_FINGERPRINTER_IMPLEMENTATION": "2.7",
        }
        crawler = get_crawler(NoRequestsSpider, settings_dict=settings)
        yield crawler.crawl()
        scheduler = Scheduler.from_crawler(crawler)
        self.assertTrue(scheduler.df.debug)
        self.assertEqual(scheduler.df.method, "from_settings")

    @inlineCallbacks
    def test_df_direct_scheduler(self):
        settings = {
            "DUPEFILTER_CLASS": DirectDupeFilter,
            "REQUEST_FINGERPRINTER_IMPLEMENTATION": "2.7",
        }
        crawler = get_crawler(NoRequestsSpider, settings_dict=settings)
        yield crawler.crawl()
        scheduler = Scheduler.from_crawler(crawler)
        self.assertEqual(scheduler.df.method, "n/a")

    @inlineCallbacks
    def test_filter(self):
        dupefilter = yield _get_dupefilter()
        r1 = Request("http://scrapytest.org/1")
        r2 = Request("http://scrapytest.org/2")
        r3 = Request("http://scrapytest.org/2")

        assert not dupefilter.request_seen(r1)
        assert dupefilter.request_seen(r1)

        assert not dupefilter.request_seen(r2)
        assert dupefilter.request_seen(r3)

        dupefilter.close("finished")

    @inlineCallbacks
    def test_dupefilter_path(self):
        r1 = Request("http://scrapytest.org/1")
        r2 = Request("http://scrapytest.org/2")

        path = tempfile.mkdtemp()
        try:
            df = yield _get_dupefilter(settings={"JOBDIR": path}, open=False)
            try:
                df.open()
                assert not df.request_seen(r1)
                assert df.request_seen(r1)
            finally:
                df.close("finished")

            df2 = yield _get_dupefilter(settings={"JOBDIR": path}, open=False)
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

    @inlineCallbacks
    def test_request_fingerprint(self):
        """Test if customization of request_fingerprint method will change
        output of request_seen.

        """
        dupefilter = yield _get_dupefilter()
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
        case_insensitive_dupefilter = yield _get_dupefilter(settings=settings)

        assert not case_insensitive_dupefilter.request_seen(r1)
        assert case_insensitive_dupefilter.request_seen(r2)

        case_insensitive_dupefilter.close("finished")

    @inlineCallbacks
    def test_seenreq_newlines(self):
        """Checks against adding duplicate \r to
        line endings on Windows platforms."""

        r1 = Request("http://scrapytest.org/1")

        path = tempfile.mkdtemp()
        crawler = get_crawler(NoRequestsSpider, settings_dict={"JOBDIR": path})
        yield crawler.crawl()
        try:
            scheduler = Scheduler.from_crawler(crawler)
            df = scheduler.df
            df.open()
            df.request_seen(r1)
            df.close("finished")

            with Path(path, "requests.seen").open("rb") as seen_file:
                try:
                    line = next(seen_file).decode()
                except StopIteration:
                    return
                assert not line.endswith("\r\r\n")
                if sys.platform == "win32":
                    assert line.endswith("\r\n")
                else:
                    assert line.endswith("\n")

        finally:
            shutil.rmtree(path)

    @inlineCallbacks
    def test_log(self):
        with LogCapture() as log:
            settings = {
                "DUPEFILTER_DEBUG": False,
                "DUPEFILTER_CLASS": FromCrawlerRFPDupeFilter,
                "REQUEST_FINGERPRINTER_IMPLEMENTATION": "2.7",
            }
            crawler = get_crawler(NoRequestsSpider, settings_dict=settings)
            yield crawler.crawl()
            spider = crawler.spider
            dupefilter = yield _get_dupefilter(crawler=crawler)

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

    @inlineCallbacks
    def test_log_debug(self):
        with LogCapture() as log:
            settings = {
                "DUPEFILTER_DEBUG": True,
                "DUPEFILTER_CLASS": FromCrawlerRFPDupeFilter,
                "REQUEST_FINGERPRINTER_IMPLEMENTATION": "2.7",
            }
            crawler = get_crawler(NoRequestsSpider, settings_dict=settings)
            yield crawler.crawl()
            spider = crawler.spider
            dupefilter = yield _get_dupefilter(crawler=crawler)

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

    @inlineCallbacks
    def test_log_debug_default_dupefilter(self):
        with LogCapture() as log:
            settings = {
                "DUPEFILTER_DEBUG": True,
                "REQUEST_FINGERPRINTER_IMPLEMENTATION": "2.7",
            }
            crawler = get_crawler(NoRequestsSpider, settings_dict=settings)
            yield crawler.crawl()
            spider = crawler.spider
            dupefilter = yield _get_dupefilter(crawler=crawler)

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
