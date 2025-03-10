from __future__ import annotations

import shutil
from pathlib import Path
from tempfile import mkdtemp
from typing import TYPE_CHECKING, Any

from testfixtures import LogCapture
from twisted.internet import defer
from twisted.trial.unittest import TestCase
from w3lib.url import add_or_replace_parameter

from scrapy import Spider, signals
from scrapy.utils.misc import load_object
from scrapy.utils.test import get_crawler
from tests.mockserver import MockServer
from tests.spiders import SimpleSpider

if TYPE_CHECKING:
    from scrapy.crawler import Crawler


class MediaDownloadSpider(SimpleSpider):
    name = "mediadownload"

    def _process_url(self, url):
        return url

    def parse(self, response):
        self.logger.info(response.headers)
        self.logger.info(response.text)
        item = {
            self.media_key: [],
            self.media_urls_key: [
                self._process_url(response.urljoin(href))
                for href in response.xpath(
                    '//table[thead/tr/th="Filename"]/tbody//a/@href'
                ).getall()
            ],
        }
        yield item


class BrokenLinksMediaDownloadSpider(MediaDownloadSpider):
    name = "brokenmedia"

    def _process_url(self, url):
        return url + ".foo"


class RedirectedMediaDownloadSpider(MediaDownloadSpider):
    name = "redirectedmedia"

    def _process_url(self, url):
        return add_or_replace_parameter(
            self.mockserver.url("/redirect-to"), "goto", url
        )


class TestFileDownloadCrawl(TestCase):
    pipeline_class = "scrapy.pipelines.files.FilesPipeline"
    store_setting_key = "FILES_STORE"
    media_key = "files"
    media_urls_key = "file_urls"
    expected_checksums: set[str] | None = {
        "5547178b89448faf0015a13f904c936e",
        "c2281c83670e31d8aaab7cb642b824db",
        "ed3f6538dc15d4d9179dae57319edc5f",
    }

    @classmethod
    def setUpClass(cls):
        cls.mockserver = MockServer()
        cls.mockserver.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.mockserver.__exit__(None, None, None)

    def setUp(self):
        # prepare a directory for storing files
        self.tmpmediastore = Path(mkdtemp())
        self.settings = {
            "ITEM_PIPELINES": {self.pipeline_class: 1},
            self.store_setting_key: str(self.tmpmediastore),
        }
        self.items = []

    def tearDown(self):
        shutil.rmtree(self.tmpmediastore)
        self.items = []

    def _on_item_scraped(self, item):
        self.items.append(item)

    def _create_crawler(
        self, spider_class: type[Spider], settings: dict[str, Any] | None = None
    ) -> Crawler:
        if settings is None:
            settings = self.settings
        crawler = get_crawler(spider_class, settings)
        crawler.signals.connect(self._on_item_scraped, signals.item_scraped)
        return crawler

    def _assert_files_downloaded(self, items, logs):
        assert len(items) == 1
        assert self.media_key in items[0]

        # check that logs show the expected number of successful file downloads
        file_dl_success = "File (downloaded): Downloaded file from"
        assert logs.count(file_dl_success) == 3

        # check that the images/files status is `downloaded`
        for item in items:
            for i in item[self.media_key]:
                assert i["status"] == "downloaded"

        # check that the images/files checksums are what we know they should be
        if self.expected_checksums is not None:
            checksums = {i["checksum"] for item in items for i in item[self.media_key]}
            assert checksums == self.expected_checksums

        # check that the image files where actually written to the media store
        for item in items:
            for i in item[self.media_key]:
                assert (self.tmpmediastore / i["path"]).exists()

    def _assert_files_download_failure(self, crawler, items, code, logs):
        # check that the item does NOT have the "images/files" field populated
        assert len(items) == 1
        assert self.media_key in items[0]
        assert not items[0][self.media_key]

        # check that there was 1 successful fetch and 3 other responses with non-200 code
        assert crawler.stats.get_value("downloader/request_method_count/GET") == 4
        assert crawler.stats.get_value("downloader/response_count") == 4
        assert crawler.stats.get_value("downloader/response_status_count/200") == 1
        assert crawler.stats.get_value(f"downloader/response_status_count/{code}") == 3

        # check that logs do show the failure on the file downloads
        file_dl_failure = f"File (code: {code}): Error downloading file from"
        assert logs.count(file_dl_failure) == 3

        # check that no files were written to the media store
        assert not list(self.tmpmediastore.iterdir())

    @defer.inlineCallbacks
    def test_download_media(self):
        crawler = self._create_crawler(MediaDownloadSpider)
        with LogCapture() as log:
            yield crawler.crawl(
                self.mockserver.url("/files/images/"),
                media_key=self.media_key,
                media_urls_key=self.media_urls_key,
            )
        self._assert_files_downloaded(self.items, str(log))

    @defer.inlineCallbacks
    def test_download_media_wrong_urls(self):
        crawler = self._create_crawler(BrokenLinksMediaDownloadSpider)
        with LogCapture() as log:
            yield crawler.crawl(
                self.mockserver.url("/files/images/"),
                media_key=self.media_key,
                media_urls_key=self.media_urls_key,
            )
        self._assert_files_download_failure(crawler, self.items, 404, str(log))

    @defer.inlineCallbacks
    def test_download_media_redirected_default_failure(self):
        crawler = self._create_crawler(RedirectedMediaDownloadSpider)
        with LogCapture() as log:
            yield crawler.crawl(
                self.mockserver.url("/files/images/"),
                media_key=self.media_key,
                media_urls_key=self.media_urls_key,
                mockserver=self.mockserver,
            )
        self._assert_files_download_failure(crawler, self.items, 302, str(log))

    @defer.inlineCallbacks
    def test_download_media_redirected_allowed(self):
        settings = {
            **self.settings,
            "MEDIA_ALLOW_REDIRECTS": True,
        }
        crawler = self._create_crawler(RedirectedMediaDownloadSpider, settings)
        with LogCapture() as log:
            yield crawler.crawl(
                self.mockserver.url("/files/images/"),
                media_key=self.media_key,
                media_urls_key=self.media_urls_key,
                mockserver=self.mockserver,
            )
        self._assert_files_downloaded(self.items, str(log))
        assert crawler.stats.get_value("downloader/response_status_count/302") == 3

    @defer.inlineCallbacks
    def test_download_media_file_path_error(self):
        cls = load_object(self.pipeline_class)

        class ExceptionRaisingMediaPipeline(cls):
            def file_path(self, request, response=None, info=None, *, item=None):
                return 1 / 0

        settings = {
            **self.settings,
            "ITEM_PIPELINES": {ExceptionRaisingMediaPipeline: 1},
        }
        crawler = self._create_crawler(MediaDownloadSpider, settings)
        with LogCapture() as log:
            yield crawler.crawl(
                self.mockserver.url("/files/images/"),
                media_key=self.media_key,
                media_urls_key=self.media_urls_key,
                mockserver=self.mockserver,
            )
        assert "ZeroDivisionError" in str(log)


skip_pillow: str | None
try:
    from PIL import Image  # noqa: F401
except ImportError:
    skip_pillow = "Missing Python Imaging Library, install https://pypi.org/pypi/Pillow"
else:
    skip_pillow = None


class ImageDownloadCrawlTestCase(TestFileDownloadCrawl):
    skip = skip_pillow

    pipeline_class = "scrapy.pipelines.images.ImagesPipeline"
    store_setting_key = "IMAGES_STORE"
    media_key = "images"
    media_urls_key = "image_urls"

    # somehow checksums for images are different for Python 3.3
    expected_checksums = None
