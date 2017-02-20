from __future__ import absolute_import
import os
import csv
import json
from io import BytesIO
import tempfile
import shutil
from six.moves.urllib.parse import urlparse

from zope.interface.verify import verifyObject
from twisted.trial import unittest
from twisted.internet import defer
from scrapy.crawler import CrawlerRunner
from scrapy.settings import Settings
from tests.mockserver import MockServer
from w3lib.url import path_to_file_uri

import scrapy
from scrapy.extensions.feedexport import (
    IFeedStorage, FileFeedStorage, FTPFeedStorage,
    S3FeedStorage, StdoutFeedStorage,
    BlockingFeedStorage)
from scrapy.utils.test import assert_aws_environ, get_s3_content_and_delete, get_crawler
from scrapy.utils.python import to_native_str


class FileFeedStorageTest(unittest.TestCase):

    def test_store_file_uri(self):
        path = os.path.abspath(self.mktemp())
        uri = path_to_file_uri(path)
        return self._assert_stores(FileFeedStorage(uri), path)

    def test_store_file_uri_makedirs(self):
        path = os.path.abspath(self.mktemp())
        path = os.path.join(path, 'more', 'paths', 'file.txt')
        uri = path_to_file_uri(path)
        return self._assert_stores(FileFeedStorage(uri), path)

    def test_store_direct_path(self):
        path = os.path.abspath(self.mktemp())
        return self._assert_stores(FileFeedStorage(path), path)

    def test_store_direct_path_relative(self):
        path = self.mktemp()
        return self._assert_stores(FileFeedStorage(path), path)

    def test_interface(self):
        path = self.mktemp()
        st = FileFeedStorage(path)
        verifyObject(IFeedStorage, st)

    @defer.inlineCallbacks
    def _assert_stores(self, storage, path):
        spider = scrapy.Spider("default")
        file = storage.open(spider)
        file.write(b"content")
        yield storage.store(file)
        self.assertTrue(os.path.exists(path))
        try:
            with open(path, 'rb') as fp:
                self.assertEqual(fp.read(), b"content")
        finally:
            os.unlink(path)


class FTPFeedStorageTest(unittest.TestCase):

    def test_store(self):
        uri = os.environ.get('FEEDTEST_FTP_URI')
        path = os.environ.get('FEEDTEST_FTP_PATH')
        if not (uri and path):
            raise unittest.SkipTest("No FTP server available for testing")
        st = FTPFeedStorage(uri)
        verifyObject(IFeedStorage, st)
        return self._assert_stores(st, path)

    @defer.inlineCallbacks
    def _assert_stores(self, storage, path):
        spider = scrapy.Spider("default")
        file = storage.open(spider)
        file.write(b"content")
        yield storage.store(file)
        self.assertTrue(os.path.exists(path))
        try:
            with open(path, 'rb') as fp:
                self.assertEqual(fp.read(), b"content")
            # again, to check s3 objects are overwritten
            yield storage.store(BytesIO(b"new content"))
            with open(path, 'rb') as fp:
                self.assertEqual(fp.read(), b"new content")
        finally:
            os.unlink(path)


class BlockingFeedStorageTest(unittest.TestCase):

    def get_test_spider(self, settings=None):
        class TestSpider(scrapy.Spider):
            name = 'test_spider'
        crawler = get_crawler(settings_dict=settings)
        spider = TestSpider.from_crawler(crawler)
        return spider

    def test_default_temp_dir(self):
        b = BlockingFeedStorage()

        tmp = b.open(self.get_test_spider())
        tmp_path = os.path.dirname(tmp.name)
        self.assertEqual(tmp_path, tempfile.gettempdir())

    def test_temp_file(self):
        b = BlockingFeedStorage()

        tests_path = os.path.dirname(os.path.abspath(__file__))
        spider = self.get_test_spider({'FEED_TEMPDIR': tests_path})
        tmp = b.open(spider)
        tmp_path = os.path.dirname(tmp.name)
        self.assertEqual(tmp_path, tests_path)

    def test_invalid_folder(self):
        b = BlockingFeedStorage()

        tests_path = os.path.dirname(os.path.abspath(__file__))
        invalid_path = os.path.join(tests_path, 'invalid_path')
        spider = self.get_test_spider({'FEED_TEMPDIR': invalid_path})

        self.assertRaises(OSError, b.open, spider=spider)


