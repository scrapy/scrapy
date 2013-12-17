import mock
import os
import time
from tempfile import mkdtemp
from shutil import rmtree

from twisted.trial import unittest
from twisted.internet import defer

from scrapy.contrib.pipeline.files import FilesPipeline, FSFilesStore
from scrapy.item import Item, Field
from scrapy.http import Request, Response
from scrapy.settings import Settings


def _mocked_download_func(request, info):
    response = request.meta.get('response')
    return response() if callable(response) else response


class FilesPipelineTestCase(unittest.TestCase):

    def setUp(self):
        self.tempdir = mkdtemp()
        self.pipeline = FilesPipeline.from_settings(Settings({'FILES_STORE': self.tempdir}))
        self.pipeline.download_func = _mocked_download_func
        self.pipeline.open_spider(None)

    def tearDown(self):
        rmtree(self.tempdir)

    def test_file_path(self):
        image_path = self.pipeline.file_path
        self.assertEqual(image_path(Request("https://dev.mydeco.com/mydeco.pdf")),
                         'full/c9b564df929f4bc635bdd19fde4f3d4847c757c5.pdf')
        self.assertEqual(image_path(Request("http://www.maddiebrown.co.uk///catalogue-items//image_54642_12175_95307.txt")),
                         'full/4ce274dd83db0368bafd7e406f382ae088e39219.txt')
        self.assertEqual(image_path(Request("https://dev.mydeco.com/two/dirs/with%20spaces%2Bsigns.doc")),
                         'full/94ccc495a17b9ac5d40e3eabf3afcb8c2c9b9e1a.doc')
        self.assertEqual(image_path(Request("http://www.dfsonline.co.uk/get_prod_image.php?img=status_0907_mdm.jpg")),
                         'full/4507be485f38b0da8a0be9eb2e1dfab8a19223f2.jpg')
        self.assertEqual(image_path(Request("http://www.dorma.co.uk/images/product_details/2532/")),
                         'full/97ee6f8a46cbbb418ea91502fd24176865cf39b2')
        self.assertEqual(image_path(Request("http://www.dorma.co.uk/images/product_details/2532")),
                         'full/244e0dd7d96a3b7b01f54eded250c9e272577aa1')

    def test_fs_store(self):
        assert isinstance(self.pipeline.store, FSFilesStore)
        self.assertEqual(self.pipeline.store.basedir, self.tempdir)

        key = 'some/image/key.jpg'
        path = os.path.join(self.tempdir, 'some', 'image', 'key.jpg')
        self.assertEqual(self.pipeline.store._get_filesystem_path(key), path)

    @defer.inlineCallbacks
    def test_file_not_expired(self):
        item_url = "http://example.com/file.pdf"
        item = _create_item_with_files(item_url)
        patchers = [
            mock.patch.object(FilesPipeline, 'inc_stats', return_value=True),
            mock.patch.object(FSFilesStore, 'stat_file', return_value={
                'checksum': 'abc', 'last_modified': time.time()}),
            mock.patch.object(FilesPipeline, 'get_media_requests',
                              return_value=[_prepare_request_object(item_url)])
        ]
        for p in patchers:
            p.start()

        result = yield self.pipeline.process_item(item, None)
        self.assertEqual(result['files'][0]['checksum'], 'abc')

        for p in patchers:
            p.stop()

    @defer.inlineCallbacks
    def test_file_expired(self):
        item_url = "http://example.com/file2.pdf"
        item = _create_item_with_files(item_url)
        patchers = [
            mock.patch.object(FSFilesStore, 'stat_file', return_value={
                'checksum': 'abc',
                'last_modified': time.time() - (FilesPipeline.EXPIRES * 60 * 60 * 24 * 2)}),
            mock.patch.object(FilesPipeline, 'get_media_requests',
                              return_value=[_prepare_request_object(item_url)]),
            mock.patch.object(FilesPipeline, 'inc_stats', return_value=True)
        ]
        for p in patchers:
            p.start()

        result = yield self.pipeline.process_item(item, None)
        self.assertNotEqual(result['files'][0]['checksum'], 'abc')

        for p in patchers:
            p.stop()


class FilesPipelineTestCaseFields(unittest.TestCase):

    def test_item_fields_default(self):
        from scrapy.contrib.pipeline.files import FilesPipeline
        class TestItem(Item):
            name = Field()
            file_urls = Field()
            files = Field()
        url = 'http://www.example.com/files/1.txt'
        item = TestItem({'name': 'item1', 'file_urls': [url]})
        pipeline = FilesPipeline.from_settings(Settings({'FILES_STORE': 's3://example/files/'}))
        requests = list(pipeline.get_media_requests(item, None))
        self.assertEqual(requests[0].url, url)
        results = [(True, {'url': url})]
        pipeline.item_completed(results, item, None)
        self.assertEqual(item['files'], [results[0][1]])

    def test_item_fields_override_settings(self):
        from scrapy.contrib.pipeline.files import FilesPipeline
        class TestItem(Item):
            name = Field()
            files = Field()
            stored_file = Field()
        url = 'http://www.example.com/files/1.txt'
        item = TestItem({'name': 'item1', 'files': [url]})
        pipeline = FilesPipeline.from_settings(Settings({'FILES_STORE': 's3://example/files/',
                'FILES_URLS_FIELD': 'files', 'FILES_RESULT_FIELD': 'stored_file'}))
        requests = list(pipeline.get_media_requests(item, None))
        self.assertEqual(requests[0].url, url)
        results = [(True, {'url': url})]
        pipeline.item_completed(results, item, None)
        self.assertEqual(item['stored_file'], [results[0][1]])


class ItemWithFiles(Item):
    file_urls = Field()
    files = Field()


def _create_item_with_files(*files):
    item = ItemWithFiles()
    item['file_urls'] = files
    return item


def _prepare_request_object(item_url):
    return Request(
        item_url,
        meta={'response': Response(item_url, status=200, body='data')})

if __name__ == "__main__":
    unittest.main()
