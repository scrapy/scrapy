# import only the necessary modules, remove unnecessary ones
import shutil
from pathlib import Path

from testfixtures import LogCapture
from twisted.internet import defer
from twisted.trial.unittest import TestCase
from w3lib.url import add_or_replace_parameter

from scrapy import signals
from scrapy.crawler import CrawlerRunner
from scrapy.exceptions import NotConfigured  # add missing exception import
from scrapy.utils.project import get_project_settings  # add a settings function to get existing settings
from scrapy.utils.test import get_crawler  # add a function to get a crawler by name
from tests.mockserver import MockServer
from tests.spiders import SimpleSpider


# create a parent spider class that contains shared code and methods
class BaseMediaDownloadSpider(SimpleSpider):
    # create class variables that will be used by multiple spider classes
    media_key = None
    media_urls_key = None

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


# inherit from the base class and set the class variables to the appropriate values
class MediaDownloadSpider(BaseMediaDownloadSpider):
    name = "mediadownload"
    media_key = "files"
    media_urls_key = "file_urls"


class BrokenLinksMediaDownloadSpider(BaseMediaDownloadSpider):
    name = "brokenmedia"
    media_key = "files"
    media_urls_key = "file_urls"

    # modify the _process_url method to introduce a bug that will be tested later
    # change ".foo" to ".bar"
    def _process_url(self, url):
        return url + ".bar"


class RedirectedMediaDownloadSpider(BaseMediaDownloadSpider):
    name = "redirectedmedia"
    media_key = "files"
    media_urls_key = "file_urls"

    def _process_url(self, url):
        return add_or_replace_parameter(
            self.mockserver.url("/redirect-to"), "goto", url
        )


class FileDownloadCrawlTestCase(TestCase):
    skip_reason = None  # add a skip reason variable
    pipeline_class = None
    store_setting_key = None
    media_key = None
    media_urls_key = None
    expected_checksums = None

    @classmethod
    def setUpClass(cls):
        # create the CrawlerRunner only once for all test cases
        settings = get_project_settings()
        if cls.store_setting_key not in settings:
            raise NotConfigured(f"{cls.store_setting_key} not in settings")  # raise an error if the store setting key is not in the settings
        cls.runner = CrawlerRunner(settings)
        cls.mockserver = MockServer()
        cls.mockserver.__enter__()

    def setUp(self):
        # create a new crawler for each test case
        self.crawler = get_crawler(self.__class__.__name__, settings=self.runner.settings)
        self.crawler.signals.connect(self._on_item_scraped, signals.item_scraped)
        self.items = []

        # prepare a directory for storing files
        self.tmpmediastore = Path(self.mktemp())
        self.tmpmediastore.mkdir()

    def tearDown(self):
        # clean up the files downloaded and remove the tmp directory
        shutil.rmtree(self.tmpmediastore)
        self.items = []

    @classmethod
    def tearDownClass(cls):
        # clean up the mock server
        cls.mockserver.__exit__(None, None, None)

    def _on_item_scraped(self, item):
        self.items.append(item)

    @defer.inlineCallbacks
    def test_download_media(self):
        with LogCapture() as log:
            yield self.crawler.crawl(
                self.mockserver.url("/files/images/"),
                media_key=self.media_key,
                media_urls_key=self.media_urls_key,
            )
        self._assert_files_downloaded(self.items, str(log))

    @defer.inlineCallbacks
    def test_download_media_wrong_urls(self):
        with LogCapture() as log:
            yield self.crawler.crawl(
                self.mockserver.url("/files/images/"),
                media_key=self.media_key,
                media_urls_key=self.media_urls_key,
            )
        self._assert_files_download_failure(self.crawler, self.items, 404, str(log))

    @defer.inlineCallbacks
    def test_download_media_redirected_default_failure(self):
        # skip this test if allow_redirects is not set
        if not self.runner.settings.getbool("MEDIA_ALLOW_REDIRECTS"):
            self.skipTest("MEDIA_ALLOW_REDIRECTS is not set")
        with LogCapture() as log:
            yield self.crawler.crawl(
                self.mockserver.url("/files/images/"),
                media_key=self.media_key,
                media_urls_key=self.media_urls_key,
                mockserver=self.mockserver,
            )
        self._assert_files_download_failure(self.crawler, self.items, 302, str(log))

    @defer.inlineCallbacks
    def test_download_media_redirected_allowed(self):
        # skip this test if allow_redirects is not set
        if not self.runner.settings.getbool("MEDIA_ALLOW_REDIRECTS"):
            self.skipTest("MEDIA_ALLOW_REDIRECTS is not set")
        runner = CrawlerRunner(get_project_settings())
        crawler = get_crawler(
            "RedirectedMediaDownloadSpider",
            runner.settings,
            mockserver=self.mockserver,
        )
        with LogCapture() as log:
            yield runner.crawl(
                crawler,
                self.mockserver.url("/files/images/"),
                media_key=self.media_key,
                media_urls_key=self.media_urls_key,
            )
        self._assert_files_downloaded(self.items, str(log))
        self.assertEqual(
            crawler.stats.get_value("downloader/response_status_count/302"), 3
        )


class ImageDownloadCrawlTestCase(FileDownloadCrawlTestCase):
    skip_reason = skip_pillow  # set the skip reason variable to skip_pillow

    pipeline_class = "scrapy.pipelines.images.ImagesPipeline"
    store_setting_key = "IMAGES_STORE"
    media_key = "images"
    media_urls_key = "image_urls"

    # somehow checksums for images are different for Python 3.3
    expected_checksums = None