class S3FeedStorageTest(unittest.TestCase):

    @defer.inlineCallbacks
    def test_store(self):
        assert_aws_environ()
        uri = os.environ.get('S3_TEST_FILE_URI')
        if not uri:
            raise unittest.SkipTest("No S3 URI available for testing")
        storage = S3FeedStorage(uri)
        verifyObject(IFeedStorage, storage)
        file = storage.open(scrapy.Spider("default"))
        expected_content = b"content: \xe2\x98\x83"
        file.write(expected_content)
        yield storage.store(file)
        u = urlparse(uri)
        content = get_s3_content_and_delete(u.hostname, u.path[1:])
        self.assertEqual(content, expected_content)


class StdoutFeedStorageTest(unittest.TestCase):

    @defer.inlineCallbacks
    def test_store(self):
        out = BytesIO()
        storage = StdoutFeedStorage('stdout:', _stdout=out)
        file = storage.open(scrapy.Spider("default"))
        file.write(b"content")
        yield storage.store(file)
        self.assertEqual(out.getvalue(), b"content")


class FeedExportTest(unittest.TestCase):

    class MyItem(scrapy.Item):
        foo = scrapy.Field()
        egg = scrapy.Field()
        baz = scrapy.Field()

    @defer.inlineCallbacks
    def run_and_export(self, spider_cls, settings=None):
        """ Run spider with specified settings; return exported data. """
        tmpdir = tempfile.mkdtemp()
        res_name = tmpdir + '/res'
        defaults = {
            'FEED_URI': 'file://' + res_name,
            'FEED_FORMAT': 'csv',
        }
        defaults.update(settings or {})
        try:
            with MockServer() as s:
                runner = CrawlerRunner(Settings(defaults))
                yield runner.crawl(spider_cls)

            with open(res_name, 'rb') as f:
                defer.returnValue(f.read())

        finally:
            shutil.rmtree(tmpdir)

    @defer.inlineCallbacks
    def exported_data(self, items, settings):
        """
        Return exported data which a spider yielding ``items`` would return.
        """
        class TestSpider(scrapy.Spider):
            name = 'testspider'
            start_urls = ['http://localhost:8998/']

            def parse(self, response):
                for item in items:
                    yield item

        data = yield self.run_and_export(TestSpider, settings)
        defer.returnValue(data)

    @defer.inlineCallbacks
    def exported_no_data(self, settings):
        """
        Return exported data which a spider yielding no ``items`` would return.
        """
        class TestSpider(scrapy.Spider):
            name = 'testspider'
            start_urls = ['http://localhost:8998/']

            def parse(self, response):
                pass

        data = yield self.run_and_export(TestSpider, settings)
        defer.returnValue(data)

    @defer.inlineCallbacks
    def assertExportedCsv(self, items, header, rows, settings=None, ordered=True):
        settings = settings or {}
        settings.update({'FEED_FORMAT': 'csv'})
        data = yield self.exported_data(items, settings)

        reader = csv.DictReader(to_native_str(data).splitlines())
        got_rows = list(reader)
        if ordered:
            self.assertEqual(reader.fieldnames, header)
        else:
            self.assertEqual(set(reader.fieldnames), set(header))

        self.assertEqual(rows, got_rows)

    @defer.inlineCallbacks
    def assertExportedJsonLines(self, items, rows, settings=None):
        settings = settings or {}
        settings.update({'FEED_FORMAT': 'jl'})
        data = yield self.exported_data(items, settings)
        parsed = [json.loads(to_native_str(line)) for line in data.splitlines()]
        rows = [{k: v for k, v in row.items() if v} for row in rows]
        self.assertEqual(rows, parsed)

    @defer.inlineCallbacks
    def assertExportedXml(self, items, rows, settings=None):
        settings = settings or {}
        settings.update({'FEED_FORMAT': 'xml'})
        data = yield self.exported_data(items, settings)
        rows = [{k: v for k, v in row.items() if v} for row in rows]
        import lxml.etree
        root = lxml.etree.fromstring(data)
        got_rows = [{e.tag: e.text for e in it} for it in root.findall('item')]
        self.assertEqual(rows, got_rows)

    def _load_until_eof(self, data, load_func):
        bytes_output = BytesIO(data)
        result = []
        while True:
            try:
                result.append(load_func(bytes_output))
            except EOFError:
                break
        return result

    @defer.inlineCallbacks
    def assertExportedPickle(self, items, rows, settings=None):
        settings = settings or {}
        settings.update({'FEED_FORMAT': 'pickle'})
        data = yield self.exported_data(items, settings)
        expected = [{k: v for k, v in row.items() if v} for row in rows]
        import pickle
        result = self._load_until_eof(data, load_func=pickle.load)
        self.assertEqual(expected, result)

    @defer.inlineCallbacks
    def assertExportedMarshal(self, items, rows, settings=None):
        settings = settings or {}
        settings.update({'FEED_FORMAT': 'marshal'})
        data = yield self.exported_data(items, settings)
        expected = [{k: v for k, v in row.items() if v} for row in rows]
        import marshal
        result = self._load_until_eof(data, load_func=marshal.load)
        self.assertEqual(expected, result)

    @defer.inlineCallbacks
    def assertExported(self, items, header, rows, settings=None, ordered=True):
        yield self.assertExportedCsv(items, header, rows, settings, ordered)
        yield self.assertExportedJsonLines(items, rows, settings)
        yield self.assertExportedXml(items, rows, settings)
        yield self.assertExportedPickle(items, rows, settings)

    @defer.inlineCallbacks
    def test_export_items(self):
        # feed exporters use field names from Item
        items = [
            self.MyItem({'foo': 'bar1', 'egg': 'spam1'}),
            self.MyItem({'foo': 'bar2', 'egg': 'spam2', 'baz': 'quux2'}),
        ]
        rows = [
            {'egg': 'spam1', 'foo': 'bar1', 'baz': ''},
            {'egg': 'spam2', 'foo': 'bar2', 'baz': 'quux2'}
        ]
        header = self.MyItem.fields.keys()
        yield self.assertExported(items, header, rows, ordered=False)

    @defer.inlineCallbacks
    def test_export_no_items_not_store_empty(self):
        formats = ('json',
                   'jsonlines',
                   'xml',
                   'csv',)

        for fmt in formats:
            settings = {'FEED_FORMAT': fmt}
            data = yield self.exported_no_data(settings)
            self.assertEqual(data, b'')

    @defer.inlineCallbacks
    def test_export_no_items_store_empty(self):
        formats = (
            ('json', b'[\n\n]'),
            ('jsonlines', b''),
            ('xml', b'<?xml version="1.0" encoding="utf-8"?>\n<items></items>'),
            ('csv', b''),
        )

        for fmt, expctd in formats:
            settings = {'FEED_FORMAT': fmt, 'FEED_STORE_EMPTY': True}
            data = yield self.exported_no_data(settings)
            self.assertEqual(data, expctd)

    @defer.inlineCallbacks
    def test_export_multiple_item_classes(self):

        class MyItem2(scrapy.Item):
            foo = scrapy.Field()
            hello = scrapy.Field()

        items = [
            self.MyItem({'foo': 'bar1', 'egg': 'spam1'}),
            MyItem2({'hello': 'world2', 'foo': 'bar2'}),
            self.MyItem({'foo': 'bar3', 'egg': 'spam3', 'baz': 'quux3'}),
            {'hello': 'world4', 'egg': 'spam4'},
        ]

        # by default, Scrapy uses fields of the first Item for CSV and
        # all fields for JSON Lines
        header = self.MyItem.fields.keys()
        rows_csv = [
            {'egg': 'spam1', 'foo': 'bar1', 'baz': ''},
            {'egg': '',      'foo': 'bar2', 'baz': ''},
            {'egg': 'spam3', 'foo': 'bar3', 'baz': 'quux3'},
            {'egg': 'spam4', 'foo': '',     'baz': ''},
        ]
        rows_jl = [dict(row) for row in items]
        yield self.assertExportedCsv(items, header, rows_csv, ordered=False)
        yield self.assertExportedJsonLines(items, rows_jl)

        # edge case: FEED_EXPORT_FIELDS==[] means the same as default None
        settings = {'FEED_EXPORT_FIELDS': []}
        yield self.assertExportedCsv(items, header, rows_csv, ordered=False)
        yield self.assertExportedJsonLines(items, rows_jl, settings)

        # it is possible to override fields using FEED_EXPORT_FIELDS
        header = ["foo", "baz", "hello"]
        settings = {'FEED_EXPORT_FIELDS': header}
        rows = [
            {'foo': 'bar1', 'baz': '',      'hello': ''},
            {'foo': 'bar2', 'baz': '',      'hello': 'world2'},
            {'foo': 'bar3', 'baz': 'quux3', 'hello': ''},
            {'foo': '',     'baz': '',      'hello': 'world4'},
        ]
        yield self.assertExported(items, header, rows,
                                  settings=settings, ordered=True)

    @defer.inlineCallbacks
    def test_export_dicts(self):
        # When dicts are used, only keys from the first row are used as
        # a header for CSV, and all fields are used for JSON Lines.
        items = [
            {'foo': 'bar', 'egg': 'spam'},
            {'foo': 'bar', 'egg': 'spam', 'baz': 'quux'},
        ]
        rows_csv = [
            {'egg': 'spam', 'foo': 'bar'},
            {'egg': 'spam', 'foo': 'bar'}
        ]
        rows_jl = items
        yield self.assertExportedCsv(items, ['egg', 'foo'], rows_csv, ordered=False)
        yield self.assertExportedJsonLines(items, rows_jl)

    @defer.inlineCallbacks
    def test_export_feed_export_fields(self):
        # FEED_EXPORT_FIELDS option allows to order export fields
        # and to select a subset of fields to export, both for Items and dicts.

        for item_cls in [self.MyItem, dict]:
            items = [
                item_cls({'foo': 'bar1', 'egg': 'spam1'}),
                item_cls({'foo': 'bar2', 'egg': 'spam2', 'baz': 'quux2'}),
            ]

            # export all columns
            settings = {'FEED_EXPORT_FIELDS': 'foo,baz,egg'}
            rows = [
                {'egg': 'spam1', 'foo': 'bar1', 'baz': ''},
                {'egg': 'spam2', 'foo': 'bar2', 'baz': 'quux2'}
            ]
            yield self.assertExported(items, ['foo', 'baz', 'egg'], rows,
                                      settings=settings, ordered=True)

            # export a subset of columns
            settings = {'FEED_EXPORT_FIELDS': 'egg,baz'}
            rows = [
                {'egg': 'spam1', 'baz': ''},
                {'egg': 'spam2', 'baz': 'quux2'}
            ]
            yield self.assertExported(items, ['egg', 'baz'], rows,
                                      settings=settings, ordered=True)

    @defer.inlineCallbacks
    def test_export_encoding(self):
        items = [dict({'foo': u'Test\xd6'})]
        header = ['foo']

        formats = {
            'json': u'[\n{"foo": "Test\\u00d6"}\n]'.encode('utf-8'),
            'jsonlines': u'{"foo": "Test\\u00d6"}\n'.encode('utf-8'),
            'xml': u'<?xml version="1.0" encoding="utf-8"?>\n<items><item><foo>Test\xd6</foo></item></items>'.encode('utf-8'),
            'csv': u'foo\r\nTest\xd6\r\n'.encode('utf-8'),
        }

        for format in formats:
            settings = {'FEED_FORMAT': format}
            data = yield self.exported_data(items, settings)
            self.assertEqual(formats[format], data)

        formats = {
            'json': u'[\n{"foo": "Test\xd6"}\n]'.encode('latin-1'),
            'jsonlines': u'{"foo": "Test\xd6"}\n'.encode('latin-1'),
            'xml': u'<?xml version="1.0" encoding="latin-1"?>\n<items><item><foo>Test\xd6</foo></item></items>'.encode('latin-1'),
            'csv': u'foo\r\nTest\xd6\r\n'.encode('latin-1'),
        }

        for format in formats:
            settings = {'FEED_FORMAT': format, 'FEED_EXPORT_ENCODING': 'latin-1'}
            data = yield self.exported_data(items, settings)
            self.assertEqual(formats[format], data)
