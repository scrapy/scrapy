# -*- coding: utf-8 -*-
import os
import shutil

from testfixtures import LogCapture
from twisted.internet import defer
from twisted.trial.unittest import TestCase
from w3lib.url import add_or_replace_parameter

from scrapy.crawler import CrawlerRunner
from scrapy import signals
from tests.mockserver import MockServer
from tests.spiders import SimpleSpider


class MediaDownloadSpider(SimpleSpider):
    name = 'mediadownload'

    def _process_url(self, url):
        return url

    def parse(self, response):
        self.logger.info(response.headers)
        self.logger.info(response.text)
        item = {
            'images': [],
            'image_urls': [
                self._process_url(response.urljoin(href))
                    for href in response.xpath('''
                        //table[thead/tr/th="Filename"]
                            /tbody//a/@href
                        ''').extract()],
        }
        yield item


class BrokenLinksMediaDownloadSpider(MediaDownloadSpider):
    name = 'brokenmedia'

    def _process_url(self, url):
        return url + '.foo'


class RedirectedMediaDownloadSpider(MediaDownloadSpider):
    name = 'redirectedmedia'

    def _process_url(self, url):
        return add_or_replace_parameter(
                    'http://localhost:8998/redirect-to',
                    'goto', url)


class MediaDownloadCrawlTestCase(TestCase):

    def setUp(self):
        self.mockserver = MockServer()
        self.mockserver.__enter__()

        # prepare a directory for storing files
        self.tmpmediastore = self.mktemp()
        os.mkdir(self.tmpmediastore)
        self.settings = {
            'ITEM_PIPELINES': {'scrapy.pipelines.images.ImagesPipeline': 1},
            'IMAGES_STORE': self.tmpmediastore,
        }
        self.runner = CrawlerRunner(self.settings)
        self.items = []
        # these are the checksums for images in test_site/files/images
        # - scrapy.png
        # - python-powered-h-50x65.png
        # - python-logo-master-v3-TM-flattened.png
        self.expected_checksums = set([
            'a7020c30837f971084834e603625af58',
            'acac52d42b63cf2c3b05832641f3a53c',
            '195672ac5888feb400fbf7b352553afe'])

    def tearDown(self):
        shutil.rmtree(self.tmpmediastore)
        self.items = []
        self.mockserver.__exit__(None, None, None)

    def _on_item_scraped(self, item):
        self.items.append(item)

    def _create_crawler(self, spider_class):
        crawler = self.runner.create_crawler(spider_class)
        crawler.signals.connect(self._on_item_scraped, signals.item_scraped)
        return crawler

    def _assert_files_downloaded(self, items, logs):
        self.assertEqual(len(items), 1)
        self.assertIn('images', items[0])

        # check that logs show the expected number of successful file downloads
        file_dl_success = 'File (downloaded): Downloaded file from'
        self.assertEqual(logs.count(file_dl_success), 3)

        # check that the images checksums are what we know they should be
        checksums = set(
            i['checksum']
                for item in items
                    for i in item['images'])
        self.assertEqual(checksums, self.expected_checksums)

        # check that the image files where actually written to the media store
        for item in items:
            for i in item['images']:
                self.assertTrue(
                    os.path.exists(
                        os.path.join(self.tmpmediastore, i['path'])))

    def _assert_files_download_failure(self, crawler, items, code, logs):

        # check that the item does NOT have the "images" field populated
        self.assertEqual(len(items), 1)
        self.assertIn('images', items[0])
        self.assertFalse(items[0]['images'])

        # check that there was 1 successful fetch and 3 other responses with non-200 code
        self.assertEqual(crawler.stats.get_value('downloader/request_method_count/GET'), 4)
        self.assertEqual(crawler.stats.get_value('downloader/response_count'), 4)
        self.assertEqual(crawler.stats.get_value('downloader/response_status_count/200'), 1)
        self.assertEqual(crawler.stats.get_value('downloader/response_status_count/%d' % code), 3)

        # check that logs do show the failure on the file downloads
        file_dl_failure = 'File (code: %d): Error downloading file from' % code
        self.assertEqual(logs.count(file_dl_failure), 3)

        # check that no files were written to the media store
        self.assertEqual(os.listdir(self.tmpmediastore), [])

    @defer.inlineCallbacks
    def test_download_media(self):
        crawler = self._create_crawler(MediaDownloadSpider)
        with LogCapture() as log:
            yield crawler.crawl("http://localhost:8998/files/images/")
        self._assert_files_downloaded(self.items, str(log))

    @defer.inlineCallbacks
    def test_download_media_wrong_urls(self):
        crawler = self._create_crawler(BrokenLinksMediaDownloadSpider)
        with LogCapture() as log:
            yield crawler.crawl("http://localhost:8998/files/images/")
        self._assert_files_download_failure(crawler, self.items, 404, str(log))

    @defer.inlineCallbacks
    def test_download_media_redirected_default_failure(self):
        crawler = self._create_crawler(RedirectedMediaDownloadSpider)
        with LogCapture() as log:
            yield crawler.crawl("http://localhost:8998/files/images/")
        self._assert_files_download_failure(crawler, self.items, 302, str(log))

    @defer.inlineCallbacks
    def test_download_media_redirected_allowed(self):
        settings = dict(self.settings)
        settings.update({'MEDIA_ALLOW_REDIRECTS': True})
        self.runner = CrawlerRunner(settings)

        crawler = self._create_crawler(RedirectedMediaDownloadSpider)
        with LogCapture() as log:
            yield crawler.crawl("http://localhost:8998/files/images/")
        self._assert_files_downloaded(self.items, str(log))
        self.assertEqual(crawler.stats.get_value('downloader/response_status_count/302'), 3)
